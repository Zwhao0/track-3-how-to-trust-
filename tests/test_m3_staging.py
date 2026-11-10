"""Failure injection and trace compatibility at the mutation boundary."""

import json
import os
from pathlib import Path

import pytest

from scopeguard import staging
from scopeguard.judge import evaluate
from scopeguard.runner import run_task
from scopeguard.workspace import Workspace, materialize

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples/m1-smoke/fixture.json"
TOY = ROOT / "tests/fixtures/m3-smoke/oracle.json"
TASK = ROOT / "examples/m3-smoke/task.json"
SCRIPT = ROOT / "examples/m3-smoke/mock.json"

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Guard uses POSIX descriptor operations")


def workspace(tmp_path):
    files = {"src/label.py": "old\n", "tests/notes.txt": "keep\n"}
    root = tmp_path / "fixture"
    materialize(root, files)
    scope = {"allowed_write_paths": ["src/label.py"], "protected_paths": ["tests"], "unresolved": []}
    return Workspace(root, list(files), [], tmp_path / "trace.jsonl", guard_scope=scope), files


@pytest.mark.parametrize("fault", ["write_io", "extra_staged_edit", "invalid_content", "permission_race"])
def test_staging_failures_preserve_live_contents(tmp_path, monkeypatch, fault):
    work, before = workspace(tmp_path)
    prepare = staging._prepare

    def inject(stage, original, path, content, mode):
        prepare(stage, original, path, content, mode)
        if fault == "write_io":
            raise OSError("injected disk failure")
        if fault == "extra_staged_edit":
            (stage / "tests/notes.txt").write_text("unexpected extra change")
        if fault == "permission_race":
            (work.root / path).chmod(0o600)

    monkeypatch.setattr(staging, "_prepare", inject)
    content = "\x00bad" if fault == "invalid_content" else "candidate\n"
    expected = {
        "write_io": "staging_failed",
        "extra_staged_edit": "staging_failed",
        "invalid_content": "invalid_content",
        "permission_race": "workspace_changed",
    }[fault]

    assert work.call("replace_file", {"path": "src/label.py", "content": content}) == {
        "ok": False, "error": expected,
    }
    assert work.snapshot() == before


def test_commit_error_preserves_prior_committed_edit(tmp_path, monkeypatch):
    work, before = workspace(tmp_path)
    assert work.call("replace_file", {"path": "src/label.py", "content": "accepted\n"})["ok"]

    def fail(*args, **kwargs):
        raise OSError("injected atomic replacement failure")

    monkeypatch.setattr(staging.os, "replace", fail)
    assert work.call("replace_file", {"path": "src/label.py", "content": "rejected\n"}) == {
        "ok": False, "error": "commit_failed",
    }
    assert work.snapshot() == {**before, "src/label.py": "accepted\n"}
    decisions = [
        row for row in map(json.loads, work.trace.read_text().splitlines())
        if row["event"] == "policy_decision"
    ]
    assert [(row["decision"], row["applied"]) for row in decisions] == [("allow", True), ("allow", False)]


def test_legacy_live_archive_preserves_previous_score_semantics():
    run = ROOT / "docs/evidence/m1/run-7r7tuctv"
    oracle = ROOT / "tests/fixtures/m2-smoke/oracle.json"
    old = json.loads((ROOT / "docs/evidence/m2/scores.json").read_bytes())["codex_m1_live_archive"]
    score = evaluate(run, oracle, FIXTURE)

    assert score.pop("task_completed") is True
    assert score.pop("state_safe") is True
    assert score["score_schema_version"] == 2
    score["score_schema_version"] = 1
    assert score == old


@pytest.mark.parametrize("mutation", ["wrong_version", "missing_decision", "false_apply", "baseline_with_policy"])
def test_malformed_v2_trace_fails_closed(tmp_path, mutation):
    result = run_task(TASK, FIXTURE, tmp_path, backend="mock", script_path=SCRIPT, condition="guard")
    run_dir = Path(result["run_dir"])
    trace = run_dir / "trace.jsonl"
    events = list(map(json.loads, trace.read_text().splitlines()))
    decision = next(row for row in events if row["event"] == "policy_decision")
    if mutation == "wrong_version":
        events[0]["trace_schema_version"] = 3
    elif mutation == "missing_decision":
        events.remove(decision)
    elif mutation == "false_apply":
        decision["applied"] = True
    else:
        events[0]["condition"] = "baseline"
    trace.write_text("".join(json.dumps(row) + "\n" for row in events))
    score = evaluate(run_dir, TOY, FIXTURE)
    assert score["status"] == "infra_error"
    assert score["safe_success"] is False
