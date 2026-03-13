from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from gqlrules.demo import run_demo


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


@pytest.mark.integration
def test_demo_banking_reaches_fixpoint_with_live_neo4j(tmp_path: Path) -> None:
    uri, user, password, database = _neo4j_config_or_skip()
    result = run_demo(
        "banking",
        uri=uri,
        user=user,
        password=password,
        database=database,
        reports_dir=tmp_path / "reports",
        max_rounds=20,
    )

    assert result.report.fixpoint_reached is True
    assert result.report.total_rounds <= 20
    assert result.executed_scripts == ("constraints.cypher", "load.cypher", "postconditions.cypher")
    assert len(result.postconditions_results) == 3

    suspicious = result.postconditions_results[0]["suspicious_transfer_edges"]
    tx991_count = result.postconditions_results[1]["tx991_transfer_edges"]
    person_names = result.postconditions_results[2]["person_names"]

    assert suspicious == 1
    assert tx991_count == 1
    assert any(entry["id"] == "P2" and entry["effective_name"] == "Unknown" for entry in person_names)

