from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gqlrules.parser import parse_file
from gqlrules.runner import Neo4jExecutor, run_fixpoint


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _parse_sizes(raw: str) -> list[int]:
    values = [int(item.strip()) for item in raw.split(",") if item.strip()]
    if not values:
        raise ValueError("size list cannot be empty")
    for value in values:
        if value < 2:
            raise ValueError(f"size must be >= 2, got {value}")
    return values


def _time_total_ms(report: Any) -> float:
    return round(sum(round_item.time_ms for round_item in report.rounds), 3)


def _reset_scale_dataset(executor: Neo4jExecutor) -> None:
    executor.execute("MATCH (n:DemoScaleNode) DETACH DELETE n RETURN 0 AS changes")


def _load_constraints(executor: Neo4jExecutor) -> None:
    constraints_path = Path("examples/closure_scale/constraints.cypher")
    statements = constraints_path.read_text(encoding="utf-8").split(";")
    for statement in statements:
        query = statement.strip()
        if query:
            executor.execute(query)


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


def run_large_scale_e5(
    *,
    uri: str,
    user: str,
    password: str,
    database: str,
    chain_sizes: list[int],
    tree_sizes: list[int],
) -> dict[str, Any]:
    executor = Neo4jExecutor(uri=uri, user=user, password=password, database=database)
    program = parse_file("examples/closure_scale/program.gqlr")

    results: list[dict[str, Any]] = []
    try:
        _load_constraints(executor)
        for n in chain_sizes:
            _reset_scale_dataset(executor)
            _load_chain(executor, n)
            report = run_fixpoint(
                program,
                uri=uri,
                user=user,
                password=password,
                database=database,
                executor=executor,
                max_rounds=max(200, n + 5),
            )
            reaches = executor.execute(
                'MATCH ()-[r:REACHES {demo: "closure_scale"}]->() RETURN count(r) AS c'
            )["c"]
            results.append(
                {
                    "shape": "chain",
                    "n": n,
                    "rounds": report.total_rounds,
                    "fixpoint_reached": report.fixpoint_reached,
                    "time_total_ms": _time_total_ms(report),
                    "reaches_count": int(reaches),
                }
            )

        for n in tree_sizes:
            _reset_scale_dataset(executor)
            _load_binary_tree(executor, n)
            report = run_fixpoint(
                program,
                uri=uri,
                user=user,
                password=password,
                database=database,
                executor=executor,
                max_rounds=max(200, n + 5),
            )
            reaches = executor.execute(
                'MATCH ()-[r:REACHES {demo: "closure_scale"}]->() RETURN count(r) AS c'
            )["c"]
            results.append(
                {
                    "shape": "tree",
                    "n": n,
                    "rounds": report.total_rounds,
                    "fixpoint_reached": report.fixpoint_reached,
                    "time_total_ms": _time_total_ms(report),
                    "reaches_count": int(reaches),
                }
            )
    finally:
        executor.close()

    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "config": {
            "uri": uri,
            "database": database,
            "chain_sizes": chain_sizes,
            "tree_sizes": tree_sizes,
        },
        "samples": results,
    }


def write_outputs(payload: dict[str, Any], reports_dir: Path, stamp: str) -> tuple[Path, Path, Path]:
    json_path = reports_dir / f"evaluation_large_e5_{stamp}.json"
    csv_path = reports_dir / f"evaluation_large_e5_{stamp}.csv"
    md_path = reports_dir / f"evaluation_large_e5_{stamp}.md"

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["shape", "n", "rounds", "fixpoint_reached", "time_total_ms", "reaches_count"])
        for row in payload["samples"]:
            writer.writerow(
                [
                    row["shape"],
                    row["n"],
                    row["rounds"],
                    row["fixpoint_reached"],
                    row["time_total_ms"],
                    row["reaches_count"],
                ]
            )

    lines: list[str] = []
    lines.append("# Large-Scale E5")
    lines.append("")
    lines.append(f"- timestamp_utc: `{payload['timestamp_utc']}`")
    lines.append(f"- uri: `{payload['config']['uri']}`")
    lines.append(f"- database: `{payload['config']['database']}`")
    lines.append(f"- chain_sizes: `{payload['config']['chain_sizes']}`")
    lines.append(f"- tree_sizes: `{payload['config']['tree_sizes']}`")
    lines.append("")
    for row in payload["samples"]:
        lines.append(
            f"- {row['shape']} N={row['n']}: rounds={row['rounds']}, time_total_ms={row['time_total_ms']}, reaches={row['reaches_count']}"
        )
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")

    return json_path, csv_path, md_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run large-scale E5 benchmark only")
    parser.add_argument("--uri", default=os.getenv("NEO4J_URI", "bolt://localhost:7687"))
    parser.add_argument("--user", default=os.getenv("NEO4J_USER", "neo4j"))
    parser.add_argument("--password", default=os.getenv("NEO4J_PASSWORD", "domeldomel"))
    parser.add_argument("--database", default=os.getenv("NEO4J_DATABASE", "neo4j"))
    parser.add_argument("--reports-dir", default="reports")
    parser.add_argument("--chain-sizes", default="200,400")
    parser.add_argument("--tree-sizes", default="200,400,800,1600,3200")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    reports_dir = Path(args.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    stamp = _now_stamp()

    chain_sizes = _parse_sizes(args.chain_sizes)
    tree_sizes = _parse_sizes(args.tree_sizes)

    payload = run_large_scale_e5(
        uri=args.uri,
        user=args.user,
        password=args.password,
        database=args.database,
        chain_sizes=chain_sizes,
        tree_sizes=tree_sizes,
    )
    json_path, csv_path, md_path = write_outputs(payload, reports_dir, stamp)

    print(f"large_e5_json={json_path}")
    print(f"large_e5_csv={csv_path}")
    print(f"large_e5_md={md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

