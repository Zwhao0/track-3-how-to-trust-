"""Synthetic scheduling and recovery tests. No model or formal execution."""

import json
import shutil
from pathlib import Path

import pytest

from scopeguard import experiment_plan as plan
from scopeguard.arms import ARMS, SAFETY_PROMPT
from scopeguard.codex_backend import _command
from scopeguard.experiment_batch import Batch, _transient_pretool, open_batch
from scopeguard.judge import evaluate
from scopeguard.runner import run_task

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "benchmarks/manifest.v0.1.json"
CLIENT = {"version": "synthetic-client", "sha256": "a" * 64}


def test_plan_is_reproducible_and_balances_all_arm_positions():
    schedule, config = plan.make_plan(MANIFEST, "a" * 40, CLIENT)
    assert (schedule, config) == plan.make_plan(MANIFEST, "a" * 40, CLIENT)
    assert len(schedule) == len({row["slot_id"] for row in schedule}) == 72
    assert all(sum(row["arm"] == arm for row in schedule) == 24 for arm in ARMS.values())
    for repeat in (1, 2):
        block = [row for row in schedule if row["repeat"] == repeat]
        assert len({row["task_id"] for row in block}) == 12
        for arm in ARMS.values():
            assert [sum(row["arm"] == arm for row in block[i::3]) for i in range(3)] == [4, 4, 4]
    for task in config["tasks"].values():
        arms = task["arms"]
        assert arms["B1"]["prompt_sha256"] == arms["B2"]["prompt_sha256"] != arms["B0"]["prompt_sha256"]
        assert len({row["tool_sha256"] for row in arms.values()}) == 1


def test_actual_mock_executor_and_prompt_parity(tmp_path):
    case = ROOT / "examples/m3-smoke"
    fixture = ROOT / "examples/m1-smoke/fixture.json"
    oracle = ROOT / "tests/fixtures/m3-smoke/oracle.json"
    starts, prompts, scores = {}, {}, {}
    for mode in ARMS:
        result = run_task(case / "task.json", fixture, tmp_path, backend="mock",
                          script_path=case / "mock.json", condition=mode)
        run = Path(result["run_dir"])
        starts[mode] = json.loads((run / "trace.jsonl").read_text().splitlines()[0])
        prompts[mode] = (run / "prompt.txt").read_bytes()
        scores[mode] = evaluate(run, oracle, fixture)
    assert prompts["safety_prompt"] == prompts["guard"]
    assert SAFETY_PROMPT.encode() not in prompts["baseline"]
    assert scores["baseline"]["status"] == scores["safety_prompt"]["status"] == "over_scope"
    assert scores["guard"]["safe_success"]
    for key in ("public_input", "fixture_sha256", "timeout_seconds", "tool_limit"):
        assert all(row[key] == starts["baseline"][key] for row in starts.values())
    guard_run = next(directory for directory in tmp_path.iterdir()
                     if (directory / "prompt.txt").read_bytes() == prompts["guard"]
                     and '"condition": "guard"' in (directory / "trace.jsonl").read_text())
    (guard_run / "prompt.txt").write_bytes(b"tampered")
    assert evaluate(guard_run, oracle, fixture)["status"] == "infra_error"


def test_mcp_launcher_differs_only_in_trusted_executor_selection(tmp_path):
    commands = []
    for condition in ARMS:
        args = _command("codex", tmp_path, tmp_path, tmp_path, 1, condition)
        index = next(i for i, arg in enumerate(args) if arg.startswith("mcp_servers.scopeguard.args="))
        worker_args = json.loads(args[index].partition("=")[2])
        assert worker_args.pop() == condition
        args[index] = json.dumps(worker_args)
        commands.append(args)
    assert commands[0] == commands[1] == commands[2]


