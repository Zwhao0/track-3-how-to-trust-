"""Re-run the classroom interventions through the real offline Mock harness."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from scopeguard.judge import evaluate
from scopeguard.runner import run_task

ROOT = Path(__file__).resolve().parents[1]
CASES = {
    "legal-multi-file": "shipment-webhook-clear",
    "clarify-before-write": "invoice-delivery-ambiguous",
    "same-file-field": "stress-session-single-field",
}


def write(path, text):
    return {"tool": "replace_file", "arguments": {"path": path, "content": text}}


def replay(case, task_id, directory):
    if case == "same-file-field":
        benchmark, split = ROOT / "benchmarks/stress-v0.2", "dev"
    else:
        benchmark, split = ROOT / "benchmarks", "eval"
    public = benchmark / split / task_id
    private = benchmark / "private" / split / task_id
    fixture = public / "fixture.json"
    controls = json.loads((private / "controls.json").read_bytes())
    actions = [write(path, text) for path, text in controls["positive"].items()]
    answers = None
    if case == "clarify-before-write":
        decoy = controls["decoy_path"]
        config = json.loads(json.loads(fixture.read_bytes())[decoy])
        config["max_attempts"] = 5
        actions[:0] = [
            write(decoy, json.dumps(config, indent=2, sort_keys=True) + "\n"),
            {"tool": "ask_user", "arguments": {"question_id": "target"}},
        ]
        answers = private / "answers.json"
    if case == "same-file-field":
        (path, content), = controls["positive"].items()
        edited = json.loads(content)
        edited["refresh"]["idle_minutes"] = edited["browser"]["idle_minutes"]
        actions = [write(path, json.dumps(edited, indent=2, sort_keys=True) + "\n")]
    script = directory / "actions.json"
    script.write_text(json.dumps(actions))
    runs = {}
    for arm, condition in (("B0", "baseline"), ("B2", "guard")):
        result = run_task(public / "task.json", fixture, directory, backend="mock",
                          condition=condition, script_path=script, answers_path=answers)
        run_dir = Path(result["run_dir"])
        score = evaluate(run_dir, private / "oracle.json", fixture)
        records = [json.loads(row) for row in (run_dir / "trace.jsonl").read_bytes().splitlines()]
        runs[arm] = {
            "run_id": run_dir.name, "outcome": score["status"], "function": score["functional"]["status"],
            "violation": score["safety"]["actual_violation"],
            "attempted": len(score["audit"]["attempted_violations"]),
            "blocked": len(score["audit"]["blocked_attempts"]), "diff": score["diff"],
            "events": [{key: row[key] for key in ("event", "call", "tool", "decision", "path", "reason_code", "revision") if key in row}
                       for row in records if row["event"] in ("tool_call", "policy_decision", "authorization_updated")],
        }
    return runs


if __name__ == "__main__":
    with TemporaryDirectory(prefix="scopeguard-controlled-") as temporary:
        directory = Path(temporary)
        runs = {case: replay(case, task_id, directory) for case, task_id in CASES.items()}
        print(json.dumps({"source": "controlled_mock", "cases": runs}, indent=2, sort_keys=True))
