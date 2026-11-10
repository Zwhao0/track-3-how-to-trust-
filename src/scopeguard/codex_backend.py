"""Call the signed-in Codex CLI with only the private ScopeGuard MCP configured."""

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from .workspace import TOOLS

MODEL = "gpt-6-luna"
EFFORT = "medium"
DISABLED_FEATURES = (
    "shell_tool", "unified_exec", "apps", "plugins", "hooks", "multi_agent",
    "multi_agent_v2", "computer_use", "browser_use", "browser_use_external",
    "in_app_browser", "skill_search", "tool_suggest", "memories",
    "request_permissions_tool",
)
CLIENT_ENV = ("HOME", "PATH", "TMPDIR", "USER", "LOGNAME", "CODEX_HOME", "LANG")


def _command(binary: str, cwd: Path, workspace: Path, record_dir: Path, deadline: float, condition: str) -> list[str]:
    config = {
        "approval_policy": "never",
        "web_search": "disabled",
        "model_reasoning_effort": EFFORT,
        "agents.enabled": False,
        "mcp_servers.scopeguard.command": sys.executable,
        "mcp_servers.scopeguard.args": [
            "-I", "-m", "scopeguard.mcp_worker", str(workspace), str(record_dir), str(deadline), condition,
        ],
        "mcp_servers.scopeguard.cwd": str(cwd),
        "mcp_servers.scopeguard.required": True,
        "mcp_servers.scopeguard.enabled_tools": list(TOOLS),
        "mcp_servers.scopeguard.default_tools_approval_mode": "approve",
    }
    args = [
        binary, "exec", "--json", "--ephemeral", "--strict-config", "--ignore-user-config",
        "--ignore-rules", "--skip-git-repo-check", "--sandbox", "read-only",
        "--cd", str(cwd), "--model", MODEL,
    ]
    for feature in DISABLED_FEATURES:
        args.extend(("--disable", feature))
    for key, value in config.items():
        args.extend(("-c", f"{key}={json.dumps(value, ensure_ascii=False)}"))
    return [*args, "-"]


def _read_events(path: Path) -> tuple[str | None, dict | None, str | None]:
    final = None
    usage = None
    mcp_success = False
    mcp_failure = False
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            item = row.get("item")
            if item:
                kind = item.get("type")
                if kind == "agent_message" and row["type"] == "item.completed":
                    final = item.get("text")
                elif kind == "mcp_tool_call":
                    if item.get("server") != "scopeguard" or item.get("tool") not in TOOLS:
                        return final, usage, "unexpected_mcp_tool"
                    mcp_success |= item.get("status") == "completed"
                    mcp_failure |= item.get("status") == "failed"
                elif kind not in {"reasoning", "agent_message", "todo_list"}:
                    return final, usage, "unexpected_codex_item"
            if row["type"] == "turn.completed":
                usage = row.get("usage")
    return final, usage, "mcp_calls_failed" if mcp_failure and not mcp_success else None


def run_codex(
    prompt: str, cwd: Path, workspace: Path, record_dir: Path, timeout: float, condition: str,
) -> dict:
    binary = shutil.which("codex")
    if not binary:
        return {"status": "backend_error", "error": "codex_not_found"}
    if os.name != "posix":
        return {"status": "backend_error", "error": "unsupported_codex_platform"}
    import fcntl

    stdout = record_dir / "codex.jsonl"
    env = {key: os.environ[key] for key in CLIENT_ENV if key in os.environ}
    deadline = time.monotonic() + timeout
    stopped = None
    with stdout.open("wb") as out, (record_dir / "codex.stderr").open("wb") as err:
        with subprocess.Popen(
            _command(binary, cwd, workspace, record_dir, deadline, condition),
            cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=out, stderr=err,
            start_new_session=True,
        ) as process:
            try:
                process.communicate(input=prompt.encode("utf-8"), timeout=max(0, deadline - time.monotonic()))
            except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
                stopped = "cancelled" if isinstance(exc, KeyboardInterrupt) else "timeout"

    # Codex may start stdio MCP in another process group. Its own deadline guarantees
    # release of this lock, even if EOF does not shut down the SDK immediately.
    (workspace.parent / "client.closed").touch()
    with (workspace.parent / "mcp.lock").open("ab") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
    if stopped:
        return {"status": stopped}
    if process.returncode != 0:
        return {"status": "backend_error", "error": "codex_exit", "exit_code": process.returncode}
    try:
        final, usage, violation = _read_events(stdout)
    except (UnicodeError, ValueError, KeyError, AttributeError, TypeError):
        return {"status": "backend_error", "error": "invalid_codex_events"}
    if violation:
        return {"status": "backend_error", "error": violation}
    if not isinstance(final, str) or not isinstance(usage, dict):
        return {"status": "backend_error", "error": "incomplete_codex_turn"}
    return {"status": "completed", "message": final, "usage": usage}
