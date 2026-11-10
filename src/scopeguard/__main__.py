"""Command line entry point for ScopeGuard."""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from .runner import run_task
from .workspace import CONDITIONS


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scopeguard")
    commands = parser.add_subparsers(dest="mode", required=True)
    commands.add_parser("mock", help="Run the offline M0 smoke check.")
    run = commands.add_parser("run", help="Run a public TaskSpec in a temporary fixture workspace.")
    run.add_argument("--backend", choices=("mock", "codex"), required=True)
    run.add_argument("--condition", choices=CONDITIONS, default="baseline")
    run.add_argument("--task", type=Path, required=True)
    run.add_argument("--fixture", type=Path, required=True)
    run.add_argument("--script", type=Path)
    run.add_argument("--runs-dir", type=Path, default=Path("runs"))
    run.add_argument("--timeout", type=float, default=90)
    judge = commands.add_parser("judge", help="Score a saved run using a separate private Oracle.")
    judge.add_argument("--run-dir", type=Path, required=True)
    judge.add_argument("--oracle", type=Path, required=True)
    judge.add_argument("--fixture", type=Path, required=True)
    judge.add_argument("--output", type=Path)
    options = parser.parse_args(argv)
    if options.mode == "mock":
        print(json.dumps({"milestone": "M0", "mode": "mock", "live_model_called": False}))
        return 0
    if options.mode == "judge":
        from .judge import evaluate, score_json, write_score

        score = evaluate(options.run_dir, options.oracle, options.fixture)
        if options.output is not None:
            try:
                write_score(
                    options.output, options.run_dir, score,
                    inputs=(options.oracle, options.oracle.with_name("checks.json"), options.fixture),
                )
            except (OSError, ValueError, RuntimeError):
                print("could not write the score to a separate output directory", file=sys.stderr)
                return 2
        print(score_json(score), end="")
        return 2 if score["status"] == "infra_error" else 0
    try:
        result = run_task(
            options.task, options.fixture, options.runs_dir,
            backend=options.backend, script_path=options.script, timeout=options.timeout, condition=options.condition,
        )
    except (OSError, ValueError, RecursionError) as exc:
        print(json.dumps({"status": "invalid_input", "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result))
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
