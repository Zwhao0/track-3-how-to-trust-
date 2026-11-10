"""Regression tests for filesystem and process boundaries."""

import json
import os
import sys
from pathlib import Path

import pytest

from scopeguard import codex_backend
from scopeguard.runner import run_task
from scopeguard.workspace import Workspace, materialize

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "m1-smoke"


@pytest.mark.parametrize("link_type", ["symlink", "directory_symlink", "hardlink"])
def test_workspace_refuses_link_targets(tmp_path, link_type):
    root = tmp_path / "fixture"
    materialize(root, {"src/label.py": "original"})
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "label.py"
    sentinel.write_text("private", encoding="utf-8")

    target = root / "src" / "label.py"
    target.unlink()
    if link_type == "directory_symlink":
        target.parent.rmdir()
        target.parent.symlink_to(outside, target_is_directory=True)
    elif link_type == "hardlink":
        target.hardlink_to(sentinel)
    else:
        target.symlink_to(sentinel)

    workspace = Workspace(root, ["src/label.py"], [], tmp_path / "trace.jsonl")
    assert workspace.call("read_file", {"path": "src/label.py"}) == {
        "ok": False, "error": "unsafe_path_type",
    }
    assert workspace.call("replace_file", {"path": "src/label.py", "content": "edited"}) == {
        "ok": False, "error": "unsafe_path_type",
    }
    assert sentinel.read_text(encoding="utf-8") == "private"


@pytest.mark.skipif(os.name != "posix", reason="Codex process isolation is POSIX-only")
def test_codex_timeout_reaps_client_and_preserves_artifacts(tmp_path, monkeypatch):
    executable = tmp_path / "codex"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import time\n"
        "time.sleep(60)\n",
        encoding="utf-8",
    )
    executable.chmod(0o700)
    monkeypatch.setenv("PATH", str(tmp_path))
    spawn = codex_backend.subprocess.Popen
    pids = []

    def record_pid(*args, **kwargs):
        process = spawn(*args, **kwargs)
        pids.append(process.pid)
        return process

    monkeypatch.setattr(codex_backend.subprocess, "Popen", record_pid)

    result = run_task(
        EXAMPLE / "task.json", EXAMPLE / "fixture.json", tmp_path / "runs",
        backend="codex", timeout=1.5,
    )

    assert result["status"] == "timeout"
    assert len(pids) == 1
    with pytest.raises(ProcessLookupError):
        os.kill(pids[0], 0)
    run_dir = Path(result["run_dir"])
    assert (run_dir / "initial.json").read_bytes() == (run_dir / "final.json").read_bytes()
    trace = (run_dir / "trace.jsonl").read_text().splitlines()
    assert json.loads(trace[-1])["status"] == "timeout"
