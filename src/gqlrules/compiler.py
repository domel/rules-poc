from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from .model import Program, RuleMode


@dataclass(frozen=True)
class CompiledRule:
    name: str
    mode: RuleMode
    cypher: str
    priority: int
    stratum: int
    source_line: int = 0


@dataclass(frozen=True)
class CompilationArtifacts:
    program_dir: Path
    rules_dir: Path
    manifest_path: Path


def compile_program(program: Program) -> tuple[CompiledRule, ...]:
    compiled: list[CompiledRule] = []
    for rule in program.rules:
        compiled.append(
            CompiledRule(
                name=rule.name,
                mode=rule.mode,
                cypher=compose_cypher(rule.body, rule.head),
                priority=rule.priority,
                stratum=rule.stratum,
                source_line=rule.line,
            )
        )
    return tuple(sorted(compiled, key=lambda rule: (rule.stratum, rule.priority, rule.name)))


def compose_cypher(body: str, head: str) -> str:
    return body + "\n" + head


def compile_to_directory(
    program: Program,
    *,
    out_dir: str | Path,
    source_path: str | Path | None = None,
) -> CompilationArtifacts:
    compiled = compile_program(program)
    output_base = Path(out_dir)
    program_name = _program_name(program, source_path)
    program_dir = output_base / _sanitize_filename(program_name)
    rules_dir = program_dir / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)

    rule_entries: list[dict[str, object]] = []
    for idx, rule in enumerate(compiled, start=1):
        file_name = f"{idx:02d}_{_sanitize_filename(rule.name)}.cypher"
        file_path = rules_dir / file_name
        file_path.write_text(rule.cypher, encoding="utf-8")
        rule_entries.append(
            {
                "index": idx,
                "name": rule.name,
                "mode": rule.mode,
                "stratum": rule.stratum,
                "priority": rule.priority,
                "source_line": rule.source_line,
                "file": f"rules/{file_name}",
                "cypher_sha256": hashlib.sha256(rule.cypher.encode("utf-8")).hexdigest(),
            }
        )

    manifest = {
        "program_name": program_name,
        "program_hash": compute_program_hash(program),
        "compiled_hash": compute_compiled_hash(compiled),
        "rule_count": len(compiled),
        "rules": rule_entries,
    }

    manifest_path = program_dir / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return CompilationArtifacts(program_dir=program_dir, rules_dir=rules_dir, manifest_path=manifest_path)


def compute_program_hash(program: Program) -> str:
    payload = json.dumps(asdict(program), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_compiled_hash(compiled_rules: tuple[CompiledRule, ...]) -> str:
    payload = json.dumps(
        [asdict(rule) for rule in compiled_rules],
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _program_name(program: Program, source_path: str | Path | None) -> str:
    if program.program_name:
        return program.program_name
    if source_path is not None:
        return Path(source_path).stem
    return "program"


def _sanitize_filename(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return sanitized or "item"

