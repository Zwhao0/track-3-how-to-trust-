"""Replay recorded evidence and preserve cancellation semantics offline."""

import json
from pathlib import Path

import pytest

from scopeguard.judge import evaluate
from scopeguard.runner import run_task
from scopeguard.workspace import Workspace

ROOT = Path(__file__).resolve().parents[1]


def test_archived_live_clarification_scores_and_discloses_only_after_ask():
    archive = ROOT / "docs/evidence/m4/run-ipwb50oo"
    example = ROOT / "examples/m4-smoke"
    oracle = ROOT / "tests/fixtures/m4-smoke/oracle.json"
    records = [json.loads(line) for line in (archive / "trace.jsonl").read_bytes().splitlines()]
    ask = next(
        i for i, row in enumerate(records)
        if row["event"] == "tool_call" and row["tool"] == "ask_user"
    )
    assert "violet-compass" not in json.dumps(records[:ask + 1])
    assert records[ask + 2]["event"] == "clarification_reply"
    assert "violet-compass" in json.dumps(records[ask + 2])
    score = evaluate(archive, oracle, example / "fixture.json")
    assert score["safe_success"] is True
    assert score["diff"]["changed"] == ["src/customer.py"]
    assert score["clarification"]["distinct_questions_answered"] == 1


def test_cancelled_mock_retains_committed_state_without_safe_completion(tmp_path, monkeypatch):
    example = ROOT / "examples/m1-smoke"
    oracle = ROOT / "tests/fixtures/m2-smoke/oracle.json"
    original = Workspace.call

    def cancel_before_check(self, tool, arguments):
        if tool == "run_public_check":
            raise KeyboardInterrupt
        return original(self, tool, arguments)

    monkeypatch.setattr(Workspace, "call", cancel_before_check)
    run = run_task(
        example / "task.json", example / "fixture.json", tmp_path,
        backend="mock", condition="baseline", script_path=example / "mock.json",
    )
    score = evaluate(Path(run["run_dir"]), oracle, example / "fixture.json")

    assert score["termination_reason"] == "cancelled"
    assert score["functional"]["status"] == "pass"
    assert score["state_safe"] is True
    assert score["safe_success"] is False


def test_v3_guard_final_state_must_match_audited_commits(tmp_path):
    import shutil

    archive = ROOT / "docs/evidence/m4/run-ipwb50oo"
    example = ROOT / "examples/m4-smoke"
    oracle = ROOT / "tests/fixtures/m4-smoke/oracle.json"
    run_dir = tmp_path / archive.name
    shutil.copytree(archive, run_dir)
    final = run_dir / "final.json"
    state = json.loads(final.read_bytes())
    # Preserve the oracle AST while injecting a state change absent from the trusted audit.
    state["src/customer.py"] += "# unaudited change\n"
    final.write_text(json.dumps(state))

    score = evaluate(run_dir, oracle, example / "fixture.json")
    assert score["status"] == "infra_error"
    assert "guard_snapshot_audit_mismatch" in score["diagnostics"]
    assert score["safe_success"] is False


def test_repeated_asks_share_the_tool_budget(tmp_path):
    example = ROOT / "examples/m4-smoke"
    toy = ROOT / "tests/fixtures/m4-smoke"
    script = tmp_path / "repeat.json"
    script.write_text(json.dumps([
        {"tool": "ask_user", "arguments": {"question_id": "display-target"}},
    ] * 21))

    run = run_task(
        example / "task.json", example / "fixture.json", tmp_path / "runs",
        backend="mock", condition="guard", script_path=script, answers_path=toy / "answers.json",
    )
    score = evaluate(Path(run["run_dir"]), toy / "oracle.json", example / "fixture.json")

    assert score["termination_reason"] == "budget_exhausted"
    assert score["safe_success"] is False
    assert score["clarification"]["total_asks"] == 21
    assert score["clarification"]["repeated_asks"] == 19
    assert score["clarification"]["distinct_questions_answered"] == 1
    assert score["audit"]["tool_errors"][-1] == {"call_id": 21, "code": "tool_budget_exhausted"}


@pytest.mark.parametrize("mutation", ["task_id", "fixture_sha256", "unknown_question", "unknown_field"])
def test_answer_script_invalid_binding_fails_before_launch(tmp_path, mutation):
    example = ROOT / "examples/m4-smoke"
    source = ROOT / "tests/fixtures/m4-smoke/answers.json"
    content = json.loads(source.read_bytes())
    if mutation == "unknown_question":
        content["answers"]["never-declared"] = {"status": "declined"}
    else:
        content[mutation] = "invalid"
    script = tmp_path / "answers.json"
    script.write_text(json.dumps(content))
    runs = tmp_path / "runs"

    with pytest.raises(ValueError):
        run_task(
            example / "task.json", example / "fixture.json", runs, backend="mock",
            condition="guard", script_path=example / "mock.json", answers_path=script,
        )
    assert not runs.exists()
