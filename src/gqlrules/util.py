from __future__ import annotations

from typing import Any, Protocol


class ScriptExecutor(Protocol):
    def execute(self, cypher: str) -> dict[str, Any]:
        raise NotImplementedError


def split_cypher_statements(script: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []

    in_single = False
    in_double = False
    in_backtick = False
    in_line_comment = False
    in_block_comment = False
    escaped = False

    i = 0
    while i < len(script):
        ch = script[i]
        nxt = script[i + 1] if i + 1 < len(script) else ""

        if in_line_comment:
            current.append(ch)
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue

        if in_block_comment:
            current.append(ch)
            if ch == "*" and nxt == "/":
                current.append(nxt)
                i += 2
                in_block_comment = False
                continue
            i += 1
            continue

        if in_single:
            current.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == "'":
                in_single = False
            i += 1
            continue

        if in_double:
            current.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_double = False
            i += 1
            continue

        if in_backtick:
            current.append(ch)
            if ch == "`":
                in_backtick = False
            i += 1
            continue

        if ch == "/" and nxt == "/":
            current.append(ch)
            current.append(nxt)
            in_line_comment = True
            i += 2
            continue

        if ch == "/" and nxt == "*":
            current.append(ch)
            current.append(nxt)
            in_block_comment = True
            i += 2
            continue

        if ch == "'":
            current.append(ch)
            in_single = True
            i += 1
            continue

        if ch == '"':
            current.append(ch)
            in_double = True
            i += 1
            continue

        if ch == "`":
            current.append(ch)
            in_backtick = True
            i += 1
            continue

        if ch == ";":
            _append_statement(statements, "".join(current))
            current = []
            i += 1
            continue

        current.append(ch)
        i += 1

    _append_statement(statements, "".join(current))
    return statements


def execute_cypher_script(executor: ScriptExecutor, script: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for statement in split_cypher_statements(script):
        row = executor.execute(statement)
        results.append(row)
    return results


def _append_statement(target: list[str], statement: str) -> None:
    normalized = statement.strip()
    if normalized:
        target.append(normalized)

