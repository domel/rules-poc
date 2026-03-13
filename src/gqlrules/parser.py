from __future__ import annotations

import bisect
import re
from pathlib import Path
from typing import Any

from .model import Program, Rule, RuleMode

_MODE_VALUES: set[str] = {"LOG", "IGNORE", "STRICT"}

_COMMENT_RE = re.compile(r"^\s*(#|//)")
_PROGRAM_RE = re.compile(r"^\s*PROGRAM\s+([A-Za-z_][A-Za-z0-9_]*)\s*;?\s*$")
_IMPORT_RE = re.compile(r"^\s*IMPORT\s+(.+?)\s*;?\s*$")
_DECLARE_RE = re.compile(r"^\s*DECLARE\b(.*)$")
_RULE_HEADER_RE = re.compile(
    r"^\s*RULE\s+([A-Za-z_][A-Za-z0-9_]*)\s+MODE\s+(LOG|IGNORE|STRICT)\b(.*)$",
    flags=re.DOTALL,
)
_HEADER_EXTRA_RE = re.compile(
    r"(PRIORITY|STRATUM)\s*:?\s*(-?\d+)",
    flags=re.IGNORECASE,
)
_PRIORITY_RE = re.compile(r"^\s*PRIORITY\s*:?\s*(-?\d+)\s*$")
_STRATUM_RE = re.compile(r"^\s*STRATUM\s*:?\s*(-?\d+)\s*$")
_TAGS_RE = re.compile(r"^\s*TAGS\s*:\s*(.*?)\s*$")
_BODY_RE = re.compile(r"^\s*BODY\s*:\s*$")
_HEAD_RE = re.compile(r"^\s*HEAD\s*:\s*$")
_SETTING_LINE_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_.-]*)\s*[:=]\s*(.*?)\s*[,;]?\s*$")


class ParseError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        line: int | None = None,
        column: int | None = None,
        source_name: str = "<string>",
    ) -> None:
        if line is not None:
            if column is None:
                location = f"{source_name}:{line}"
            else:
                location = f"{source_name}:{line}:{column}"
            message = f"{location}: {message}"
        super().__init__(message)
        self.line = line
        self.column = column
        self.source_name = source_name


def parse_file(path: str | Path) -> Program:
    file_path = Path(path)
    return parse_program(file_path.read_text(encoding="utf-8"), source_name=str(file_path))


def parse_program(source: str, *, source_name: str = "<string>") -> Program:
    lines = source.splitlines(keepends=True)
    if not lines and source == "":
        return Program(rules=())

    line_offsets = _line_offsets(lines)
    i = 0

    program_name: str | None = None
    imports: list[str] = []
    declarations: list[str] = []
    settings: dict[str, Any] = {}
    rules: list[Rule] = []

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        line_no = i + 1

        if _is_ignorable_top_level(stripped):
            i += 1
            continue

        program_match = _PROGRAM_RE.match(line)
        if program_match:
            if program_name is not None:
                raise ParseError("duplicate PROGRAM declaration", line=line_no, source_name=source_name)
            program_name = program_match.group(1)
            i += 1
            continue

        import_match = _IMPORT_RE.match(line)
        if import_match:
            imports.append(_strip_quotes(_strip_optional_semicolon(import_match.group(1).strip())))
            i += 1
            continue

        declare_match = _DECLARE_RE.match(line)
        if declare_match:
            payload = _strip_optional_semicolon(declare_match.group(1).strip())
            if not payload:
                raise ParseError("empty DECLARE statement", line=line_no, source_name=source_name)
            declarations.append(payload)
            i += 1
            continue

        if line.lstrip().startswith("SETTINGS"):
            consumed, parsed = _parse_settings(
                source=source,
                lines=lines,
                line_offsets=line_offsets,
                start_line=i,
                source_name=source_name,
            )
            overlap = set(settings).intersection(parsed)
            if overlap:
                duplicated = ", ".join(sorted(overlap))
                raise ParseError(
                    f"duplicate settings key(s): {duplicated}",
                    line=line_no,
                    source_name=source_name,
                )
            settings.update(parsed)
            i = consumed
            continue

        if line.lstrip().startswith("RULE"):
            consumed, rule = _parse_rule(
                source=source,
                lines=lines,
                line_offsets=line_offsets,
                start_line=i,
                source_name=source_name,
            )
            rules.append(rule)
            i = consumed
            continue

        raise ParseError(
            f"unknown top-level statement: {stripped}",
            line=line_no,
            source_name=source_name,
        )

    return Program(
        rules=tuple(rules),
        program_name=program_name,
        imports=tuple(imports),
        declarations=tuple(declarations),
        settings=settings,
    )


