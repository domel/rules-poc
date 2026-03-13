from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import statistics
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gqlrules.demo import run_demo
from gqlrules.parser import parse_file
from gqlrules.runner import Neo4jExecutor, RunnerError, run_fixpoint
from gqlrules.util import execute_cypher_script


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _load_script_if_exists(executor: Neo4jExecutor, path: Path) -> None:
    if path.exists():
        execute_cypher_script(executor, path.read_text(encoding="utf-8"))


def _run_postconditions(executor: Neo4jExecutor, path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return execute_cypher_script(executor, path.read_text(encoding="utf-8"))


def _time_total_ms(report: Any) -> float:
    return round(sum(r.time_ms for r in report.rounds), 3)


def run_e1(uri: str, user: str, password: str, database: str, reports_dir: Path) -> dict[str, Any]:
    scenarios = {
        "banking": _check_banking,
        "family": _check_family,
        "compliance": _check_compliance,
    }

    results: dict[str, Any] = {}
    for scenario, checker in scenarios.items():
        result = run_demo(
            scenario,
            uri=uri,
            user=user,
            password=password,
            database=database,
            reports_dir=reports_dir / "e1",
            csv=True,
            max_rounds=50,
        )
        checks = checker(result.postconditions_results)
        results[scenario] = {
            "pass": all(item["ok"] for item in checks),
            "checks": checks,
            "rounds": result.report.total_rounds,
            "fixpoint_reached": result.report.fixpoint_reached,
            "total_changes": result.report.total_changes,
            "time_total_ms": _time_total_ms(result.report),
            "report_path": str(result.report_path),
        }
    return results


def run_e2(uri: str, user: str, password: str, database: str) -> dict[str, Any]:
    base_dir = Path("examples")
    scenarios = ["banking", "family", "compliance"]
    results: dict[str, Any] = {}
    executor = Neo4jExecutor(uri=uri, user=user, password=password, database=database)
    try:
        for scenario in scenarios:
            scenario_dir = base_dir / scenario
            _load_script_if_exists(executor, scenario_dir / "constraints.cypher")
            _load_script_if_exists(executor, scenario_dir / "load.cypher")
            program = parse_file(scenario_dir / "program.gqlr")

            first = run_fixpoint(
                program,
                uri=uri,
                user=user,
                password=password,
                database=database,
                executor=executor,
                max_rounds=50,
            )
            second = run_fixpoint(
                program,
                uri=uri,
                user=user,
                password=password,
                database=database,
                executor=executor,
                max_rounds=5,
            )

            results[scenario] = {
                "pass": second.total_changes == 0 and second.fixpoint_reached,
                "first_run": {
                    "total_changes": first.total_changes,
                    "rounds": first.total_rounds,
                    "time_total_ms": _time_total_ms(first),
                },
                "second_run_after_fixpoint": {
                    "total_changes": second.total_changes,
                    "rounds": second.total_rounds,
                    "time_total_ms": _time_total_ms(second),
                },
            }
    finally:
        executor.close()
    return results


def run_e3(uri: str, user: str, password: str, database: str, seeds: int) -> dict[str, Any]:
    scenario_dir = Path("examples") / "family"
    executor = Neo4jExecutor(uri=uri, user=user, password=password, database=database)
    program = parse_file(scenario_dir / "program.gqlr")

    rounds: list[int] = []
    time_totals: list[float] = []
    hashes: list[str] = []
    fingerprints: list[dict[str, Any]] = []

    try:
        _load_script_if_exists(executor, scenario_dir / "constraints.cypher")
        for seed in range(seeds):
            _load_script_if_exists(executor, scenario_dir / "load.cypher")
            report = run_fixpoint(
                program,
                uri=uri,
                user=user,
                password=password,
                database=database,
                executor=executor,
                max_rounds=50,
                shuffle=True,
                seed=seed,
            )
            fp_row = executor.execute(
                """
                MATCH (x:DemoFamilyPerson)-[:DESCENDED_FROM {demo: "family"}]->(y:DemoFamilyPerson)
                WITH x.id + "->" + y.id AS pair
                ORDER BY pair
                RETURN collect(pair) AS pairs, count(*) AS edge_count
                """
            )
            pairs = fp_row.get("pairs", [])
            edge_count = int(fp_row.get("edge_count", 0))
            digest = hashlib.sha256(json.dumps(pairs, ensure_ascii=False).encode("utf-8")).hexdigest()

            rounds.append(report.total_rounds)
            time_totals.append(_time_total_ms(report))
            hashes.append(digest)
            fingerprints.append(
                {
                    "seed": seed,
                    "rounds": report.total_rounds,
                    "time_total_ms": _time_total_ms(report),
                    "edge_count": edge_count,
                    "result_hash": digest,
                }
            )
    finally:
        executor.close()

    unique_hashes = sorted(set(hashes))
    return {
        "pass": len(unique_hashes) == 1,
        "runs": seeds,
        "unique_hashes": len(unique_hashes),
        "hashes": unique_hashes,
        "rounds": {
            "min": min(rounds) if rounds else None,
            "max": max(rounds) if rounds else None,
            "median": statistics.median(rounds) if rounds else None,
        },
        "time_total_ms": {
            "min": min(time_totals) if time_totals else None,
            "max": max(time_totals) if time_totals else None,
            "median": round(statistics.median(time_totals), 3) if time_totals else None,
        },
        "samples": fingerprints,
    }


def run_e4(uri: str, user: str, password: str, database: str) -> dict[str, Any]:
    base_dir = Path("examples") / "mode_robustness"
    executor = Neo4jExecutor(uri=uri, user=user, password=password, database=database)
    modes = {
        "LOG": base_dir / "program_log.gqlr",
        "IGNORE": base_dir / "program_ignore.gqlr",
        "STRICT": base_dir / "program_strict.gqlr",
    }
    results: dict[str, Any] = {}

    try:
        for mode_name, program_path in modes.items():
            _load_script_if_exists(executor, base_dir / "load.cypher")
            program = parse_file(program_path)
            try:
                report = run_fixpoint(
                    program,
                    uri=uri,
                    user=user,
                    password=password,
                    database=database,
                    executor=executor,
                    max_rounds=5,
                )
                errors = sum(1 for metric in report.rule_rounds if metric.error)
                results[mode_name] = {
                    "finished": True,
                    "termination": report.termination_reason,
                    "errors_in_report": errors,
                    "fixpoint_reached": report.fixpoint_reached,
                    "time_total_ms": _time_total_ms(report),
                }
            except RunnerError as exc:
                report = exc.report
                errors = 0
                if report is not None:
                    errors = sum(1 for metric in report.rule_rounds if metric.error)
                results[mode_name] = {
                    "finished": False,
                    "termination": report.termination_reason if report is not None else "strict_error",
                    "errors_in_report": errors,
                    "fixpoint_reached": False,
                    "time_total_ms": _time_total_ms(report) if report is not None else None,
                    "error_message": str(exc),
                }
    finally:
        executor.close()

    pass_condition = (
        results.get("STRICT", {}).get("finished") is False
        and results.get("LOG", {}).get("finished") is True
        and results.get("IGNORE", {}).get("finished") is True
    )
    return {"pass": pass_condition, "modes": results}


def run_e5(uri: str, user: str, password: str, database: str, sizes: list[int]) -> dict[str, Any]:
    executor = Neo4jExecutor(uri=uri, user=user, password=password, database=database)
    scenario_dir = Path("examples") / "closure_scale"
    program = parse_file(scenario_dir / "program.gqlr")
    _load_script_if_exists(executor, scenario_dir / "constraints.cypher")

    def run_shape(shape: str, n: int) -> dict[str, Any]:
        _reset_scale_dataset(executor)
        if shape == "chain":
            _load_chain(executor, n)
        elif shape == "tree":
            _load_binary_tree(executor, n)
        else:
            raise ValueError(shape)

        report = run_fixpoint(
            program,
            uri=uri,
            user=user,
            password=password,
            database=database,
            executor=executor,
            max_rounds=max(50, n + 5),
        )
        facts_row = executor.execute(
            'MATCH ()-[r:REACHES {demo: "closure_scale"}]->() RETURN count(r) AS reaches_count'
        )
        return {
            "shape": shape,
            "n": n,
            "rounds": report.total_rounds,
            "fixpoint_reached": report.fixpoint_reached,
            "time_total_ms": _time_total_ms(report),
            "reaches_count": int(facts_row.get("reaches_count", 0)),
        }

    samples: list[dict[str, Any]] = []
    try:
        for n in sizes:
            samples.append(run_shape("chain", n))
            samples.append(run_shape("tree", n))
    finally:
        executor.close()

    return {"sizes": sizes, "samples": samples}


def run_e6(uri: str, user: str, password: str, database: str, repeats: int) -> dict[str, Any]:
    base_dir = Path("examples") / "mode_robustness"
    executor = Neo4jExecutor(uri=uri, user=user, password=password, database=database)

    def measure(program_path: Path) -> list[float]:
        program = parse_file(program_path)
        times: list[float] = []
        for _ in range(repeats):
            _load_script_if_exists(executor, base_dir / "load.cypher")
            report = run_fixpoint(
                program,
                uri=uri,
                user=user,
                password=password,
                database=database,
                executor=executor,
                max_rounds=5,
            )
            times.append(_time_total_ms(report))
        return times

    try:
        log_times = measure(base_dir / "program_log.gqlr")
        ignore_times = measure(base_dir / "program_ignore.gqlr")
    finally:
        executor.close()

    log_median = statistics.median(log_times) if log_times else 0.0
    ignore_median = statistics.median(ignore_times) if ignore_times else 0.0
    overhead_pct = ((log_median - ignore_median) / ignore_median * 100.0) if ignore_median > 0 else None
    return {
        "repeats": repeats,
        "log_time_ms": {"median": round(log_median, 3), "samples": log_times},
        "ignore_time_ms": {"median": round(ignore_median, 3), "samples": ignore_times},
        "log_over_ignore_pct": round(overhead_pct, 3) if overhead_pct is not None else None,
    }


def _reset_scale_dataset(executor: Neo4jExecutor) -> None:
    executor.execute("MATCH (n:DemoScaleNode) DETACH DELETE n RETURN 0 AS changes")


def _load_chain(executor: Neo4jExecutor, n: int) -> None:
    executor.execute(
        f"""
        UNWIND range(1, {n}) AS i
        CREATE (:DemoScaleNode {{id: "chain-" + toString(i), idx: i, demo: "closure_scale", shape: "chain"}})
        RETURN count(*) AS changes
        """
    )
    executor.execute(
        f"""
        UNWIND range(1, {n - 1}) AS i
        MATCH (a:DemoScaleNode {{id: "chain-" + toString(i), demo: "closure_scale"}}),
              (b:DemoScaleNode {{id: "chain-" + toString(i + 1), demo: "closure_scale"}})
        MERGE (a)-[:NEXT {{demo: "closure_scale"}}]->(b)
        RETURN count(*) AS changes
        """
    )


def _load_binary_tree(executor: Neo4jExecutor, n: int) -> None:
    executor.execute(
        f"""
        UNWIND range(1, {n}) AS i
        CREATE (:DemoScaleNode {{id: "tree-" + toString(i), idx: i, demo: "closure_scale", shape: "tree"}})
        RETURN count(*) AS changes
        """
    )
    executor.execute(
        f"""
        UNWIND range(1, {n}) AS i
        MATCH (p:DemoScaleNode {{id: "tree-" + toString(i), demo: "closure_scale"}})
        UNWIND [2 * i, 2 * i + 1] AS child
        WITH p, child WHERE child <= {n}
        MATCH (c:DemoScaleNode {{id: "tree-" + toString(child), demo: "closure_scale"}})
        MERGE (p)-[:NEXT {{demo: "closure_scale"}}]->(c)
        RETURN count(*) AS changes
        """
    )


def _check_banking(post: tuple[dict[str, Any], ...]) -> list[dict[str, Any]]:
    post_list = list(post)
    suspicious = int(post_list[0]["suspicious_transfer_edges"])
    tx_count = int(post_list[1]["tx991_transfer_edges"])
    person_names = post_list[2]["person_names"]
    has_unknown = any(item.get("id") == "P2" and item.get("effective_name") == "Unknown" for item in person_names)
    return [
        {"name": "suspicious_transfer_edges == 1", "ok": suspicious == 1, "value": suspicious},
        {"name": "tx991_transfer_edges == 1", "ok": tx_count == 1, "value": tx_count},
        {"name": "P2 fallback unknown", "ok": has_unknown, "value": has_unknown},
    ]


def _check_family(post: tuple[dict[str, Any], ...]) -> list[dict[str, Any]]:
    post_list = list(post)
    child = int(post_list[0]["child_of_edges"])
    closure = int(post_list[1]["descended_from_edges"])
    pairs = sorted(post_list[2]["descended_pairs"])
    expected = sorted(["CARA->ANN", "CARA->BOB", "BOB->ANN", "DAN->ANN"])
    return [
        {"name": "child_of_edges == 3", "ok": child == 3, "value": child},
        {"name": "descended_from_edges == 4", "ok": closure == 4, "value": closure},
        {"name": "descended_pairs match expected", "ok": pairs == expected, "value": pairs},
    ]


def _check_compliance(post: tuple[dict[str, Any], ...]) -> list[dict[str, Any]]:
    post_list = list(post)
    risk = int(post_list[0]["risk_transfer_edges"])
    defaulted = int(post_list[1]["country_defaulted_edges"])
    frequent = int(post_list[2]["frequent_receiver_edges"])
    return [
        {"name": "risk_transfer_edges == 2", "ok": risk == 2, "value": risk},
        {"name": "country_defaulted_edges == 1", "ok": defaulted == 1, "value": defaulted},
        {"name": "frequent_receiver_edges == 1", "ok": frequent == 1, "value": frequent},
    ]


def write_markdown_summary(payload: dict[str, Any], out_path: Path) -> None:
    lines: list[str] = []
    lines.append("# Evaluation Summary")
    lines.append("")
    lines.append(f"- timestamp_utc: `{payload['timestamp_utc']}`")
    lines.append(f"- uri: `{payload['config']['uri']}`")
    lines.append(f"- database: `{payload['config']['database']}`")
    lines.append("")

    e1 = payload["e1"]
    lines.append("## E1 Functional Correctness")
    for scenario, result in e1.items():
        status = "PASS" if result["pass"] else "FAIL"
        lines.append(f"- {scenario}: `{status}`, rounds={result['rounds']}, time_total_ms={result['time_total_ms']}")
    lines.append("")

    e2 = payload["e2"]
    lines.append("## E2 Idempotence")
    for scenario, result in e2.items():
        status = "PASS" if result["pass"] else "FAIL"
        second = result["second_run_after_fixpoint"]
        lines.append(
            f"- {scenario}: `{status}`, second_run_total_changes={second['total_changes']}, second_run_rounds={second['rounds']}"
        )
    lines.append("")

    e3 = payload["e3"]
    lines.append("## E3 Determinism")
    lines.append(
        f"- pass={e3['pass']}, runs={e3['runs']}, unique_hashes={e3['unique_hashes']}, median_rounds={e3['rounds']['median']}"
    )
    lines.append("")

    e4 = payload["e4"]
    lines.append("## E4 MODE Robustness")
    lines.append(f"- pass={e4['pass']}")
    for mode, result in e4["modes"].items():
        lines.append(
            f"- {mode}: finished={result['finished']}, termination={result['termination']}, errors={result['errors_in_report']}"
        )
    lines.append("")

    e5 = payload["e5"]
    lines.append("## E5 Scaling (Naive Fixpoint)")
    for sample in e5["samples"]:
        lines.append(
            f"- {sample['shape']} N={sample['n']}: rounds={sample['rounds']}, time_total_ms={sample['time_total_ms']}, reaches={sample['reaches_count']}"
        )
    lines.append("")

    e6 = payload["e6"]
    lines.append("## E6 Diagnostics Overhead")
    lines.append(
        f"- repeats={e6['repeats']}, log_median_ms={e6['log_time_ms']['median']}, ignore_median_ms={e6['ignore_time_ms']['median']}, overhead_pct={e6['log_over_ignore_pct']}"
    )
    lines.append("")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_csv_exports(payload: dict[str, Any], reports_dir: Path, stamp: str) -> tuple[Path, Path]:
    e3_path = reports_dir / f"evaluation_{stamp}_e3_samples.csv"
    e5_path = reports_dir / f"evaluation_{stamp}_e5_scaling.csv"

    with e3_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["seed", "rounds", "time_total_ms", "edge_count", "result_hash"])
        for row in payload["e3"]["samples"]:
            writer.writerow([row["seed"], row["rounds"], row["time_total_ms"], row["edge_count"], row["result_hash"]])

    with e5_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["shape", "n", "rounds", "fixpoint_reached", "time_total_ms", "reaches_count"])
        for row in payload["e5"]["samples"]:
            writer.writerow(
                [row["shape"], row["n"], row["rounds"], row["fixpoint_reached"], row["time_total_ms"], row["reaches_count"]]
            )

    return e3_path, e5_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the evaluation experiments for the gqlrules PoC")
    parser.add_argument("--uri", default=os.getenv("NEO4J_URI", "bolt://localhost:7687"))
    parser.add_argument("--user", default=os.getenv("NEO4J_USER", "neo4j"))
    parser.add_argument("--password", default=os.getenv("NEO4J_PASSWORD", "domeldomel"))
    parser.add_argument("--database", default=os.getenv("NEO4J_DATABASE", "neo4j"))
    parser.add_argument("--reports-dir", default="reports")
    parser.add_argument("--determinism-seeds", type=int, default=10)
    parser.add_argument("--scale-sizes", default="50,100,200")
    parser.add_argument("--e6-repeats", type=int, default=10)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    reports_dir = Path(args.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    stamp = _now_stamp()

    sizes = [int(item.strip()) for item in args.scale_sizes.split(",") if item.strip()]
    if not sizes:
        raise ValueError("scale sizes cannot be empty")

    payload: dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "config": {
            "uri": args.uri,
            "user": args.user,
            "database": args.database,
            "determinism_seeds": args.determinism_seeds,
            "scale_sizes": sizes,
            "e6_repeats": args.e6_repeats,
        },
    }

    payload["e1"] = run_e1(args.uri, args.user, args.password, args.database, reports_dir)
    payload["e2"] = run_e2(args.uri, args.user, args.password, args.database)
    payload["e3"] = run_e3(args.uri, args.user, args.password, args.database, args.determinism_seeds)
    payload["e4"] = run_e4(args.uri, args.user, args.password, args.database)
    payload["e5"] = run_e5(args.uri, args.user, args.password, args.database, sizes)
    payload["e6"] = run_e6(args.uri, args.user, args.password, args.database, args.e6_repeats)

    json_path = reports_dir / f"evaluation_{stamp}.json"
    md_path = reports_dir / f"evaluation_{stamp}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown_summary(payload, md_path)
    e3_csv_path, e5_csv_path = write_csv_exports(payload, reports_dir, stamp)

    print(f"evaluation_json={json_path}")
    print(f"evaluation_md={md_path}")
    print(f"evaluation_e3_csv={e3_csv_path}")
    print(f"evaluation_e5_csv={e5_csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
