"""Validate the write-ahead portion of a Trace v3 record."""

from ._codec import fields


def normalize_commits(records: list) -> list:
    if len(records) < 2 or not all(isinstance(row, dict) for row in records):
        raise ValueError("invalid_v3_records")
    terminal = records[-1]
    if terminal.get("error") in ("unknown_commit", "audit_failed"):
        raise ValueError(terminal["error"])
    start = {**records[0], "trace_schema_version": 2}
    result = [start]
    intent = None
    for row in records[1:]:
        event = row.get("event")
        if event == "commit_intent":
            if (
                intent is not None or result[-1].get("event") != "tool_call"
                or not fields(row, "event time_ns call tool path decision reason_code question_id proposed_diff")
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
            intent = None
        elif event == "policy_decision" and row.get("applied") is True:
            raise ValueError("missing_commit_intent")
        result.append(row)
    if intent is not None:
        raise ValueError("unknown_commit")
    return result
