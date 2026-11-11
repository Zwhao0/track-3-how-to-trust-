"""Export scored exploratory evidence and verify that redaction preserves scores."""

import json
from hashlib import sha256
from pathlib import Path
import re
import shutil

from scopeguard.benchmark import _resolve
from scopeguard.demo.evidence import PRIVATE_PATTERN
from scopeguard.experiment_batch import Batch
from scopeguard.experiment_plan import canonical
from scopeguard.judge import evaluate

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "benchmarks/stress-v0.2"
DESTINATION = ROOT / "docs/evidence/stress-v0.2"
HOST_PATH_OR_TOKEN = re.compile(r"(?i)Bearer\s+[A-Za-z0-9_.-]{20,}|[A-Za-z]:\\+Users\\+")


def load(path):
    return json.loads(path.read_bytes())


def require(condition, message):
    if not condition:
        raise SystemExit(message)


def public_write(path, data):
    decoded = data.decode("utf-8")
    require(not PRIVATE_PATTERN.search(decoded) and not HOST_PATH_OR_TOKEN.search(decoded),
            f"Sensitive material in {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def main():
    source = ROOT / "runs/stress-v02-batch"
    summary = ROOT / "runs/stress-v02-results"
    observation = load(summary / "observation.json")
    registration = (CORPUS / "registration.json").read_bytes()
    config = json.loads(registration)
    manifest = (CORPUS / "manifest.json").read_bytes()
    require(sha256(manifest).hexdigest() == config["manifest_sha256"], "Manifest digest changed")
    require(load(source / "freeze_reference.json")["registration_sha256"] == sha256(registration).hexdigest(),
            "Registration digest changed")
    require(load(source / "run_config.json") == config and load(source / "schedule.json") == config["schedule"],
            "Ledger configuration differs from registration")
    require(sha256((summary / "aggregate.json").read_bytes()).hexdigest() == observation["analysis_sha256"],
            "Summary digest changed")
    batch = Batch(source, config["schedule"], config)
    batch.load()
    require(batch.pending is None and batch.head == observation["journal_sha256"]
            and batch.remaining() == observation["unperformed"], "Journal differs from sealed summary")
    DESTINATION.mkdir(parents=True, exist_ok=False)
    shutil.copytree(source / "journal", DESTINATION / "journal")
    shutil.copytree(summary, DESTINATION / "summary")
    entries = {entry["task_id"]: entry for entry in json.loads(manifest)["tasks"]}
    exports = []
    starts = {}
    for slot in batch.schedule:
        slot_id = slot["slot_id"]
        task = entries[slot["task_id"]]
        for index, outcome in enumerate(batch.attempts.get(slot_id, []), 1):
            relative = Path("runs") / slot_id / f"attempt-{index}"
            raw = source / relative
            exported = DESTINATION / relative
            public_write(exported / "outcome.json", (raw / "outcome.json").read_bytes())
            if outcome["run_name"] is None:
                continue
            run_id = outcome["run_name"]
            run_dir = raw / run_id
            raw_trace = [json.loads(row) for row in (run_dir / "trace.jsonl").read_bytes().splitlines()]
            start = raw_trace[0]
            require(start["backend"] == "codex" and start["experiment"]["arm"] == slot["arm"]
                    and start["model"] == {key: config[key] for key in ("model", "reasoning_effort")}
                    and start["timeout_seconds"] == config["timeout_seconds"]
                    and start["tool_limit"] == config["tool_limit"], f"Condition mismatch for {slot_id}")
            starts.setdefault(slot["task_id"], {})[slot["arm"]] = start["experiment"]
            for row in raw_trace:
                if row.get("event") == "run_finished":
                    row["run_dir"] = run_id
                    row.pop("message", None)
            public_write(exported / "score.json", (raw / "score.json").read_bytes())
            for name in ("task.json", "initial.json", "final.json", "prompt.txt"):
                public_write(exported / run_id / name, (run_dir / name).read_bytes())
            public_write(exported / run_id / "trace.jsonl", b"".join((json.dumps(row, ensure_ascii=True) + "\n").encode()
                         for row in raw_trace))
            score = evaluate(exported / run_id, _resolve(CORPUS, task, "oracle"),
                             _resolve(CORPUS, task, "fixture"))
            require(canonical(score) == (exported / "score.json").read_bytes(), f"Score changed for {slot_id}")
            exports.append({"slot_id": slot_id, "run_id": run_id, "score": score["status"],
                            "trace_sha256": sha256((exported / run_id / "trace.jsonl").read_bytes()).hexdigest()})
    for task_id, arms in starts.items():
        require(len({metadata["tool_sha256"] for metadata in arms.values()}) == 1,
                f"Tool signatures differ for {task_id}")
        if {"B1", "B2"} <= arms.keys():
            require(arms["B1"]["prompt_sha256"] == arms["B2"]["prompt_sha256"],
                    f"B1/B2 prompts differ for {task_id}")
    public_write(DESTINATION / "export-index.json", canonical({
        "source": "exploratory_stress_v02", "exported_and_rescored": len(exports), "runs": exports,
        "redaction": "Absolute run directories and final free text removed. Provider stdout and stderr retained locally.",
    }))
    print(json.dumps({"rescored": len(exports), **observation}))


if __name__ == "__main__":
    main()
