"""Offline benchmark contract tests and fail-closed input controls."""

import json
import shutil
from pathlib import Path

import pytest

from scopeguard.benchmark import digest, validate_manifest

BENCHMARK = Path(__file__).resolve().parents[1] / "benchmarks"


def _write(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _prototype(tmp_path, family):
    source = json.loads((BENCHMARK / "manifest.v0.1.json").read_bytes())
    source["tasks"] = [entry for entry in source["tasks"] if entry["family"] == family]
    for entry in source["tasks"]:
        for ref in entry["files"].values():
            relative = Path(ref["path"])
            destination = tmp_path / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(BENCHMARK / relative, destination)
    manifest = tmp_path / "manifest.json"
    _write(manifest, source)
    return manifest, source


def test_full_candidate_has_static_controls_and_archive_compatibility():
    result = validate_manifest(BENCHMARK / "manifest.v0.1.json")
    assert result["ok"] is True, result["failures"]
    assert result["eval_pairs"] >= 4
    assert all(count >= 3 for count in result["eval_counts"].values())
    assert result["archive_replays"] == {"v1": True, "v2": True, "v3": True}
    assert {task["split"] for task in result["tasks"].values()} == {"dev", "pilot", "eval"}
    for task in result["tasks"].values():
        assert task["cases"]["noop"]["actual"] == "functional_failure"
        assert all(case["ok"] for case in task["cases"].values())
        if task["variant"] == "ambiguous":
            assert task["cases"]["pre_ask_isolation"]["ok"] is True


@pytest.mark.parametrize("mutation", ["missing", "checksum", "leak", "wrong_reply"])
def test_manifest_rejects_bad_task_artifacts(tmp_path, mutation):
    manifest, source = _prototype(tmp_path, "invoice-delivery")
    entry = next(row for row in source["tasks"] if row["variant"] == "ambiguous")
    task_ref, answer_ref = entry["files"]["task"], entry["files"]["answers"]
    task_path, answer_path = tmp_path / task_ref["path"], tmp_path / answer_ref["path"]
    if mutation == "missing":
        answer_path.unlink()
    elif mutation == "checksum":
        task_path.write_text(task_path.read_text() + "\n")
    elif mutation == "leak":
        task = json.loads(task_path.read_bytes())
        reply = json.loads(answer_path.read_bytes())["answers"]["target"]["reply"]
        task["request"] += " " + reply
        _write(task_path, task)
        task_ref["sha256"] = digest(task_path)
    else:
        answer = json.loads(answer_path.read_bytes())
        answer["answers"]["target"]["selected_path"] = "services/partner/delivery.json"
        _write(answer_path, answer)
        answer_ref["sha256"] = digest(answer_path)
    _write(manifest, source)

    report = validate_manifest(manifest, prototype=True)

    expected = {"missing": "missing_artifact", "checksum": "artifact_checksum_mismatch",
                "leak": "public_answer_leak", "wrong_reply": "answer_oracle_target_mismatch"}
    assert not report["ok"]
    assert report["failures"] == [{"task_id": entry["task_id"], "error": expected[mutation]}]


def test_manifest_rejects_duplicate_task_ids(tmp_path):
    manifest, source = _prototype(tmp_path, "invoice-delivery")
    source["tasks"].append(source["tasks"][0])
    _write(manifest, source)
    with pytest.raises(ValueError, match="duplicate_task_id"):
        validate_manifest(manifest, prototype=True)
