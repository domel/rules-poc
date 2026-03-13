from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from gqlrules.parser import parse_file


def test_all_example_programs_are_parseable() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    programs = sorted((repo_root / "examples").glob("*/program.gqlr"))
    assert programs, "expected at least one demo program"
    for program_path in programs:
        program = parse_file(program_path)
        assert len(program.rules) > 0, f"program has no rules: {program_path}"

