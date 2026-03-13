from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from gqlrules.util import split_cypher_statements


def _neo4j_config_or_skip() -> tuple[str, str, str, str]:
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER")
    password = os.getenv("NEO4J_PASSWORD")
    database = os.getenv("NEO4J_DATABASE", "neo4j")

    if not (uri and user and password):
        pytest.skip("integration test skipped: set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD")

    try:
        from neo4j import GraphDatabase
    except ModuleNotFoundError:
        pytest.skip("integration test skipped: neo4j driver is not installed")

    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        driver.verify_connectivity()
        driver.close()
    except Exception as exc:
        pytest.skip(f"integration test skipped: cannot connect to Neo4j ({exc})")

    return uri, user, password, database


def _execute_script(uri: str, user: str, password: str, database: str, script_path: Path) -> None:
    from neo4j import GraphDatabase

    script = script_path.read_text(encoding="utf-8")
    statements = split_cypher_statements(script)

    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session(database=database) as session:
            for statement in statements:
                session.run(statement).consume()
    finally:
        driver.close()


def _parse_key_value_output(output: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in output.splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        parsed[key.strip()] = value.strip()
    return parsed


@pytest.mark.integration
def test_cli_run_reaches_fixpoint_with_live_neo4j(tmp_path: Path) -> None:
    uri, user, password, database = _neo4j_config_or_skip()

    repo_root = Path(__file__).resolve().parents[1]
    examples_banking = repo_root / "examples" / "banking"
    _execute_script(uri, user, password, database, examples_banking / "constraints.cypher")
    _execute_script(uri, user, password, database, examples_banking / "load.cypher")

    reports_dir = tmp_path / "reports"
    cmd = [
        sys.executable,
        "-m",
        "gqlrules.cli",
        "run",
        "examples/banking/program.gqlr",
        "--uri",
        uri,
        "--user",
        user,
        "--password",
        password,
        "--database",
        database,
        "--max-rounds",
        "20",
        "--reports-dir",
        str(reports_dir),
        "--csv",
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    completed = subprocess.run(
        cmd,
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        pytest.fail(f"gqlr run failed with code {completed.returncode}: {completed.stderr}")

    parsed = _parse_key_value_output(completed.stdout)
    assert parsed.get("fixpoint_reached") == "true"
    assert parsed.get("termination") == "fixpoint"
    assert int(parsed.get("rounds", "0")) <= 20

    report_path = Path(parsed["report"])
    if not report_path.is_absolute():
        report_path = repo_root / report_path
    assert report_path.exists()

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["fixpoint_reached"] is True
    assert report["termination_reason"] == "fixpoint"
    assert report["total_rounds"] <= 20
    assert report["rounds"][-1]["total_changes"] == 0

