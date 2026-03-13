from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from gqlrules.compiler import compile_program, compile_to_directory
from gqlrules.parser import parse_program


def test_compile_sorts_rules_deterministically() -> None:
    source = """
RULE z MODE LOG PRIORITY 1 STRATUM 2 {
  BODY:
    MATCH (n)
  HEAD:
    RETURN 1 AS changes
}
RULE a MODE LOG PRIORITY 3 STRATUM 1 {
  BODY:
    MATCH (n)
  HEAD:
    RETURN 1 AS changes
}
RULE b MODE IGNORE PRIORITY 2 STRATUM 1 {
  BODY:
    MATCH (n)
  HEAD:
    RETURN 1 AS changes
}
RULE c MODE STRICT PRIORITY 2 STRATUM 1 {
  BODY:
    MATCH (n)
  HEAD:
    RETURN 1 AS changes
}
""".lstrip()

    program = parse_program(source)
    compiled = compile_program(program)
    assert [rule.name for rule in compiled] == ["b", "c", "a", "z"]


def test_compile_combines_body_and_head_with_single_separator_newline() -> None:
    source = (
        "RULE r MODE LOG {\n"
        "  BODY:\n"
        "    MATCH (n)\n"
        "  HEAD:\n"
        "    RETURN 1 AS changes\n"
        "}\n"
    )
    program = parse_program(source)
    compiled = compile_program(program)
    assert compiled[0].cypher == "    MATCH (n)\n\n    RETURN 1 AS changes\n"


def test_compile_writes_rules_and_manifest(tmp_path: Path) -> None:
    source = """
PROGRAM Demo;
RULE r1 MODE LOG PRIORITY 5 STRATUM 1 {
  BODY:
    MATCH (n)
  HEAD:
    RETURN 1 AS changes
}
RULE r2 MODE LOG PRIORITY 1 STRATUM 1 {
  BODY:
    MATCH (m)
  HEAD:
    RETURN 2 AS changes
}
""".lstrip()
    program = parse_program(source)

    artifacts = compile_to_directory(program, out_dir=tmp_path, source_path="demo.gqlr")

    first_rule = artifacts.rules_dir / "01_r2.cypher"
    second_rule = artifacts.rules_dir / "02_r1.cypher"
    assert first_rule.exists()
    assert second_rule.exists()
    assert artifacts.manifest_path.exists()

    manifest = json.loads(artifacts.manifest_path.read_text(encoding="utf-8"))
    assert manifest["program_name"] == "Demo"
    assert manifest["rule_count"] == 2
    assert [entry["name"] for entry in manifest["rules"]] == ["r2", "r1"]
