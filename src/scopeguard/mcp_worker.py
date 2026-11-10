"""Private stdio adapter. The runner supplies trusted paths at startup."""

import fcntl
import json
import os
import sys
import threading
import time
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .workspace import CONDITIONS, Workspace, event


def serve(root: Path, record_dir: Path, deadline: float, condition: str) -> None:
    if condition not in CONDITIONS:
        raise ValueError("invalid condition")
    task = json.loads((record_dir / "task.json").read_text(encoding="utf-8"))
    initial = json.loads((record_dir / "initial.json").read_text(encoding="utf-8"))
    trace = record_dir / "trace.jsonl"
    scope = task["scope"] if condition == "guard" else None
    workspace = Workspace(root, list(initial), task["public_check_ids"], trace, guard_scope=scope)
    server = FastMCP("scopeguard", instructions="Tools operate on the current synthetic task fixture.")

    @server.tool()
    def list_files() -> dict:
        """List the regular files in the task fixture."""
        return workspace.call("list_files", {})

    @server.tool()
    def read_file(path: str) -> dict:
        """Read a text file by its exact fixture-relative path."""
        return workspace.call("read_file", {"path": path})

    @server.tool()
    def replace_file(path: str, content: str) -> dict:
        """Replace the full text of one existing fixture file."""
        return workspace.call("replace_file", {"path": path, "content": content})

    @server.tool()
    def run_public_check(check_id: str) -> dict:
        """Run a public static check by its exact task check ID."""
        return workspace.call("run_public_check", {"check_id": check_id})

    with (root.parent / "mcp.lock").open("ab") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if (root.parent / "client.closed").exists() or time.monotonic() >= deadline:
            return
        # The Codex client and the MCP process do not necessarily share a process group.
        timer = threading.Timer(deadline - time.monotonic(), os._exit, args=(124,))
        timer.daemon = True
        timer.start()
        try:
            event(trace, "tool_server_started")
            server.run(transport="stdio")
        finally:
            timer.cancel()


if __name__ == "__main__":
    serve(Path(sys.argv[1]), Path(sys.argv[2]), float(sys.argv[3]), sys.argv[4])
