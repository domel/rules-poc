from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from gqlrules.parser import ParseError, parse_program


def test_parse_wrapper_only_rule_with_program_settings_imports_and_declarations() -> None:
    source = """
PROGRAM Banking;
IMPORT "shared/base.gqlr";
DECLARE EDGE KEY TRANSFER.txId FUNCTIONAL;
SETTINGS {
  max_rounds: 50
  shuffle: false
}

RULE suspiciousTransfers MODE LOG PRIORITY 5 STRATUM 2 {
  DECLARE GRAPH bank;
  BODY:
    MATCH (a:Account)-[t:TRANSFER]->(b:Account)
    WHERE t.amount > 10000
  HEAD:
    MERGE (a)-[:SUSPICIOUS_TRANSFER]->(b)
    RETURN count(*) AS changes
}
""".lstrip()

    program = parse_program(source)

    assert program.program_name == "Banking"
    assert program.imports == ("shared/base.gqlr",)
    assert program.declarations == ("EDGE KEY TRANSFER.txId FUNCTIONAL",)
    assert program.settings == {"max_rounds": 50, "shuffle": False}
    assert len(program.rules) == 1

    rule = program.rules[0]
    assert rule.name == "suspiciousTransfers"
    assert rule.mode == "LOG"
    assert rule.priority == 5
    assert rule.stratum == 2
    assert rule.declarations == ("GRAPH bank",)

    expected_body = (
        "    MATCH (a:Account)-[t:TRANSFER]->(b:Account)\n"
        "    WHERE t.amount > 10000\n"
    )
    expected_head = (
        "    MERGE (a)-[:SUSPICIOUS_TRANSFER]->(b)\n"
        "    RETURN count(*) AS changes\n"
    )
    assert rule.body == expected_body
    assert rule.head == expected_head


def test_missing_mode_is_error() -> None:
    source = """
RULE r1 {
  BODY:
    RETURN 0 AS changes
  HEAD:
    RETURN 0 AS changes
}
""".lstrip()

    with pytest.raises(ParseError, match="invalid RULE header"):
        parse_program(source)


def test_missing_body_or_head_is_error() -> None:
    missing_body = """
RULE r1 MODE LOG {
  HEAD:
    RETURN 0 AS changes
}
""".lstrip()
    with pytest.raises(ParseError, match="missing BODY"):
        parse_program(missing_body)

    missing_head = """
RULE r1 MODE LOG {
  BODY:
    RETURN 0 AS changes
}
""".lstrip()
    with pytest.raises(ParseError, match="missing HEAD"):
        parse_program(missing_head)


def test_body_head_whitespace_is_preserved_1_to_1() -> None:
    source = (
        "RULE keep MODE STRICT {\n"
        "  BODY:\n"
        "\tMATCH (n)\n"
        "    WHERE n.name = \"A\"   \n"
        "\n"
        "  HEAD:\n"
        "    MERGE (n)-[:FLAG]->(:Marker {k: \"v\"})\n"
        "      RETURN 1 AS changes\n"
        "}\n"
    )

    program = parse_program(source)
    rule = program.rules[0]
    assert rule.body == "\tMATCH (n)\n    WHERE n.name = \"A\"   \n\n"
    assert rule.head == "    MERGE (n)-[:FLAG]->(:Marker {k: \"v\"})\n      RETURN 1 AS changes\n"


def test_rule_block_priority_and_stratum_lines_are_supported() -> None:
    source = """
RULE r2 MODE IGNORE {
  PRIORITY: -1
  STRATUM: 3
  BODY:
    MATCH (a)
  HEAD:
    CALL {
      WITH a
      RETURN a
    }
    RETURN 1 AS changes
}
;
""".lstrip()

    program = parse_program(source)
    rule = program.rules[0]
    assert rule.priority == -1
    assert rule.stratum == 3
    assert "CALL {\n" in rule.head

