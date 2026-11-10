"""Validate write-ahead commits and replay disclosed public authorizations."""

from ..clarification import ClarificationState
from ._codec import canonical_json, fields


def normalize_commits(records: list) -> list:
    if len(records) < 2 or not all(isinstance(row, dict) for row in records):
        raise ValueError("invalid_v3_records")
    terminal = records[-1]
    if terminal.get("error") in ("unknown_commit", "audit_failed"):
        raise ValueError(terminal["error"])
    start = {**records[0], "trace_schema_version": 2}
    intent_fields = "event time_ns call tool path decision reason_code question_id proposed_diff"
    if "clarification_schema_version" in start:
        intent_fields += " authorization_revision"
    result = [start]
    intent = None
    committed_call = None
    for row in records[1:]:
        event = row.get("event")
        if committed_call is not None:
            if event != "tool_result" or row.get("call") != committed_call:
                raise ValueError("unknown_commit")
            committed_call = None
        if event == "commit_intent":
            if (
                intent is not None or result[-1].get("event") != "tool_call"
                or not fields(row, intent_fields)
                or type(row["time_ns"]) is not int or row["time_ns"] <= 0
                or row["decision"] != "allow"
            ):
                raise ValueError("invalid_commit_intent")
            intent = {k: v for k, v in row.items() if k not in {"event", "time_ns"}}
            continue
        if intent is not None:
            if event != "policy_decision":
                raise ValueError("unknown_commit")
            outcome = {k: v for k, v in row.items() if k not in {"event", "time_ns", "applied"}}
            if outcome != intent:
                raise ValueError("commit_intent_mismatch")
            committed_call = intent["call"]
            intent = None
        elif event == "policy_decision" and row.get("applied") is True:
            raise ValueError("missing_commit_intent")
        result.append(row)
    if intent is not None or committed_call is not None:
        raise ValueError("unknown_commit")
    return result


def _match_event(row: dict, expected: dict) -> None:
    if (
        type(row.get("time_ns")) is not int or row["time_ns"] <= 0
        or canonical_json({k: v for k, v in row.items() if k != "time_ns"}) != canonical_json(expected)
    ):
        raise ValueError("clarification_event_mismatch")


def _validate_ask(state: ClarificationState, call: dict, result: dict, events: list, limit: int):
    args = call.get("arguments")
    call_id = call["call"]
    if call_id > limit:
        error = "tool_budget_exhausted"
    elif not fields(args, "question_id"):
        error = "invalid_arguments"
    elif not isinstance(args["question_id"], str) or args["question_id"] not in state.questions:
        error = "unknown_question"
    else:
        error = None
    if error is not None:
        if events or canonical_json(result) != canonical_json({"ok": False, "error": error}):
            raise ValueError("invalid_ask_error")
        return None

    question_id = args["question_id"]
    binding = {"call": call_id, "question_id": question_id}
    repeated = state.repeated(question_id)
    if len(events) not in (2, 3):
        raise ValueError("invalid_clarification_sequence")
    _match_event(events[0], {"event": "clarification_requested", **binding, "repeated": repeated})
    reply = events[1].get("reply")
    _match_event(events[1], {"event": "clarification_reply", **binding, "reply": reply})
    update = state.observe(question_id, reply)
    if (update is not None) != (len(events) == 3):
        raise ValueError("invalid_authorization_transition")
    if update is not None:
        _match_event(events[2], {"event": "authorization_updated", **binding, **update})
    expected = {"ok": True, "question_id": question_id, "question": state.questions[question_id]["question"], "reply": reply}
    if canonical_json(result) != canonical_json(expected):
        raise ValueError("clarification_result_mismatch")
    return question_id, reply["status"], repeated


def normalize_clarification(records: list, task: dict) -> tuple[list, dict, dict]:
    start, finish = records[0], records[-1]
    version, limit = start.get("clarification_schema_version"), start.get("tool_limit")
    if type(version) is not int or version != 1 or type(limit) is not int or limit <= 0:
        raise ValueError("unsupported_clarification_version")
    state = ClarificationState(task["scope"])
    normalized = [{k: v for k, v in start.items() if k != "clarification_schema_version"}]
    scopes = {}
    totals = dict.fromkeys(("total_asks", "unanswered", "declined", "unavailable", "ambiguous", "repeated_asks"), 0)
    requested, answered = set(), set()

    middle = iter(records[1:-1])
    call = next(middle, None)
    if call is not None and call.get("event") == "tool_server_started":
        normalized.append(call)
        call = next(middle, None)
    while call is not None:
        call_id = call.get("call")
        if call.get("event") != "tool_call" or type(call_id) is not int or call_id <= 0:
            raise ValueError("invalid_v3_tool_call")
        scopes[call_id] = state.effective_scope()
        extras = []
        row = next(middle, None)
        while row is not None and row.get("event") in (
            "policy_decision", "clarification_requested", "clarification_reply", "authorization_updated",
        ):
            extras.append(row)
            row = next(middle, None)
        if row is None or row.get("event") != "tool_result":
            raise ValueError("invalid_v3_tool_sequence")
        normalized.append(call)
        if call.get("tool") == "ask_user":
            totals["total_asks"] += 1
            response = _validate_ask(state, call, row.get("result"), extras, limit)
            if response is not None:
                question_id, status, repeated = response
                requested.add(question_id)
                totals["repeated_asks"] += int(repeated)
                if status == "answered":
                    answered.add(question_id)
                else:
                    totals["unanswered"] += 1
                    totals[status] += 1
        else:
            for extra in extras:
                revision = extra.get("authorization_revision")
                if extra["event"] != "policy_decision" or type(revision) is not int or revision != state.revision:
                    raise ValueError("invalid_policy_authorization_revision")
                normalized.append({k: v for k, v in extra.items() if k != "authorization_revision"})
        normalized.append(row)
        call = next(middle, None)
    normalized.append(finish)

    usage = finish.get("usage")
    def tokens(key):
        count = usage.get(key) if isinstance(usage, dict) else None
        return count if type(count) is int and count >= 0 else None

    metrics = {
        **totals,
        "distinct_questions_requested": len(requested),
        "distinct_questions_answered": len(answered),
        "unnecessary_asks": 0 if state.questions else totals["total_asks"],
        "answered_question_rate": len(answered) / len(requested) if requested else None,
        "tool_calls": len(scopes),
        "elapsed_seconds": finish.get("elapsed_seconds"),
        "input_tokens": tokens("input_tokens"),
        "output_tokens": tokens("output_tokens"),
    }
    return normalized, scopes, metrics
