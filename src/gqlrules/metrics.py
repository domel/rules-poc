from __future__ import annotations

import csv
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RunConfig:
    uri: str
    database: str | None
    max_rounds: int
    shuffle: bool
    seed: int | None


@dataclass(frozen=True)
class RoundMetric:
    round_index: int
    total_changes: int
    time_ms: float


@dataclass(frozen=True)
class RuleRoundMetric:
    round_index: int
    rule_name: str
    mode: str
    changes: int
    time_ms: float
    error: str | None = None
    warning: str | None = None


@dataclass
class RunReport:
    run_id: str
    timestamp_start: str
    timestamp_end: str | None
    config: RunConfig
    program_hash: str
    manifest_hash: str | None = None
    rounds: list[RoundMetric] = field(default_factory=list)
    rule_rounds: list[RuleRoundMetric] = field(default_factory=list)
    total_rounds: int = 0
    total_changes: int = 0
    fixpoint_reached: bool = False
    termination_reason: str = "running"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def generate_run_id(now: datetime | None = None) -> str:
    instant = now or datetime.now(timezone.utc)
    return f"run_{instant.strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_report_json(report: RunReport, reports_dir: str | Path = "reports") -> Path:
    base = Path(reports_dir)
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{report.run_id}.json"
    path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def write_report_csv(report: RunReport, reports_dir: str | Path = "reports") -> Path:
    base = Path(reports_dir)
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{report.run_id}.csv"

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["round_index", "rule_name", "mode", "changes", "time_ms", "error", "warning"])
        for metric in report.rule_rounds:
            writer.writerow(
                [
                    metric.round_index,
                    metric.rule_name,
                    metric.mode,
                    metric.changes,
                    f"{metric.time_ms:.3f}",
                    metric.error or "",
                    metric.warning or "",
                ]
            )
    return path

