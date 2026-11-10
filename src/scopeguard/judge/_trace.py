"""Decode M1's unversioned, serialized tool trace as legacy trace v1."""

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..task import canonical_path, valid_text
from ._codec import canonical_json, decode, fields, read_bytes

TRACE_SCHEMA_VERSION = 1
RUN_ID = re.compile(r"run-[A-Za-z0-9_-]{1,80}")
TERMINATIONS = {"completed", "budget_exhausted", "timeout", "cancelled", "backend_error"}
TOOL_ERRORS = {
    "tool_budget_exhausted", "unknown_tool", "invalid_arguments", "check_not_authorized",
    "path_not_in_fixture", "unsafe_path_type", "invalid_content", "workspace_operation_failed",
}
V1_TOOLS = {
    "list_files": (),
    "read_file": ("path",),
    "replace_file": ("path", "content"),
    "run_public_check": ("check_id",),
}


@dataclass(frozen=True)
class Trace:
    termination: str
    calls: list[tuple[dict, dict]]
    version: int = TRACE_SCHEMA_VERSION
    condition: str = "baseline"
    policy_decisions: list[dict] = field(default_factory=list)
    clarification: dict | None = None


def _event_fields(record: dict, required: str = "", optional: str = "") -> bool:
    return fields(record, "event time_ns " + required, optional)


def _positive_int(value) -> bool:
    return type(value) is int and value > 0


def _number(value, *, lower=0, upper=math.inf) -> bool:
    return type(value) in {int, float} and lower <= value <= upper and math.isfinite(value)


def _validate_start(start: dict, task: dict) -> None:
    if (
        not _event_fields(start, "backend model public_input fixture_sha256 tool_limit timeout_seconds model_prompt")
        or start["event"] != "run_started"
        or not _positive_int(start["tool_limit"])
        or not _number(start["timeout_seconds"], upper=600)
        or start["timeout_seconds"] <= 0
    ):
        raise ValueError("invalid_run_start")
    projection = {key: task[key] for key in ("task_id", "request", "scope", "public_check_ids")}
    if (
        canonical_json(start["public_input"]) != canonical_json(projection)
        or start["fixture_sha256"] != task["fixture"]["sha256"]
    ):
        raise ValueError("trace_task_binding_mismatch")
    model, prompt = start["model"], start["model_prompt"]
    if start["backend"] == "mock" and model is None and prompt is None:
        return
    if (
        start["backend"] == "codex"
        and fields(model, "model reasoning_effort")
        and all(isinstance(value, str) and value for value in model.values())
        and isinstance(prompt, str)
        and "\n" in prompt
        and canonical_json(decode(prompt.rsplit("\n", 1)[1])) == canonical_json(projection)
    ):
        return
    raise ValueError("invalid_model_configuration")


def _validate_finish(finish: dict, start: dict, run_id: str) -> None:
    if (
        not _event_fields(finish, "backend status run_dir elapsed_seconds", "message usage error exit_code backend_result")
        or finish["event"] != "run_finished"
        or finish["backend"] != start["backend"]
        or not isinstance(finish["status"], str)
        or finish["status"] not in TERMINATIONS
        or not isinstance(finish["run_dir"], str)
        or finish["run_dir"].replace("\\", "/").rsplit("/", 1)[-1] != run_id
        or not _number(finish["elapsed_seconds"])
    ):
        raise ValueError("invalid_run_finish")
    for name, expected in (("message", str), ("usage", dict), ("error", str), ("exit_code", int), ("backend_result", dict)):
        if name in finish and type(finish[name]) is not expected:
            raise ValueError("invalid_terminal_detail")


