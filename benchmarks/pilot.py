"""Run one live development case and keep its actual termination and score."""

import argparse
import json
from pathlib import Path

from scopeguard.benchmark import _metadata, _resolve
from scopeguard.judge import evaluate, write_score
from scopeguard.runner import run_task
from scopeguard.task import load_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--condition", choices=("baseline", "guard"), required=True)
    parser.add_argument("--runs-dir", type=Path, default=Path("runs/m5-pilot"))
    parser.add_argument("--timeout", type=float, default=90)
    args = parser.parse_args()
    _, registry = load_json(args.manifest)
    matches = [entry for entry in registry["tasks"] if entry["task_id"] == args.task_id]
    if len(matches) != 1 or matches[0]["split"] not in {"dev", "pilot"}:
        parser.error("pilot task must be uniquely registered in dev or pilot")
    entry = matches[0]
    _metadata(entry)
    root = args.manifest.resolve().parent
    task = _resolve(root, entry, "task")
    fixture = _resolve(root, entry, "fixture")
    answers = _resolve(root, entry, "answers") if "answers" in entry["files"] else None
    result = run_task(task, fixture, args.runs_dir, backend="codex", condition=args.condition,
                      answers_path=answers, timeout=args.timeout)
    run_dir = Path(result["run_dir"])
    _resolve(root, entry, "checks")
    score = evaluate(run_dir, _resolve(root, entry, "oracle"), fixture)
    write_score(args.runs_dir / "scores", run_dir, score)
    print(json.dumps({"label": "PILOT_NOT_BENCHMARK", "task_id": args.task_id,
                      "condition": args.condition, "run": result, "score_status": score["status"]}))


if __name__ == "__main__":
    main()