def _parse_rule(
    *,
    source: str,
    lines: list[str],
    line_offsets: list[int],
    start_line: int,
    source_name: str,
) -> tuple[int, Rule]:
    start_offset = line_offsets[start_line]
    open_offset = source.find("{", start_offset)
    if open_offset == -1:
        raise ParseError("RULE missing opening '{'", line=start_line + 1, source_name=source_name)

    header_text = source[start_offset:open_offset]
    header_match = _RULE_HEADER_RE.match(header_text)
    if not header_match:
        raise ParseError(
            "invalid RULE header; expected: RULE <name> MODE <LOG|IGNORE|STRICT>",
            line=start_line + 1,
            source_name=source_name,
        )

    rule_name = header_match.group(1)
    mode = header_match.group(2).upper()
    if mode not in _MODE_VALUES:
        raise ParseError(f"unsupported MODE value: {mode}", line=start_line + 1, source_name=source_name)

    header_priority, header_stratum = _parse_header_extras(
        header_match.group(3),
        line=start_line + 1,
        source_name=source_name,
    )

    close_offset = _find_matching_brace(
        source=source,
        open_offset=open_offset,
        line_offsets=line_offsets,
        source_name=source_name,
    )
    close_line = _offset_to_line(line_offsets, close_offset)
    close_col = close_offset - line_offsets[close_line] + 1

    trailing = lines[close_line][close_col:].strip()
    if trailing and not re.match(r"^;?\s*(//.*|#.*)?$", trailing):
        raise ParseError(
            "unexpected text after rule closing brace",
            line=close_line + 1,
            column=close_col + 1,
            source_name=source_name,
        )

    inner = source[open_offset + 1 : close_offset]
    rule = _parse_rule_block(
        inner,
        name=rule_name,
        mode=mode,  # type: ignore[arg-type]
        header_priority=header_priority,
        header_stratum=header_stratum,
        block_start_line=_offset_to_line(line_offsets, open_offset) + 1,
        source_name=source_name,
    )

    consumed = close_line + 1
    return consumed, rule


