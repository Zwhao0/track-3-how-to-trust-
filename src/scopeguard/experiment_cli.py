"""Offline preparation and gated formal experiment commands."""

import json
import subprocess
from pathlib import Path

from .experiment_plan import REPO_ROOT, preflight, write_plan


def register(commands):
    experiment = commands.add_parser("experiment", help="Plan, verify, and analyze a pinned batch.")
    modes = experiment.add_subparsers(dest="experiment_mode", required=True)
    plan = modes.add_parser("plan", help="Write a deterministic, unsigned review packet.")
    plan.add_argument("--manifest", type=Path, required=True)
    plan.add_argument("--output", type=Path, required=True)
    for operation in ("preflight", "run"):
        mode = modes.add_parser(operation)
        mode.add_argument("--manifest", type=Path, required=True)
        mode.add_argument("--packet", type=Path, required=True)
        mode.add_argument("--approval", type=Path)
        if operation == "run":
            mode.add_argument("--confirm", help="Repeat the signed batch ID to explicitly start or resume it.")
    score = modes.add_parser("score", help="Independently verify recorded scores without writing.")
    score.add_argument("--batch", type=Path, required=True)
    score.add_argument("--manifest", type=Path, required=True)
    summary = modes.add_parser("summarize")
    summary.add_argument("--batch", type=Path, required=True)
    summary.add_argument("--output", type=Path, required=True)


def dispatch(options) -> int:
    mode = options.experiment_mode
    try:
        if mode == "plan":
            config = write_plan(options.output, options.manifest)
            result = {"status": "FORMAL_RUN_BLOCKED", "planned_slots": config["planned_slots"],
                      "schedule_sha256": config["schedule_sha256"]}
        elif mode in ("preflight", "run"):
            schedule, config, freeze = preflight(options.manifest, options.packet, options.approval)
            result = {"status": "verified", "batch_id": freeze["batch_id"]}
            if mode == "run":
                if options.confirm != freeze["batch_id"]:
                    raise ValueError("FORMAL_RUN_BLOCKED: explicit batch confirmation required")
                from .experiment_batch import attempt_executor, open_batch

                root = REPO_ROOT / "experiments" / freeze["batch_id"]
                batch = open_batch(root, schedule, config, freeze, attempt_executor(options.manifest, config))
                result.update(status=batch.stop or batch.pause or "completed", not_run=batch.remaining())
        else:
            from .experiment_batch import read_batch, score_batch

            batch = read_batch(options.batch)
            if mode == "score":
                result = {"verified": score_batch(batch, options.manifest)}
            else:
                from .experiment_analysis import summarize, write_summary

                if options.output.resolve().is_relative_to(options.batch.resolve()):
                    raise ValueError("summary output must be outside the sealed batch")
                report = summarize(batch.schedule, batch.primary(), seed=batch.config["seed"])
                write_summary(options.output, report)
                result = {"status": "summarized", "output": str(options.output), "planned_slots": len(batch.schedule)}
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        result = {"status": "FORMAL_RUN_BLOCKED" if mode in ("preflight", "run") else "invalid",
                  "error": str(error)}
        print(json.dumps(result))
        return 2
    print(json.dumps(result))
    return 0