def test_unsigned_formal_cli_and_direct_eval_are_blocked(tmp_path, capsys):
    from scopeguard.__main__ import main

    assert main(["experiment", "run", "--manifest", str(MANIFEST), "--packet", str(tmp_path)]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "FORMAL_RUN_BLOCKED"
    case = ROOT / "benchmarks/eval/shipment-webhook-clear"
    with pytest.raises(ValueError, match="FORMAL_RUN_BLOCKED"):
        run_task(case / "task.json", case / "fixture.json", tmp_path / "runs", backend="codex")
    assert not (tmp_path / "runs").exists()


def test_preflight_rejects_tampered_signature_schedule_and_model(tmp_path, monkeypatch):
    code = "a" * 40
    schedule, config = plan.make_plan(MANIFEST, code, CLIENT)
    for name, data in (("schedule.json", schedule), ("run_config.json", config)):
        plan.immutable(tmp_path / name, data)
    approval = {
        "status": "owner_approved", "batch_id": "scopeguard-approval-test", "tag": "scopeguard-freeze-test",
        "code_sha": code, "config_sha256": plan.sha256(plan.canonical(config)),
        "schedule_sha256": config["schedule_sha256"], "manifest_sha256": config["manifest_sha256"],
        "approved_eval_ids": sorted(config["tasks"]), "ci_run_id": 1, "owner": "synthetic",
        "reviewer": "synthetic", "approved_budget": config["budget"],
    }
    path = tmp_path / "approval.json"
    plan.immutable(path, approval)
    monkeypatch.setattr(plan, "git", lambda *args: code if args[0] == "rev-parse" else "")
    monkeypatch.setattr(plan, "client_identity", lambda **kwargs: CLIENT)
    monkeypatch.setattr(plan, "_verify_ci", lambda *args: None)

    def reject(*args):
        raise ValueError("signature rejected")

    monkeypatch.setattr(plan, "_verify_tag", reject)
    with pytest.raises(ValueError, match="signature"):
        plan.preflight(MANIFEST, tmp_path, path)
    monkeypatch.setattr(plan, "_verify_tag", lambda *args: None)
    assert plan.preflight(MANIFEST, tmp_path, path)[0] == schedule
    monkeypatch.setattr(plan, "git", lambda *args: "b" * 40)
    with pytest.raises(ValueError, match="approved SHA"):
        plan.preflight(MANIFEST, tmp_path, path)
    monkeypatch.setattr(plan, "git", lambda *args: code if args[0] == "rev-parse" else "")
    monkeypatch.setattr(plan, "client_identity", lambda **kwargs: {**CLIENT, "version": "changed"})
    with pytest.raises(ValueError, match="configuration"):
        plan.preflight(MANIFEST, tmp_path, path)
    monkeypatch.setattr(plan, "client_identity", lambda **kwargs: CLIENT)
    copied_registry = tmp_path / "benchmarks"
    shutil.copytree(MANIFEST.parent, copied_registry)
    modified_manifest = copied_registry / MANIFEST.name
    modified_manifest.write_bytes(modified_manifest.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="configuration"):
        plan.preflight(modified_manifest, tmp_path, path)
    (tmp_path / "schedule.json").write_bytes(b"[]")
    with pytest.raises(ValueError, match="schedule"):
        plan.preflight(MANIFEST, tmp_path, path)


def _result(status="completed", *, retryable=False, tokens=10):
    return {"status": status, "score": None, "usage": {"input_tokens": tokens, "output_tokens": 1},
            "elapsed_seconds": 1, "asks": [], "answered_questions": [], "retryable": retryable,
            "run_name": None, "error": None}


def _batch_inputs():
    return [{"slot_id": f"slot-{i}"} for i in range(3)], {
        "budget": {"input_tokens": 100, "output_tokens": 100, "elapsed_seconds": 100},
    }


def test_retry_keeps_first_attempt_and_after_tool_error_stops(tmp_path):
    slots, config = _batch_inputs()
    calls = []

    def execute(slot, path):
        calls.append(path.name)
        (path / "raw.txt").write_text("preserved")
        if slot["slot_id"] == "slot-0":
            return _result("infra_error", retryable=True) if path.name == "attempt-1" else _result()
        return _result("infra_error")

    batch = open_batch(tmp_path, slots, config, {}, execute)
    assert calls == ["attempt-1", "attempt-2", "attempt-1"]
    assert batch.primary()["slot-0"]["attempt_count"] == 2
    assert batch.primary()["slot-1"]["status"] == "infra_error"
    assert batch.primary()["slot-2"]["status"] == "not_run"
    assert len(list(tmp_path.glob("runs/*/*/raw.txt"))) == 3
    open_batch(tmp_path, slots, config, {}, lambda *_: pytest.fail("should not rerun"))
    (tmp_path / "runs/slot-0/attempt-1/raw.txt").write_text("tampered")
    with pytest.raises(ValueError, match="evidence changed"):
        open_batch(tmp_path, slots, config, {}, execute)


@pytest.mark.parametrize("budget_key", ["elapsed_seconds", "input_tokens"])
def test_ceilings_leave_remaining_slots_unperformed(tmp_path, budget_key):
    slots, config = _batch_inputs()
    config["budget"][budget_key] = 5
    tick = [0]

    def execute(slot, path):
        tick[0] += 6
        return _result()

    batch = Batch(tmp_path, slots, config)
    batch.load()
    batch.execute(execute, now=lambda: tick[0])
    assert batch.remaining() == ["slot-1", "slot-2"]
    assert batch.stop == ("time_ceiling" if budget_key == "elapsed_seconds" else "token_ceiling")


def test_pause_resumes_after_cancelled_slot_without_overwriting(tmp_path):
    slots, config = _batch_inputs()
    first = open_batch(tmp_path, slots, config, {}, lambda *_: _result("cancelled"))
    assert first.pause and first.remaining() == ["slot-1", "slot-2"]
    resumed = open_batch(tmp_path, slots, config, {}, lambda *_: _result())
    assert resumed.remaining() == []
    assert resumed.primary()["slot-0"]["status"] == "cancelled"
    assert len(resumed.attempts["slot-0"]) == 1


def test_interrupted_unsealed_attempt_becomes_infra_on_resume(tmp_path):
    slots, config = _batch_inputs()
    batch = Batch(tmp_path, slots, config)
    batch.load()
    batch._append(kind="batch_started", at=0)
    batch._append(kind="attempt_started", slot_id="slot-0", attempt=1)
    evidence = tmp_path / "runs/slot-0/attempt-1/partial.txt"
    evidence.parent.mkdir(parents=True)
    evidence.write_text("partial")
    resumed = Batch(tmp_path, slots, config)
    resumed.load()
    resumed.execute(lambda *_: pytest.fail("uncertain attempt cannot be rerun"), now=lambda: 1)
    assert evidence.read_text() == "partial"
    assert resumed.primary()["slot-0"]["error"] == "interrupted_attempt"
    assert resumed.remaining() == ["slot-1", "slot-2"]


def test_resume_seals_existing_outcome_without_repeating_attempt(tmp_path):
    slots, config = _batch_inputs()
    batch = Batch(tmp_path, slots, config)
    batch.load()
    batch._append(kind="batch_started", at=0)
    batch._append(kind="attempt_started", slot_id="slot-0", attempt=1)
    outcome = tmp_path / "runs/slot-0/attempt-1/outcome.json"
    plan.immutable(outcome, {"result": _result(), "artifacts": {}})

    resumed = Batch(tmp_path, slots, config)
    resumed.load()
    calls = []

    def execute(slot, directory):
        calls.append(slot["slot_id"])
        return _result()

    resumed.execute(execute, now=lambda: 1)
    assert calls == ["slot-1", "slot-2"]
    assert resumed.primary()["slot-0"]["status"] == "completed"
    assert resumed.primary()["slot-0"]["attempt_count"] == 1


def test_provider_retry_requires_verified_transient_and_no_tool_attempt():
    started = {"event": "run_started"}
    provider = [{"type": "turn.failed", "error": {"code": "server_error"}}]
    assert _transient_pretool([started], provider, "backend_error")
    assert not _transient_pretool([started, {"event": "tool_call"}], provider, "backend_error")
    assert not _transient_pretool([started], provider + [{"item": {"type": "mcp_tool_call"}}], "backend_error")
    assert not _transient_pretool([started], [], "backend_error")
