"""Validate v2 additions before passing unchanged event shapes to the v1 decoder."""

from ._codec import fields
from ..policy import decide

V2_ERRORS = {
    "scope_denied", "clarification_required", "staging_failed", "workspace_changed", "commit_failed",
}
_REASON_CODES = {
    "allow": {"allowed_path"},
    "deny": {"protected_path", "path_not_allowed"},
    "clarify": {"unresolved_target"},
}


def _validate_decision(event, call, result, task, initial) -> None:
    if not fields(event, "event time_ns call tool path decision reason_code question_id proposed_diff applied"):
        raise ValueError("invalid_policy_fields")
    path = event["path"]
    decision = event["decision"]
    reason = event["reason_code"]
    question = event["question_id"]
    diff = event["proposed_diff"]
    applied = event["applied"]
    args = call.get("arguments")
    if (
        type(event["time_ns"]) is not int or event["time_ns"] <= 0
        or type(event["call"]) is not int or event["call"] != call.get("call")
        or call.get("tool") != "replace_file" or event["tool"] != "replace_file"
        or not isinstance(path, str) or path not in initial
        or not isinstance(args, dict) or args.get("path") != path
        or not isinstance(decision, str) or decision not in _REASON_CODES
        or not isinstance(reason, str) or reason not in _REASON_CODES[decision]
        or type(applied) is not bool
        or not fields(diff, "added removed changed") or diff["added"] != [] or diff["removed"] != []
        or diff["changed"] not in ([], [path])
    ):
        raise ValueError("invalid_policy_decision")
    expected_policy = decide(task["scope"], path)
    if (decision, reason, question) != (
        expected_policy.decision, expected_policy.reason_code, expected_policy.question_id,
    ):
        raise ValueError("policy_authorization_mismatch")

    if decision == "clarify":
        public = task["scope"]["unresolved"]
        if not any(q["id"] == question and path in q["candidate_paths"] for q in public):
            raise ValueError("invalid_policy_question")
        expected = {"ok": False, "error": "clarification_required", "question_id": question}
    else:
        if question is not None:
            raise ValueError("unexpected_policy_question")
        expected = {"ok": False, "error": "scope_denied"}
    if decision != "allow":
        if applied or result != expected:
            raise ValueError("policy_result_mismatch")
    elif applied:
        if result != {"ok": True, "path": path}:
            raise ValueError("policy_result_mismatch")
    elif result not in (
        {"ok": False, "error": "workspace_changed"}, {"ok": False, "error": "commit_failed"},
    ):
        raise ValueError("policy_result_mismatch")


def decode_v2(
    records: list, run_id: str, task: dict, initial: dict, *, scopes: dict | None = None,
) -> tuple[str, list[dict], list[dict]]:
    start = records[0]
    if type(start["trace_schema_version"]) is not int or start["trace_schema_version"] != 2:
        raise ValueError("unsupported_trace_version")
    condition = start.get("condition")
    if condition not in ("baseline", "guard") or start.get("run_id") != run_id:
        raise ValueError("invalid_v2_run_identity")
    if len(records) < 2 or not all(isinstance(row, dict) for row in records):
        raise ValueError("invalid_v2_records")

    # Retain the exact v1 start shape after verifying v2 metadata.
    legacy = [{k: v for k, v in start.items() if k not in {"trace_schema_version", "condition", "run_id"}}]
    decisions = []
    middle = iter(records[1:-1])
    call = next(middle, None)
    if call is not None and call.get("event") == "tool_server_started":
        legacy.append(call)
        call = next(middle, None)
    while call is not None:
        row = next(middle, None)
        policy = None
        if row is not None and row.get("event") == "policy_decision":
            if condition != "guard":
                raise ValueError("policy_event_in_baseline")
            policy = row
            row = next(middle, None)
        if call.get("event") != "tool_call" or row is None or row.get("event") != "tool_result":
            raise ValueError("invalid_v2_tool_sequence")
        result = row.get("result")
        if not isinstance(result, dict):
            raise ValueError("invalid_v2_tool_result")
        error = result.get("error")
        v2_error = isinstance(error, str) and error in V2_ERRORS
        if v2_error and (condition != "guard" or call.get("tool") != "replace_file"):
            raise ValueError("unexpected_guard_error")
        needs_policy = (
            condition == "guard" and call.get("tool") == "replace_file"
            and (result.get("ok") is True or (v2_error and error != "staging_failed"))
        )
        if needs_policy != (policy is not None):
            raise ValueError("missing_or_unexpected_policy_event")
        if policy is not None:
            policy_task = task if scopes is None else {**task, "scope": scopes[call["call"]]}
            _validate_decision(policy, call, result, policy_task, initial)
            decisions.append({k: v for k, v in policy.items() if k not in {"event", "time_ns"}})
        if error == "clarification_required":
            row = {**row, "result": {k: v for k, v in result.items() if k != "question_id"}}
        legacy.extend((call, row))
        call = next(middle, None)
    legacy.append(records[-1])
    return condition, decisions, legacy
