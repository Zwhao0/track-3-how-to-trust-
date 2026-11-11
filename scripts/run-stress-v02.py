"""Run the registered exploratory task set with the existing Codex runner and Judge."""

import json
from hashlib import sha256
from pathlib import Path
import sys

from scopeguard.arms import ARMS
from scopeguard.benchmark import _resolve, validate_manifest
from scopeguard.experiment_analysis import summarize, write_summary
from scopeguard.experiment_batch import open_batch
from scopeguard.experiment_plan import canonical, client_identity, immutable
from scopeguard.judge import evaluate
from scopeguard.runner import run_task

ROOT = Path(__file__).resolve().parents[1]
STRESS = ROOT / "benchmarks/stress-v0.2"
MANIFEST = STRESS / "manifest.json"
REGISTRATION = STRESS / "registration.json"


def main():
    if sys.argv[1:] != ["--run-registered"]:
        raise SystemExit("Usage: python scripts/run-stress-v02.py --run-registered")
    registration = json.loads(REGISTRATION.read_bytes())
    manifest_bytes = MANIFEST.read_bytes()
    if sha256(manifest_bytes).hexdigest() != registration["manifest_sha256"]:
        raise SystemExit("Exploratory manifest differs from its registration")
    if client_identity(signed_in=True) != registration["client"]:
        raise SystemExit("Codex client differs from its registration")
    if not validate_manifest(MANIFEST, prototype=True)["ok"]:
        raise SystemExit("Exploratory fixture validation failed")
    entries = {entry["task_id"]: entry for entry in json.loads(manifest_bytes)["tasks"]}
    schedule = registration["schedule"]
    by_arm = {arm: condition for condition, arm in ARMS.items()}
    if {entry["split"] for entry in entries.values()} != {"dev"} or (
        len(schedule) != len(entries) * len(by_arm)
        or {(slot["task_id"], slot["arm"]) for slot in schedule}
        != {(task_id, arm) for task_id in entries for arm in by_arm}
    ):
        raise SystemExit("Exploratory schedule must contain one slot per development task and arm")
    output = ROOT / "runs" / "stress-v02-results"
    if output.exists():
        raise SystemExit("Results already exist at the registered output path")

    def execute(slot, directory):
        entry = entries[slot["task_id"]]
        files = {name: _resolve(STRESS, entry, name) for name in entry["files"]}
        result = run_task(
            files["task"], files["fixture"], directory, backend="codex",
            condition=by_arm[slot["arm"]], timeout=registration["timeout_seconds"],
            answers_path=files.get("answers"),
        )
        run_dir = Path(result["run_dir"])
        score = evaluate(run_dir, files["oracle"], files["fixture"])
        immutable(directory / "score.json", score)
        trace = [json.loads(line) for line in (run_dir / "trace.jsonl").read_bytes().splitlines()]
        return {
            "status": "infra_error" if score["status"] == "infra_error" else result["status"],
            "score": score, "usage": result.get("usage"), "elapsed_seconds": result["elapsed_seconds"],
            "asks": [row["arguments"]["question_id"] for row in trace if row["event"] == "tool_call"
                     and row["tool"] == "ask_user" and isinstance(row["arguments"].get("question_id"), str)],
            "answered_questions": [row["question_id"] for row in trace if row["event"] == "authorization_updated"],
            "retryable": False, "run_name": run_dir.name, "error": result.get("error"),
        }

    ledger = ROOT / "runs" / "stress-v02-batch"
    batch = open_batch(ledger, schedule, registration, {
        "status": "exploratory_preregistered",
        "registration_sha256": sha256(REGISTRATION.read_bytes()).hexdigest(),
    }, execute)
    summary = summarize(schedule, batch.primary(), seed=registration["seed"])
    write_summary(output, summary)
    immutable(output / "observation.json", {
        "status": batch.stop or batch.pause or "completed", "planned": len(schedule),
        "executed": len(batch.attempts), "unperformed": batch.remaining(),
        "journal_sha256": batch.head, "analysis_sha256": sha256(canonical(summary)).hexdigest(),
    })
    print((output / "observation.json").read_text(), end="")


if __name__ == "__main__":
    main()