def _validate_result(call: dict, result, initial: dict, task: dict, limit: int) -> None:
    if not isinstance(result, dict) or type(result.get("ok")) is not bool:
        raise ValueError("invalid_tool_result")
    if not result["ok"]:
        if not fields(result, "ok error") or not isinstance(result["error"], str) or not result["error"]:
            raise ValueError("invalid_tool_error")
        return

    tool, args = call["tool"], call["arguments"]
    if tool not in V1_TOOLS or set(args) != set(V1_TOOLS[tool]) or call["call"] > limit:
        raise ValueError("invalid_successful_call")
    if tool in {"read_file", "replace_file"}:
        if not canonical_path(args["path"]) or args["path"] not in initial:
            raise ValueError("invalid_successful_path")
    if tool == "read_file" and fields(result, "ok content") and valid_text(result["content"]):
        return
    if tool == "replace_file" and fields(result, "ok path") and result["path"] == args["path"] and valid_text(args["content"]):
        return
    if tool == "list_files" and fields(result, "ok paths") and result["paths"] == sorted(initial):
        return
    if (
        tool == "run_public_check" and fields(result, "ok passed failures")
        and args["check_id"] in task["public_check_ids"]
        and type(result["passed"]) is bool and isinstance(result["failures"], list)
        and result["passed"] == (not result["failures"])
        and all(
            fields(failure, "path line message")
            and canonical_path(failure["path"]) and failure["path"] in initial
            and (failure["line"] is None or type(failure["line"]) is int)
            and isinstance(failure["message"], str)
            for failure in result["failures"]
        )
    ):
        return
    raise ValueError("invalid_successful_result")


def read_trace(path: Path, run_id: str, task: dict, initial: dict) -> Trace:
    records = [decode(line) for line in read_bytes(path).decode("utf-8").splitlines()]
    if records and isinstance(records[0], dict) and "trace_schema_version" in records[0]:
        from ._trace_v2 import decode_v2

        version = records[0]["trace_schema_version"]
        scopes = metrics = None
        if type(version) is int and version == 3:
            from ._trace_v3 import normalize_clarification, normalize_commits

            records = normalize_commits(records)
            if "clarification_schema_version" in records[0]:
                records, scopes, metrics = normalize_clarification(records, task)
        condition, decisions, legacy = decode_v2(records, run_id, task, initial, scopes=scopes)
        trace = _decode_v1(legacy, run_id, task, initial, has_clarification=metrics is not None)
        return Trace(trace.termination, trace.calls, version=version, condition=condition,
                     policy_decisions=decisions, clarification=metrics)
    return _decode_v1(records, run_id, task, initial)


def _decode_v1(records: list, run_id: str, task: dict, initial: dict, *, has_clarification: bool = False) -> Trace:
    if len(records) < 2 or any(
        not isinstance(row, dict) or not _positive_int(row.get("time_ns")) for row in records
    ):
        raise ValueError("invalid_trace_records")
    start, finish = records[0], records[-1]
    _validate_start(start, task)
    _validate_finish(finish, start, run_id)
    middle = records[1:-1]
    if middle and middle[0].get("event") == "tool_server_started":
        if start["backend"] != "codex" or not _event_fields(middle[0]):
            raise ValueError("invalid_tool_server_start")
        middle = middle[1:]
    if len(middle) % 2:
        raise ValueError("unpaired_tool_event")

    calls = []
    for call_id, (call, result) in enumerate(zip(middle[::2], middle[1::2]), start=1):
        if (
            not _event_fields(call, "call tool arguments") or call["event"] != "tool_call"
            or not _event_fields(result, "call tool result") or result["event"] != "tool_result"
            or not _positive_int(call["call"]) or not _positive_int(result["call"])
            or call["call"] != call_id or result["call"] != call_id
            or not isinstance(call["tool"], str) or not call["tool"]
            or result["tool"] != call["tool"] or not isinstance(call["arguments"], dict)
        ):
            raise ValueError("invalid_tool_pair")
        if not (has_clarification and call["tool"] == "ask_user"):
            _validate_result(call, result["result"], initial, task, start["tool_limit"])
        calls.append((call, result["result"]))
    budget_hit = any(result.get("error") == "tool_budget_exhausted" for _, result in calls)
    if (finish["status"] == "budget_exhausted" and not budget_hit) or (
        finish["status"] == "completed" and budget_hit
    ):
        raise ValueError("trace_budget_mismatch")
    return Trace(finish["status"], calls)
