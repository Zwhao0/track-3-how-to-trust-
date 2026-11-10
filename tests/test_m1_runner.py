"""Exercise the installed runner entry point without credentials."""

import json
import subprocess
import sys
from pathlib import Path

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "m1-smoke"
ORACLE_SENTINEL = "private-oracle-must-not-be-loaded"


def run_cli(tmp_path, *, task=EXAMPLE / "task.json", actions=None):
    script = EXAMPLE / "mock.json"
    if actions is not None:
        script = tmp_path / "mock.json"
        script.write_text(json.dumps(actions), encoding="utf-8")
    return subprocess.run(
        [
            sys.executable, "-m", "scopeguard", "run", "--backend", "mock",
            "--task", str(task), "--fixture", str(EXAMPLE / "fixture.json"),
            "--script", str(script), "--runs-dir", str(tmp_path / "runs"),
        ],
        cwd=tmp_path, env={}, capture_output=True, text=True, timeout=10,
    )


def read_artifacts(result, tmp_path):
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "completed"
    run_dir = Path(payload["run_dir"])
    assert run_dir.parent == (tmp_path / "runs").resolve()
    initial = json.loads((run_dir / "initial.json").read_bytes())
    final = json.loads((run_dir / "final.json").read_bytes())
    trace = [json.loads(line) for line in (run_dir / "trace.jsonl").read_bytes().splitlines()]
    return initial, final, trace


def test_mock_cli_changes_only_the_task_copy(tmp_path):
    fixture = EXAMPLE / "fixture.json"
    original = fixture.read_bytes()
    initial, final, trace = read_artifacts(run_cli(tmp_path), tmp_path)
    assert initial == json.loads(original)
    assert final == {**initial, "src/label.py": "def label(value):\n    return value.strip()\n"}
    assert fixture.read_bytes() == original
    assert [row["event"] for row in trace] == ["run_started", *(["tool_call", "tool_result"] * 4), "run_finished"]
    assert [row["tool"] for row in trace if row["event"] == "tool_call"] == [
        "list_files", "read_file", "replace_file", "run_public_check",
    ]
    assert trace[-2]["result"]["passed"] is True


def test_invalid_tool_targets_are_logged_and_leave_snapshot_unchanged(tmp_path):
    outside = tmp_path / "outside.txt"
    actions = [
        {"tool": "replace_file", "arguments": {"path": path, "content": "changed"}}
        for path in ("../src/label.py", str(outside), "src/unknown.py", "src/Label.py")
    ]
    actions.append({"tool": "shell", "arguments": {"command": "touch outside.txt"}})

    initial, final, trace = read_artifacts(run_cli(tmp_path, actions=actions), tmp_path)

    assert final == initial
    assert not outside.exists()
    assert [row["result"] for row in trace if row["event"] == "tool_result"] == [
        *([{"ok": False, "error": "path_not_in_fixture"}] * 4),
        {"ok": False, "error": "unknown_tool"},
    ]


def test_oracle_field_is_rejected_before_a_run_exists(tmp_path):
    task = json.loads((EXAMPLE / "task.json").read_bytes())
    task["oracle"] = {"secret": ORACLE_SENTINEL}
    task_path = tmp_path / "task.json"
    task_path.write_text(json.dumps(task), encoding="utf-8")

    result = run_cli(tmp_path, task=task_path)

    assert result.returncode == 2
    assert ORACLE_SENTINEL not in result.stdout + result.stderr
    assert not (tmp_path / "runs").exists()


def test_static_check_does_not_execute_candidate(tmp_path):
    marker = tmp_path / "candidate-ran"
    actions = [
        {
            "tool": "replace_file",
            "arguments": {"path": "src/label.py", "content": f"open({str(marker)!r}, 'w').close()\n"},
        },
        {"tool": "run_public_check", "arguments": {"check_id": "python-syntax"}},
        {"tool": "run_public_check", "arguments": {"check_id": "pytest"}},
    ]
    _, _, trace = read_artifacts(run_cli(tmp_path, actions=actions), tmp_path)
    outputs = [row["result"] for row in trace if row["event"] == "tool_result"]
    assert outputs[1] == {"ok": True, "passed": True, "failures": []}
    assert outputs[2] == {"ok": False, "error": "check_not_authorized"}
    assert not marker.exists()
