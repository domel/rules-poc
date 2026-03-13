from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from gqlrules.demo import run_demo


class FakeExecutor:
    def __init__(self, responses: list[dict[str, int]]) -> None:
        self.responses = list(responses)
        self.executed: list[str] = []

    def execute(self, cypher: str) -> dict[str, int]:
        self.executed.append(cypher)
        if not self.responses:
            raise RuntimeError("unexpected extra query")
        return self.responses.pop(0)


def test_run_demo_banking_executes_scripts_and_writes_report(tmp_path: Path) -> None:
    examples_dir = tmp_path / "examples"
    banking = examples_dir / "banking"
    banking.mkdir(parents=True)

    (banking / "program.gqlr").write_text(
        """
PROGRAM BankingPoC;
RULE one MODE LOG {
  BODY:
    MATCH (n)
  HEAD:
    RETURN 1 AS changes
}
""".lstrip(),
        encoding="utf-8",
    )
    (banking / "constraints.cypher").write_text("CREATE (:ConstraintMarker);\n", encoding="utf-8")
    (banking / "load.cypher").write_text("CREATE (:LoadMarker);\n", encoding="utf-8")
    (banking / "postconditions.cypher").write_text("RETURN 42 AS answer;\n", encoding="utf-8")

    executor = FakeExecutor(
        [
            {},  # constraints
            {},  # load
            {"changes": 1},  # round1 rule
            {"changes": 0},  # round2 rule -> fixpoint
            {"answer": 42},  # postcondition
        ]
    )

    result = run_demo(
        "banking",
        examples_dir=examples_dir,
        reports_dir=tmp_path / "reports",
        executor=executor,
        max_rounds=10,
    )

    assert result.report.fixpoint_reached is True
    assert result.report.total_rounds == 2
    assert result.report_path.exists()
    assert result.executed_scripts == ("constraints.cypher", "load.cypher", "postconditions.cypher")
    assert result.postconditions_results == ({"answer": 42},)

