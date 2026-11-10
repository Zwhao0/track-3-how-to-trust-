"""Replay the publishable scores and statistics without calling Codex."""

import hashlib
import json
import math
import re
import subprocess
import tempfile
from pathlib import Path

from scopeguard.benchmark import _resolve
from scopeguard.experiment_analysis import summarize
from scopeguard.experiment_batch import Batch
from scopeguard.experiment_plan import canonical
from scopeguard.judge import evaluate

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = Path(__file__).resolve().parent
ARCHIVE = BUNDLE / "archive"
OWNER_FINGERPRINT = "16C4353D8F326C6B7EFC78E6AC3C0FE5E51B724D"


def verify(condition, description):
    if not condition:
        raise SystemExit(f"Verification failed: {description}")


def read(path):
    return json.loads(path.read_bytes())


def digest(data):
    return hashlib.sha256(data).hexdigest()


def same_values(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(same_values(left[key], right[key]) for key in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(same_values(x, y) for x, y in zip(left, right))
    if isinstance(left, float):
        return math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-12)
    return left == right


approval_bytes = (BUNDLE / "approval.json").read_bytes()
approval = json.loads(approval_bytes)
verify(approval_bytes == canonical(approval), "canonical approval")
tag = (BUNDLE / "signed-tag.txt").read_bytes()
payload, marker, signature = tag.partition(b"-----BEGIN PGP SIGNATURE-----")
verify(bool(marker), "OpenPGP tag signature is present")
verify(payload.startswith(f"object {approval['code_sha']}\ntype commit\ntag {approval['tag']}\n".encode()), "signed tag target")
verify(payload.endswith(f"\n\nscopeguard-freeze-sha256 {digest(approval_bytes)}\n".encode()), "signed approval hash")
with tempfile.TemporaryDirectory(prefix="sgpg-", dir="/tmp") as temporary:
    home = Path(temporary)
    body_path, sig_path = home / "tag-body", home / "tag-signature.asc"
    body_path.write_bytes(payload)
    sig_path.write_bytes(marker + signature)
    gpg = ["gpg", "--batch", "--homedir", temporary]
    key = subprocess.run([*gpg, "--import", str(BUNDLE / "owner-public-key.asc")], capture_output=True)
    verify(key.returncode == 0, "public signing key import")
    check = subprocess.run([*gpg, "--status-fd", "1", "--verify", str(sig_path), str(body_path)],
                           capture_output=True, text=True)
    verify(check.returncode == 0 and f"[GNUPG:] VALIDSIG {OWNER_FINGERPRINT} " in check.stdout,
           "owner's OpenPGP signature")
config_bytes = (ARCHIVE / "run_config.json").read_bytes()
schedule_bytes = (ARCHIVE / "schedule.json").read_bytes()
config, schedule = json.loads(config_bytes), json.loads(schedule_bytes)
manifest = ROOT / "benchmarks/manifest.v0.1.json"
verify(digest(config_bytes) == approval["config_sha256"], "config digest")
verify(digest(schedule_bytes) == approval["schedule_sha256"], "schedule digest")
verify(digest(manifest.read_bytes()) == approval["manifest_sha256"], "manifest digest")
verify(read(ARCHIVE / "freeze_reference.json") == approval, "batch approval")
entries = {row["task_id"]: row for row in read(manifest)["tasks"]}
slots = {row["slot_id"]: row for row in schedule}
index = read(BUNDLE / "archive-index.json")
exports = {(row["slot_id"], row["attempt"]): row for row in index["exports"]}
verify(len(exports) == len(index["exports"]), "unique export IDs")
batch = Batch(ARCHIVE, schedule, config)
journal_head = "0" * 64
recomputed = 0
for i, path in enumerate(sorted((ARCHIVE / "journal").glob("*.json")), 1):
    verify(path.name == f"{i:06d}.json", "journal sequence")
    content = path.read_bytes()
    entry = json.loads(content)
    verify(content == canonical(entry) and entry["previous"] == journal_head, "journal hash chain")
    journal_head = digest(content)
    event = entry["event"]
    if event["kind"] in ("stop", "pause"):
        setattr(batch, event["kind"], event["cause"])
    if event["kind"] != "attempt_sealed":
        continue
    slot_id, number = event["slot_id"], event["attempt"]
    verify(slot_id in slots and re.fullmatch(r"[A-Za-z0-9-]+", slot_id) and number in (1, 2), "slot or attempt ID")
    row = exports.pop((slot_id, number))
    attempt = ARCHIVE / "runs" / slot_id / f"attempt-{number}"
    outcome_data = (attempt / "outcome.json").read_bytes()
    verify(digest(outcome_data) == event["outcome_sha256"], f"outcome digest for {slot_id}")
    outcome = json.loads(outcome_data)
    verify(outcome["artifacts"] == row["raw_file_hashes"], f"raw file digests for {slot_id}")
    result = outcome["result"]
    batch.attempts.setdefault(slot_id, []).append(result)
    for relative, sha in row["exported_file_hashes"].items():
        file = (attempt / relative).resolve()
        verify(file.is_relative_to(attempt.resolve()), "export path")
        verify(digest(file.read_bytes()) == sha, f"export digest for {slot_id}: {relative}")
    if row["recomputed_from_export"]:
        name = result["run_name"]
        verify(isinstance(name, str) and re.fullmatch(r"run-[a-z0-9_]+", name), "run ID")
        task = entries[slots[slot_id]["task_id"]]
        score = evaluate(attempt / name, _resolve(manifest.parent, task, "oracle"),
                         _resolve(manifest.parent, task, "fixture"))
        verify(canonical(score) == (attempt / "score.json").read_bytes(), f"independent score for {slot_id}")
        recomputed += 1

verify(not exports and journal_head == index["journal_sha256"], "complete export index")
verify(len(batch.attempts) == index["executed_slots"], "executed count")
verify(batch.remaining() == index["remaining"], "not-run roster")
summary = summarize(schedule, batch.primary(), seed=config["seed"])
stored_summary = (BUNDLE / "summary/aggregate.json").read_bytes()
exact = canonical(summary) == stored_summary
verify(exact or same_values(summary, json.loads(stored_summary)), "reproduced aggregate")
print(json.dumps({"status": "verified", "executed_slots": len(batch.attempts), "recomputed_export_scores": recomputed,
                  "aggregate_comparison": "byte_identical" if exact else "float_rounding_only"}))
