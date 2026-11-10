"""Shared M1 tools for private fixture workspaces."""

import ast
import json
import os
import stat
import tempfile
import time
from pathlib import Path

from .clarification import ClarificationState, TrustedResponder
from .staging import replace_guarded
from .task import canonical_path, valid_text

TOOLS = {
    "list_files": (),
    "read_file": ("path",),
    "replace_file": ("path", "content"),
    "run_public_check": ("check_id",),
    "ask_user": ("question_id",),
}
MAX_TOOL_CALLS = 20
CONDITIONS = ("baseline", "guard")


class AuditError(RuntimeError):
    """A policy decision could not be recorded by the trusted executor."""


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def event(trace_path: Path, kind: str, *, durable: bool = False, **fields) -> None:
    with trace_path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"event": kind, "time_ns": time.time_ns(), **fields}) + "\n")
        if durable:
            stream.flush()
            os.fsync(stream.fileno())


def materialize(root: Path, files: dict[str, str]) -> None:
    root.mkdir(mode=0o700)
    for path, content in files.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content.encode("utf-8"))


class Workspace:
    def __init__(
        self, root: Path, paths: list[str], checks: list[str], trace: Path, *,
        guard_scope: dict | None = None, clarification: ClarificationState | None = None,
        responder: TrustedResponder | None = None,
    ):
        self.root = root
        self.paths = sorted(paths)
        self.checks = frozenset(checks)
        self.trace = trace
        self.guard_scope = guard_scope
        self.clarification = clarification
        self.responder = responder
        self.calls = 0
        self.pending_commit = False
        self.audit_error: str | None = None

    def _record(self, kind: str, **details) -> None:
        if self.audit_error is not None:
            raise AuditError(self.audit_error)
        try:
            event(self.trace, kind, durable=self.pending_commit or kind == "commit_intent", **details)
        except OSError as exc:
            self.audit_error = "unknown_commit" if self.pending_commit else "audit_failed"
            try:
                event(self.trace, "audit_failure", call=self.calls, error=self.audit_error)
            except OSError:
                pass
            raise AuditError(self.audit_error) from exc
        if kind == "commit_intent":
            self.pending_commit = True

    def _existing_file(self, path: object) -> Path:
        if not canonical_path(path) or path not in self.paths:
            raise ValueError("path_not_in_fixture")
        target = self.root
        for part in path.split("/")[:-1]:
            target /= part
            if not stat.S_ISDIR(target.lstat().st_mode):
                raise ValueError("unsafe_path_type")
        target /= path.split("/")[-1]
        info = target.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("unsafe_path_type")
        return target

    def snapshot(self) -> dict[str, str]:
        actual = sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*") if not p.is_dir() or p.is_symlink())
        if actual != self.paths:
            raise ValueError("unexpected workspace entries")
        return {path: self._existing_file(path).read_bytes().decode("utf-8") for path in self.paths}

    def call(self, tool: str, arguments: dict) -> dict:
        self.calls += 1
        self._record("tool_call", call=self.calls, tool=tool, arguments=arguments)
        try:
            if self.calls > MAX_TOOL_CALLS:
                raise ValueError("tool_budget_exhausted")
            if tool not in TOOLS:
                raise ValueError("unknown_tool")
            if not isinstance(arguments, dict) or set(arguments) != set(TOOLS[tool]):
                raise ValueError("invalid_arguments")
            result = {"ok": True, **self._dispatch(tool, arguments)}
        except ValueError as exc:
            result = {"ok": False, "error": str(exc)}
        except (OSError, RecursionError):
            result = {"ok": False, "error": "workspace_operation_failed"}
        self._record("tool_result", call=self.calls, tool=tool, result=result)
        self.pending_commit = False
        return result

    def _ask_user(self, question_id: object) -> dict:
        state = self.clarification
        if not isinstance(question_id, str) or state is None or question_id not in state.questions:
            raise ValueError("unknown_question")
        question = state.questions[question_id]["question"]
        repeated = state.repeated(question_id)
        self._record("clarification_requested", call=self.calls, question_id=question_id, repeated=repeated)
        reply = self.responder.reply_to(question_id)
        update = state.observe(question_id, reply)
        self._record("clarification_reply", call=self.calls, question_id=question_id, reply=reply)
        if update is not None:
            self._record("authorization_updated", call=self.calls, question_id=question_id, **update)
        return {"question_id": question_id, "question": question, "reply": reply}

    def _dispatch(self, tool: str, args: dict) -> dict:
        if tool == "ask_user":
            return self._ask_user(args["question_id"])
        if tool == "list_files":
            return {"paths": self.paths}
        if tool == "run_public_check":
            if args["check_id"] != "python-syntax" or "python-syntax" not in self.checks:
                raise ValueError("check_not_authorized")
            failures = []
            for path in self.paths:
                if path.endswith(".py"):
                    source = self._existing_file(path).read_bytes().decode("utf-8")
                    try:
                        ast.parse(source, filename=path)
                    except SyntaxError as exc:
                        failures.append({"path": path, "line": exc.lineno, "message": exc.msg})
            return {"passed": not failures, "failures": failures}

        target = self._existing_file(args["path"])
        if tool == "read_file":
            return {"content": target.read_bytes().decode("utf-8")}
        if not valid_text(args["content"]):
            raise ValueError("invalid_content")
        if self.guard_scope is not None:
            def audit(kind, **details):
                if self.clarification is not None:
                    details["authorization_revision"] = self.clarification.revision
                self._record(kind, call=self.calls, tool=tool, **details)

            scope = self.clarification.effective_scope() if self.clarification is not None else self.guard_scope
            return replace_guarded(self.root, self.paths, scope, args["path"], args["content"], audit)
        # The temporary write is outside the visible fixture tree and on the same filesystem.
        with tempfile.TemporaryDirectory(dir=self.root.parent) as temp:
            staged_file = Path(temp) / "replacement"
            staged_file.write_bytes(args["content"].encode("utf-8"))
            staged_file.chmod(stat.S_IMODE(target.stat().st_mode))
            os.replace(staged_file, target)
        return {"path": args["path"]}
