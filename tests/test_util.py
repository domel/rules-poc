from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from gqlrules.util import split_cypher_statements


def test_split_cypher_statements_handles_quotes_and_comments() -> None:
    script = """
// comment with ; that should be ignored
CREATE (:A {txt: "a;b"});
CREATE (:B {txt: 'x;y'});
/* block ; comment ; */
MATCH (n)
WHERE n.name = "x;y"
RETURN count(n) AS c;
""".lstrip()

    statements = split_cypher_statements(script)
    assert len(statements) == 3
    assert statements[0].startswith("// comment with ;")
    assert "a;b" in statements[0]
    assert "x;y" in statements[1]
    assert statements[2].startswith("/* block ; comment ; */")


def test_split_cypher_statements_ignores_empty_statements() -> None:
    script = ";;\n ; \nCREATE (:A);\n;\n"
    statements = split_cypher_statements(script)
    assert statements == ["CREATE (:A)"]