def _parse_rule_block(
    block: str,
    *,
    name: str,
    mode: RuleMode,
    header_priority: int | None,
    header_stratum: int | None,
    block_start_line: int,
    source_name: str,
) -> Rule:
    lines = block.splitlines(keepends=True)
    offsets = _line_offsets(lines)

    priority = 0 if header_priority is None else header_priority
    stratum = 0 if header_stratum is None else header_stratum
    priority_seen = header_priority is not None
    stratum_seen = header_stratum is not None
    tags: tuple[str, ...] = ()
    declarations: list[str] = []

    body_start: int | None = None
    body_end: int | None = None
    head_start: int | None = None
    state = "wrapper"

    for i, line in enumerate(lines):
        stripped = line.strip()
        line_no = block_start_line + i

        if state == "wrapper":
            if _is_ignorable_wrapper(stripped):
                continue

            prio_match = _PRIORITY_RE.match(line)
            if prio_match:
                if priority_seen:
                    raise ParseError(
                        f"duplicate PRIORITY in rule {name}",
                        line=line_no,
                        source_name=source_name,
                    )
                priority = int(prio_match.group(1))
                priority_seen = True
                continue

            stratum_match = _STRATUM_RE.match(line)
            if stratum_match:
                if stratum_seen:
                    raise ParseError(
                        f"duplicate STRATUM in rule {name}",
                        line=line_no,
                        source_name=source_name,
                    )
                stratum = int(stratum_match.group(1))
                stratum_seen = True
                continue

            tags_match = _TAGS_RE.match(line)
            if tags_match:
                tag_items = [part.strip() for part in tags_match.group(1).split(",") if part.strip()]
                tags = tuple(tag_items)
                continue

            declare_match = _DECLARE_RE.match(line)
            if declare_match:
                payload = _strip_optional_semicolon(declare_match.group(1).strip())
                if not payload:
                    raise ParseError(
                        f"empty DECLARE statement in rule {name}",
                        line=line_no,
                        source_name=source_name,
                    )
                declarations.append(payload)
                continue

            if _BODY_RE.match(line):
                body_start = offsets[i] + len(line)
                state = "body"
                continue

            if _HEAD_RE.match(line):
                raise ParseError(
                    f"rule {name} is missing BODY section",
                    line=line_no,
                    source_name=source_name,
                )

            raise ParseError(
                f"unsupported wrapper statement in rule {name}: {stripped}",
                line=line_no,
                source_name=source_name,
            )

        if state == "body":
            if _HEAD_RE.match(line):
                if body_start is None:
                    raise ParseError(
                        f"internal parser error while parsing BODY in rule {name}",
                        line=line_no,
                        source_name=source_name,
                    )
                body_end = offsets[i]
                head_start = offsets[i] + len(line)
                state = "head"
            continue

    if body_start is None:
        raise ParseError(f"rule {name} is missing BODY section", line=block_start_line, source_name=source_name)

    if head_start is None:
        missing_line = block_start_line + len(lines)
        raise ParseError(f"rule {name} is missing HEAD section", line=missing_line, source_name=source_name)

    if body_end is None:
        raise ParseError(
            f"internal parser error while finalizing BODY in rule {name}",
            line=block_start_line,
            source_name=source_name,
        )

    body = block[body_start:body_end]
    head = block[head_start:]

    if not body.strip():
        raise ParseError(
            f"rule {name} has empty BODY section",
            line=block_start_line,
            source_name=source_name,
        )

    if not head.strip():
        raise ParseError(
            f"rule {name} has empty HEAD section",
            line=block_start_line,
            source_name=source_name,
        )

    return Rule(
        name=name,
        mode=mode,
        body=body,
        head=head,
        tags=tags,
        priority=priority,
        stratum=stratum,
        declarations=tuple(declarations),
        line=block_start_line,
    )


def _parse_header_extras(extra: str, *, line: int, source_name: str) -> tuple[int | None, int | None]:
    priority: int | None = None
    stratum: int | None = None

    cursor = 0
    while cursor < len(extra):
        while cursor < len(extra) and extra[cursor].isspace():
            cursor += 1
        if cursor >= len(extra):
            break

        match = _HEADER_EXTRA_RE.match(extra, cursor)
        if not match:
            remaining = extra[cursor:].strip()
            raise ParseError(
                f"unsupported token in RULE header: {remaining}",
                line=line,
                source_name=source_name,
            )

        key = match.group(1).upper()
        value = int(match.group(2))
        if key == "PRIORITY":
            if priority is not None:
                raise ParseError("duplicate PRIORITY in RULE header", line=line, source_name=source_name)
            priority = value
        else:
            if stratum is not None:
                raise ParseError("duplicate STRATUM in RULE header", line=line, source_name=source_name)
            stratum = value

        cursor = match.end()

    return priority, stratum


