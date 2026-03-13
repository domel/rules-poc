from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from gqlrules.metrics import (
    RoundMetric,
    RuleRoundMetric,
    RunConfig,
    RunReport,
    write_report_csv,
    write_report_json,
)


def test_write_report_json_and_csv(tmp_path: Path) -> None:
    report = RunReport(
        run_id="run_test_001",
        timestamp_start="2026-03-03T10:00:00+00:00",
        timestamp_end="2026-03-03T10:00:01+00:00",
        config=RunConfig(
            uri="bolt://localhost:7687",
            database="neo4j",
            max_rounds=10,
            shuffle=False,
            seed=123,
        ),
        program_hash="abc",
        rounds=[RoundMetric(round_index=1, total_changes=3, time_ms=11.5)],
        rule_rounds=[
            RuleRoundMetric(
                round_index=1,
                rule_name="r1",
                mode="LOG",
                changes=3,
                time_ms=4.2,
                error=None,
                warning=None,
            )
        ],
        total_rounds=1,
        total_changes=3,
        fixpoint_reached=False,
        termination_reason="max_rounds",
    )

    json_path = write_report_json(report, tmp_path)
    csv_path = write_report_csv(report, tmp_path)

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["run_id"] == "run_test_001"
    assert payload["rounds"][0]["total_changes"] == 3

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == ["round_index", "rule_name", "mode", "changes", "time_ms", "error", "warning"]
    assert rows[1][1] == "r1"
    assert rows[1][3] == "3"

