from __future__ import annotations

import random
import time
from dataclasses import asdict
from typing import Any, Protocol

from .compiler import CompiledRule, compile_program, compute_program_hash
from .metrics import (
    RoundMetric,
    RuleRoundMetric,
    RunConfig,
    RunReport,
    generate_run_id,
    utc_now_iso,
)
from .model import Program


class QueryExecutor(Protocol):
    def execute(self, cypher: str) -> dict[str, Any]:
        raise NotImplementedError

    def close(self) -> None:  # pragma: no cover - optional in tests
        raise NotImplementedError


class RunnerError(RuntimeError):
    def __init__(self, message: str, *, report: RunReport | None = None) -> None:
        super().__init__(message)
        self.report = report


class Neo4jExecutor:
    def __init__(self, *, uri: str, user: str, password: str, database: str | None = None) -> None:
        try:
            from neo4j import GraphDatabase
        except ModuleNotFoundError as exc:  # pragma: no cover - integration path
            raise RunnerError(
                "neo4j driver is not installed; install dependency 'neo4j' to run against database"
            ) from exc

        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        self._database = database

    def execute(self, cypher: str) -> dict[str, Any]:
        with self._driver.session(database=self._database) as session:
            result = session.run(cypher)
            try:
                record = result.single()
            except TypeError:
                record = result.single(strict=False)
            if record is None:
                return {}
            return dict(record.items())

    def close(self) -> None:  # pragma: no cover - integration path
        self._driver.close()


class _MissingChangesError(ValueError):
    pass


def run_fixpoint(
    program: Program,
    *,
    uri: str = "bolt://localhost:7687",
    user: str = "neo4j",
    password: str | None = "domeldomel",
    database: str | None = "neo4j",
    max_rounds: int = 50,
    shuffle: bool = False,
    seed: int | None = None,
    executor: QueryExecutor | None = None,
) -> RunReport:
    if max_rounds <= 0:
        raise ValueError("max_rounds must be > 0")

    close_executor = False
    if executor is None:
        if not password:
            raise RunnerError("password is required unless a custom executor is provided")
        executor = Neo4jExecutor(uri=uri, user=user, password=password, database=database)
        close_executor = True

    config = RunConfig(uri=uri, database=database, max_rounds=max_rounds, shuffle=shuffle, seed=seed)
    report = RunReport(
        run_id=generate_run_id(),
        timestamp_start=utc_now_iso(),
        timestamp_end=None,
        config=config,
        program_hash=compute_program_hash(program),
        manifest_hash=None,
    )

    compiled_rules = compile_program(program)
    rng = random.Random(seed)

    try:
        for round_index in range(1, max_rounds + 1):
            round_start = time.perf_counter()
            total_changes_in_round = 0

            for rule in _rules_for_round(compiled_rules, shuffle=shuffle, rng=rng):
                one_rule_start = time.perf_counter()
                error: str | None = None
                warning: str | None = None
                changes = 0

                try:
                    row = executor.execute(rule.cypher)
                    changes = _extract_changes(row)
                except _MissingChangesError as exc:
                    warning = str(exc)
                    if rule.mode == "STRICT":
                        metric = RuleRoundMetric(
                            round_index=round_index,
                            rule_name=rule.name,
                            mode=rule.mode,
                            changes=0,
                            time_ms=_elapsed_ms(one_rule_start),
                            error=warning,
                            warning=None,
                        )
                        report.rule_rounds.append(metric)
                        report.rounds.append(
                            RoundMetric(
                                round_index=round_index,
                                total_changes=total_changes_in_round,
                                time_ms=_elapsed_ms(round_start),
                            )
                        )
                        report.total_rounds = round_index
                        report.total_changes += total_changes_in_round
                        report.fixpoint_reached = False
                        report.termination_reason = "strict_error"
                        report.timestamp_end = utc_now_iso()
                        raise RunnerError(
                            f"STRICT rule '{rule.name}' did not return required 'changes' field",
                            report=report,
                        ) from exc
                    changes = 0
                except Exception as exc:
                    error = str(exc)
                    if rule.mode == "STRICT":
                        metric = RuleRoundMetric(
                            round_index=round_index,
                            rule_name=rule.name,
                            mode=rule.mode,
                            changes=0,
                            time_ms=_elapsed_ms(one_rule_start),
                            error=error,
                            warning=None,
                        )
                        report.rule_rounds.append(metric)
                        report.rounds.append(
                            RoundMetric(
                                round_index=round_index,
                                total_changes=total_changes_in_round,
                                time_ms=_elapsed_ms(round_start),
                            )
                        )
                        report.total_rounds = round_index
                        report.total_changes += total_changes_in_round
                        report.fixpoint_reached = False
                        report.termination_reason = "strict_error"
                        report.timestamp_end = utc_now_iso()
                        raise RunnerError(f"STRICT rule '{rule.name}' failed: {error}", report=report) from exc
                    changes = 0

                total_changes_in_round += changes
                report.rule_rounds.append(
                    RuleRoundMetric(
                        round_index=round_index,
                        rule_name=rule.name,
                        mode=rule.mode,
                        changes=changes,
                        time_ms=_elapsed_ms(one_rule_start),
                        error=error,
                        warning=warning,
                    )
                )

            report.rounds.append(
                RoundMetric(
                    round_index=round_index,
                    total_changes=total_changes_in_round,
                    time_ms=_elapsed_ms(round_start),
                )
            )
            report.total_rounds = round_index
            report.total_changes += total_changes_in_round

            if total_changes_in_round == 0:
                report.fixpoint_reached = True
                report.termination_reason = "fixpoint"
                break

        if report.termination_reason == "running":
            report.fixpoint_reached = False
            report.termination_reason = "max_rounds"
    finally:
        report.timestamp_end = report.timestamp_end or utc_now_iso()
        if close_executor:
            close_fn = getattr(executor, "close", None)
            if callable(close_fn):
                close_fn()

    return report


def report_to_jsonable(report: RunReport) -> dict[str, Any]:
    return asdict(report)


def _extract_changes(row: dict[str, Any]) -> int:
    if "changes" not in row:
        raise _MissingChangesError("missing 'changes' field in query result")
    value = row["changes"]

    if isinstance(value, bool):
        raise _MissingChangesError("'changes' must be numeric, got boolean")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    raise _MissingChangesError(f"'changes' must be an integer-compatible value, got: {type(value).__name__}")


def _rules_for_round(
    compiled_rules: tuple[CompiledRule, ...],
    *,
    shuffle: bool,
    rng: random.Random,
) -> list[CompiledRule]:
    if not shuffle:
        return list(compiled_rules)

    by_stratum: dict[int, list[CompiledRule]] = {}
    for rule in compiled_rules:
        by_stratum.setdefault(rule.stratum, []).append(rule)

    ordered: list[CompiledRule] = []
    for stratum in sorted(by_stratum):
        group = list(by_stratum[stratum])
        rng.shuffle(group)
        ordered.extend(group)
    return ordered


def _elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000.0, 3)