def _parse_settings(
    *,
    source: str,
    lines: list[str],
    line_offsets: list[int],
    start_line: int,
    source_name: str,
) -> tuple[int, dict[str, Any]]:
    first_line = lines[start_line]
    start_offset = line_offsets[start_line]
    local_open = first_line.find("{")

    if local_open != -1:
        open_offset = start_offset + local_open
        close_offset = _find_matching_brace(
            source=source,
            open_offset=open_offset,
            line_offsets=line_offsets,
            source_name=source_name,
        )
        close_line = _offset_to_line(line_offsets, close_offset)
        close_col = close_offset - line_offsets[close_line] + 1
        trailing = lines[close_line][close_col:].strip()
        if trailing and not re.match(r"^;?\s*(//.*|#.*)?$", trailing):
            raise ParseError(
                "unexpected text after SETTINGS block",
                line=close_line + 1,
                column=close_col + 1,
                source_name=source_name,
            )
        block = source[open_offset + 1 : close_offset]
        return close_line + 1, _parse_settings_block(block, base_line=start_line + 1, source_name=source_name)

    match = re.match(r"^\s*SETTINGS\b(.*)$", first_line)
    if not match:
        raise ParseError("invalid SETTINGS declaration", line=start_line + 1, source_name=source_name)
    payload = _strip_optional_semicolon(match.group(1).strip())
    if payload.startswith(":"):
        payload = payload[1:].strip()
    if not payload:
        raise ParseError(
            "SETTINGS requires key=value pairs or a { ... } block",
            line=start_line + 1,
            source_name=source_name,
        )

    parsed = _parse_settings_block(payload, base_line=start_line + 1, source_name=source_name)
    return start_line + 1, parsed


def _parse_settings_block(block: str, *, base_line: int, source_name: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    lines = block.splitlines()
    if not lines:
        return result

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or _COMMENT_RE.match(stripped):
            continue

        match = _SETTING_LINE_RE.match(line)
        if not match:
            raise ParseError(
                f"invalid SETTINGS entry: {stripped}",
                line=base_line + idx,
                source_name=source_name,
            )

        key = match.group(1)
        value = _parse_setting_value(match.group(2))
        if key in result:
            raise ParseError(
                f"duplicate SETTINGS key: {key}",
                line=base_line + idx,
                source_name=source_name,
            )
        result[key] = value

    return result


def _parse_setting_value(value: str) -> Any:
    raw = value.strip()
    if not raw:
        return ""

    lower = raw.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False

    if re.fullmatch(r"-?\d+", raw):
        return int(raw)

    if re.fullmatch(r"-?\d+\.\d+", raw):
        return float(raw)

    return _strip_quotes(raw)


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _strip_optional_semicolon(value: str) -> str:
    return value[:-1].rstrip() if value.endswith(";") else value


def _find_matching_brace(
    *,
    source: str,
    open_offset: int,
    line_offsets: list[int],
    source_name: str,
) -> int:
    depth = 0
    in_single = False
    in_double = False
    in_comment = False
    escaped = False

    for pos in range(open_offset, len(source)):
        ch = source[pos]
        nxt = source[pos + 1] if pos + 1 < len(source) else ""

        if in_comment:
            if ch == "\n":
                in_comment = False
            continue

        if in_single:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == "'":
                in_single = False
            continue

        if in_double:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_double = False
            continue

        if ch == "#":
            in_comment = True
            continue

        if ch == "/" and nxt == "/":
            in_comment = True
            continue

        if ch == "'":
            in_single = True
            continue

        if ch == '"':
            in_double = True
            continue

        if ch == "{":
            depth += 1
            continue

        if ch == "}":
            depth -= 1
            if depth == 0:
                return pos
            if depth < 0:
                line = _offset_to_line(line_offsets, pos) + 1
                col = pos - line_offsets[line - 1] + 1
                raise ParseError("unexpected closing brace", line=line, column=col, source_name=source_name)

    line = _offset_to_line(line_offsets, open_offset) + 1
    raise ParseError("missing closing brace", line=line, source_name=source_name)


def _line_offsets(lines: list[str]) -> list[int]:
    offsets: list[int] = []
    acc = 0
    for line in lines:
        offsets.append(acc)
        acc += len(line)
    return offsets


def _offset_to_line(line_offsets: list[int], offset: int) -> int:
    if not line_offsets:
        return 0
    return max(0, bisect.bisect_right(line_offsets, offset) - 1)


def _is_ignorable_top_level(stripped: str) -> bool:
    if not stripped:
        return True
    if stripped == ";":
        return True
    return bool(_COMMENT_RE.match(stripped))


def _is_ignorable_wrapper(stripped: str) -> bool:
    if not stripped:
        return True
    return bool(_COMMENT_RE.match(stripped))
