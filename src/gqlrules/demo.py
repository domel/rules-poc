from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .metrics import RunReport, write_report_csv, write_report_json
from .parser import parse_file
from .runner import Neo4jExecutor, QueryExecutor, RunnerError, run_fixpoint
from .util import execute_cypher_script


@dataclass(frozen=True)
class DemoResult:
    report: RunReport
    report_path: Path
    report_csv_path: Path | None
    executed_scripts: tuple[str, ...]
    postconditions_results: tuple[dict[str, Any], ...]


def run_demo(
    name: str,
    *,
    examples_dir: str | Path = "examples",
    uri: str = "bolt://localhost:7687",
    user: str = "neo4j",
    password: str | None = "domeldomel",
    database: str | None = "neo4j",
    max_rounds: int = 50,
    shuffle: bool = False,
    seed: int | None = None,
    reports_dir: str | Path = "reports",
    csv: bool = False,
    executor: QueryExecutor | None = None,
) -> DemoResult:
    demo_dir = Path(examples_dir) / name
    if not demo_dir.is_dir():
        raise FileNotFoundError(f"demo directory not found: {demo_dir}")

    program_path = demo_dir / "program.gqlr"
    if not program_path.exists():
        raise FileNotFoundError(f"missing program file: {program_path}")

    program = parse_file(program_path)

    own_executor = False
    if executor is None:
        if not password:
            raise RunnerError("password is required for demo when custom executor is not provided")
        executor = Neo4jExecutor(uri=uri, user=user, password=password, database=database)
        own_executor = True

    executed_scripts: list[str] = []
    postconditions_results: list[dict[str, Any]] = []

    try:
        for pre_name in ("constraints.cypher", "load.cypher"):
            pre_path = demo_dir / pre_name
            if pre_path.exists():
                try:
                    execute_cypher_script(executor, pre_path.read_text(encoding="utf-8"))
                except Exception as exc:
                    raise RunnerError(f"failed while executing {pre_name}: {exc}") from exc
                executed_scripts.append(pre_name)

        report = run_fixpoint(
            program,
            uri=uri,
            user=user,
            password=password,
            database=database,
            max_rounds=max_rounds,
            shuffle=shuffle,
            seed=seed,
            executor=executor,
        )

        post_path = demo_dir / "postconditions.cypher"
        if post_path.exists():
            try:
                postconditions_results = execute_cypher_script(executor, post_path.read_text(encoding="utf-8"))
            except Exception as exc:
                raise RunnerError(f"failed while executing postconditions.cypher: {exc}") from exc
            executed_scripts.append("postconditions.cypher")

        report_path = write_report_json(report, reports_dir=reports_dir)
        csv_path = write_report_csv(report, reports_dir=reports_dir) if csv else None
        return DemoResult(
            report=report,
            report_path=report_path,
            report_csv_path=csv_path,
            executed_scripts=tuple(executed_scripts),
            postconditions_results=tuple(postconditions_results),
        )
    finally:
        if own_executor:
            close_fn = getattr(executor, "close", None)
            if callable(close_fn):
                close_fn()
