from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

RuleMode = Literal["LOG", "IGNORE", "STRICT"]


@dataclass(frozen=True)
class Rule:
    name: str
    mode: RuleMode
    body: str
    head: str
    tags: tuple[str, ...] = ()
    priority: int = 0
    stratum: int = 0
    declarations: tuple[str, ...] = ()
    line: int = 0


@dataclass(frozen=True)
class Program:
    rules: tuple[Rule, ...]
    program_name: str | None = None
    imports: tuple[str, ...] = ()
    declarations: tuple[str, ...] = ()
    settings: dict[str, Any] = field(default_factory=dict)

