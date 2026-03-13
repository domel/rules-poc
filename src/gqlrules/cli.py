from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict

from .compiler import compile_program, compile_to_directory
from .demo import run_demo
from .metrics import write_report_csv, write_report_json
from .parser import ParseError, parse_file
from .runner import RunnerError, run_fixpoint

DEFAULT_NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
DEFAULT_NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
DEFAULT_NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "domeldomel")
DEFAULT_NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gqlr", description="GQL Rules wrapper-only parser")
    sub = parser.add_subparsers(dest="command", required=True)

    parse_cmd = sub.add_parser("parse", help="Parse .gqlr and print AST as JSON")
    parse_cmd.add_argument("program", help="Path to .gqlr file")
    parse_cmd.add_argument("--indent", type=int, default=2, help="JSON indentation (default: 2)")

    compile_cmd = sub.add_parser("compile", help="Compile .gqlr into sorted .cypher files + manifest")
    compile_cmd.add_argument("program", help="Path to .gqlr file")
    compile_cmd.add_argument("--out", default="out", help="Output directory (default: out)")
    compile_cmd.add_argument("--print-json", action="store_true", help="Print compiled rules as JSON")
    compile_cmd.add_argument("--indent", type=int, default=2, help="JSON indentation (default: 2)")

    run_cmd = sub.add_parser("run", help="Run rules to fixpoint and write execution report")
    run_cmd.add_argument("program", help="Path to .gqlr file")
    run_cmd.add_argument("--uri", default=DEFAULT_NEO4J_URI)
    run_cmd.add_argument("--user", default=DEFAULT_NEO4J_USER)
    run_cmd.add_argument("--password", default=DEFAULT_NEO4J_PASSWORD)
    run_cmd.add_argument("--database", default=DEFAULT_NEO4J_DATABASE)
    run_cmd.add_argument("--max-rounds", type=int, default=50)
    run_cmd.add_argument("--shuffle", action="store_true")
    run_cmd.add_argument("--seed", type=int)
    run_cmd.add_argument("--reports-dir", default="reports")
    run_cmd.add_argument("--csv", action="store_true", help="Also write per-rule CSV report")

    demo_cmd = sub.add_parser("demo", help="Run bundled demo scenario")
    demo_cmd.add_argument("name", help="Demo name (directory inside --examples-dir)")
    demo_cmd.add_argument("--examples-dir", default="examples")
    demo_cmd.add_argument("--uri", default=DEFAULT_NEO4J_URI)
    demo_cmd.add_argument("--user", default=DEFAULT_NEO4J_USER)
    demo_cmd.add_argument("--password", default=DEFAULT_NEO4J_PASSWORD)
    demo_cmd.add_argument("--database", default=DEFAULT_NEO4J_DATABASE)
    demo_cmd.add_argument("--max-rounds", type=int, default=50)
    demo_cmd.add_argument("--shuffle", action="store_true")
    demo_cmd.add_argument("--seed", type=int)
    demo_cmd.add_argument("--reports-dir", default="reports")
    demo_cmd.add_argument("--csv", action="store_true", help="Also write per-rule CSV report")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "parse":
        try:
            program = parse_file(args.program)
        except ParseError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(json.dumps(asdict(program), ensure_ascii=False, indent=args.indent))
        return 0
    if args.command == "compile":
        try:
            program = parse_file(args.program)
        except ParseError as exc:
            print(str(exc), file=sys.stderr)
            return 2

        artifacts = compile_to_directory(program, out_dir=args.out, source_path=args.program)
        if args.print_json:
            compiled_rules = compile_program(program)
            print(
                json.dumps(
                    [asdict(rule) for rule in compiled_rules],
                    ensure_ascii=False,
                    indent=args.indent,
                )
            )
        print(f"compiled_rules_dir={artifacts.rules_dir}")
        print(f"manifest={artifacts.manifest_path}")
        return 0
    if args.command == "run":
        try:
            program = parse_file(args.program)
        except ParseError as exc:
            print(str(exc), file=sys.stderr)
            return 2

        try:
            report = run_fixpoint(
                program,
                uri=args.uri,
                user=args.user,
                password=args.password,
                database=args.database,
                max_rounds=args.max_rounds,
                shuffle=args.shuffle,
                seed=args.seed,
            )
            report_path = write_report_json(report, args.reports_dir)
            csv_path = write_report_csv(report, args.reports_dir) if args.csv else None
            print(f"run_id={report.run_id}")
            print(f"fixpoint_reached={str(report.fixpoint_reached).lower()}")
            print(f"rounds={report.total_rounds}")
            print(f"termination={report.termination_reason}")
            print(f"report={report_path}")
            if csv_path:
                print(f"report_csv={csv_path}")
            return 0
        except RunnerError as exc:
            partial_report_path = None
            if exc.report is not None:
                partial_report_path = write_report_json(exc.report, args.reports_dir)
            print(str(exc), file=sys.stderr)
            if partial_report_path is not None:
                print(f"partial_report={partial_report_path}", file=sys.stderr)
            return 3
    if args.command == "demo":
        try:
            result = run_demo(
                args.name,
                examples_dir=args.examples_dir,
                uri=args.uri,
                user=args.user,
                password=args.password,
                database=args.database,
                max_rounds=args.max_rounds,
                shuffle=args.shuffle,
                seed=args.seed,
                reports_dir=args.reports_dir,
                csv=args.csv,
            )
            print(f"demo={args.name}")
            print(f"run_id={result.report.run_id}")
            print(f"fixpoint_reached={str(result.report.fixpoint_reached).lower()}")
            print(f"rounds={result.report.total_rounds}")
            print(f"termination={result.report.termination_reason}")
            print(f"report={result.report_path}")
            if result.report_csv_path:
                print(f"report_csv={result.report_csv_path}")
            if result.executed_scripts:
                print("executed_scripts=" + ",".join(result.executed_scripts))
            if result.postconditions_results:
                print(
                    "postconditions="
                    + json.dumps([dict(row) for row in result.postconditions_results], ensure_ascii=False)
                )
            return 0
        except (ValueError, FileNotFoundError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        except RunnerError as exc:
            partial_report_path = None
            if exc.report is not None:
                partial_report_path = write_report_json(exc.report, args.reports_dir)
            print(str(exc), file=sys.stderr)
            if partial_report_path is not None:
                print(f"partial_report={partial_report_path}", file=sys.stderr)
            return 3

    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
