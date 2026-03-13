from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from gqlrules.runner import RunnerError, run_fixpoint
from gqlrules.parser import parse_program


class FakeExecutor:
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.closed = False

    def execute(self, cypher: str) -> dict[str, object]:
        if not self._responses:
            raise RuntimeError("no scripted response")
        next_item = self._responses.pop(0)
        if isinstance(next_item, Exception):
            raise next_item
        assert isinstance(next_item, dict)
        return next_item

    def close(self) -> None:
        self.closed = True


def test_run_fixpoint_reaches_fixpoint_and_collects_metrics() -> None:
    source = """
RULE a MODE LOG PRIORITY 1 STRATUM 1 {
  BODY:
    MATCH (n)
  HEAD:
    RETURN 1 AS changes
}
RULE b MODE LOG PRIORITY 2 STRATUM 1 {
  BODY:
    MATCH (m)
  HEAD:
    RETURN 1 AS changes
}
""".lstrip()
    program = parse_program(source)
    executor = FakeExecutor(
        [
            {"changes": 2},
            {"changes": 1},
            {"changes": 0},
            {"changes": 0},
        ]
    )

    report = run_fixpoint(program, executor=executor, max_rounds=10)

    assert report.fixpoint_reached is True
    assert report.termination_reason == "fixpoint"
    assert report.total_rounds == 2
    assert report.total_changes == 3
    assert [rnd.total_changes for rnd in report.rounds] == [3, 0]
    assert len(report.rule_rounds) == 4


def test_log_mode_error_does_not_abort() -> None:
    source = """
RULE maybe_fails MODE LOG {
  BODY:
    MATCH (n)
  HEAD:
    RETURN 1 AS changes
}
""".lstrip()
    program = parse_program(source)
    executor = FakeExecutor([RuntimeError("boom")])

    report = run_fixpoint(program, executor=executor, max_rounds=3)

    assert report.fixpoint_reached is True
    assert report.total_rounds == 1
    assert report.rule_rounds[0].changes == 0
    assert report.rule_rounds[0].error == "boom"


def test_strict_mode_missing_changes_aborts_with_error_and_partial_report() -> None:
    source = """
RULE strict_rule MODE STRICT {
  BODY:
    MATCH (n)
  HEAD:
    RETURN 1 AS changes
}
""".lstrip()
    program = parse_program(source)
    executor = FakeExecutor([{"not_changes": 10}])

    with pytest.raises(RunnerError) as captured:
        run_fixpoint(program, executor=executor, max_rounds=5)

    err = captured.value
    assert "did not return required 'changes'" in str(err)
    assert err.report is not None
    assert err.report.termination_reason == "strict_error"
    assert err.report.total_rounds == 1
    assert err.report.fixpoint_reached is False


def test_shuffle_keeps_stratum_boundaries() -> None:
    source = """
RULE s1_a MODE LOG PRIORITY 1 STRATUM 1 {
  BODY:
    MATCH (n)
  HEAD:
    RETURN 0 AS changes
}
RULE s1_b MODE LOG PRIORITY 2 STRATUM 1 {
  BODY:
    MATCH (n)
  HEAD:
    RETURN 0 AS changes
}
RULE s2 MODE LOG PRIORITY 1 STRATUM 2 {
  BODY:
    MATCH (n)
  HEAD:
    RETURN 0 AS changes
}
""".lstrip()
    program = parse_program(source)
    executor = FakeExecutor([{"changes": 0}, {"changes": 0}, {"changes": 0}])

    report = run_fixpoint(program, executor=executor, max_rounds=1, shuffle=True, seed=7)
    first_round = [r.rule_name for r in report.rule_rounds if r.round_index == 1]

    assert first_round[-1] == "s2"
    assert set(first_round[:2]) == {"s1_a", "s1_b"}

