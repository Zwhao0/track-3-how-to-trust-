"""Synthetic analysis tests; these fixtures are not model experiments."""

import csv
import json

from scopeguard.experiment_analysis import summarize, write_summary


def _score(*, safe=True, functional="pass", actual_violation=False, wrong_target=False,
           over_scope=False, scope_observed=True, attempted=None, blocked=None,
           expected_missing=None, policy_decisions=None, tool_errors=None):
    status = "safe_completion" if safe else "incomplete"
    if wrong_target:
        status = "wrong_target"
    elif over_scope:
        status = "over_scope"
    return {
        "status": status,
        "safe_success": safe,
        "state_safe": not actual_violation if scope_observed else None,
        "functional": {"status": functional},
        "safety": {
            "actual_violation": actual_violation if scope_observed else None,
            "wrong_target": wrong_target if scope_observed else None,
            "expected_target_not_modified": expected_missing or [],
            "out_of_scope_paths": ["src/extra.py"] if over_scope else [],
            "protected_paths_changed": [],
            "forbidden_removals": [],
            "coverage": {
                "path_presence_and_content": "observed" if scope_observed else "unknown",
            },
        },
        "audit": {
            "status": "valid",
            "attempted_violations": attempted or [],
            "blocked_attempts": blocked or [],
            "executor_reported_writes": [],
            "tool_errors": tool_errors or [],
            "policy_decisions": policy_decisions or [],
        },
    }


def _fixture():
    schedule = []
    primary = {}
    tasks = [
        ("task-a", "family-a", "multi_file", "clear", []),
        ("task-b", "family-b", "wrong_target", "ambiguous", ["target"]),
        ("task-c", "family-c", "over_scope", "clear", []),
        ("task-d", "family-d", "broad_change", "ambiguous", ["approval"]),
    ]
    for index, (task_id, family, category, variant, required) in enumerate(tasks):
        for arm in ("B0", "B1", "B2"):
            slot_id = f"{task_id}-r1-{arm}"
            schedule.append({
                "slot_id": slot_id,
                "task_id": task_id,
                "family": family,
                "category": category,
                "variant": variant,
                "repeat": 1,
                "arm": arm,
                "position": index * 3 + ("B0", "B1", "B2").index(arm),
                "seed": 20261110 + index,
                "required_questions": required,
            })
            result = {
                "status": "completed",
                "score": _score(),
                "usage": {
                    "input_tokens": 100,
                    "cached_input_tokens": 40,
                    "output_tokens": 10,
                    "tool_calls": 2,
                },
                "elapsed_seconds": 10.0 + index,
                "asks": [],
                "answered_questions": [],
                "attempt_count": 1,
            }
            if task_id == "task-b" and arm == "B0":
                result.update(asks=["target", "target", "extra"], answered_questions=["target"])
            if task_id == "task-b" and arm == "B1":
                result.update(
                    score=_score(safe=False, functional="fail"),
                    asks=["target"], answered_questions=[],
                )
            if task_id == "task-b" and arm == "B2":
                result.update(
                    score=_score(
                        safe=False,
                        expected_missing=["src/target.py"],
                        policy_decisions=[{
                            "call": 1,
                            "path": "src/target.py",
                            "decision": "clarify",
                            "reason_code": "unresolved_target",
                        }],
                        tool_errors=[{"call_id": 1, "code": "clarification_required"}],
                    ),
                )
            if task_id == "task-c" and arm == "B0":
                result.update(status="not_run", score=None, asks=None, answered_questions=None, attempt_count=0)
            if task_id == "task-c" and arm == "B1":
                result["score"] = _score(scope_observed=False)
            if task_id == "task-c" and arm == "B2":
                result["score"] = _score(
                    safe=False,
                    policy_decisions=[{
                        "call": 1,
                        "path": "src/expected.py",
                        "decision": "deny",
                        "reason_code": "path_not_allowed",
                    }],
                )
            if task_id == "task-d" and arm == "B2":
                result.update(
                    score=_score(
                        safe=False,
                        attempted=[{"call_id": 2, "path": "src/unrelated.py", "reasons": ["unauthorized_path"]}],
                        blocked=[{"call_id": 2, "path": "src/unrelated.py", "reasons": ["unauthorized_path"]}],
                        policy_decisions=[{
                            "call": 3,
                            "path": "src/expected.py",
                            "decision": "deny",
                            "reason_code": "path_not_allowed",
                        }, {
                            "call": 4,
                            "path": "src/candidate.py",
                            "decision": "clarify",
                            "reason_code": "unresolved_target",
                        }],
                    ),
                    asks=[],
                )
            if task_id == "task-a" and arm == "B0":
                result["attempt_count"] = 2
            if task_id == "task-a" and arm == "B2":
                result.update(status="infra_error", score=None, usage=None)
            if task_id == "task-d" and arm == "B1":
                # Keep this registered slot absent to exercise missing-primary handling.
                continue
            primary[slot_id] = result
    return schedule, primary


def test_planned_denominators_separate_unknown_missing_and_infrastructure():
    schedule, primary = _fixture()
    report = summarize(schedule, primary, draws=200)

    assert report["planned_slots"] == 12
    assert report["primary_records_received"] == 11
    assert report["overall"]["safe_completion"] == {
        "numerator": 5,
        "denominator": 12,
        "rate": 5 / 12,
        "non_success_slots": 7,
        "missing_or_unknown_slots": 3,
    }
    assert report["overall"]["outcome_counts"] == {
        "infra_error": 1,
        "missing": 1,
        "not_run": 1,
        "scored": 9,
    }
    assert report["by_arm"]["B2"]["outcome_counts"]["infra_error"] == 1
    assert report["by_arm"]["B1"]["outcome_counts"]["missing"] == 1
    assert report["by_arm"]["B0"]["outcome_counts"]["not_run"] == 1
    assert report["overall"]["scope"]["denominator"] == 8
    assert report["overall"]["scope"]["unknown_n"] == 1


def test_audit_holds_and_clarification_metrics_use_their_registered_denominators():
    schedule, primary = _fixture()
    report = summarize(schedule, primary, draws=100)
    b0 = report["by_arm"]["B0"]["clarification"]
    assert b0["required_questions_declared"] == 2
    assert b0["required_questions_asked"] == 1
    assert b0["required_questions_answered"] == 1
    assert b0["needless_ask_calls"] == 1
    assert b0["repeated_ask_calls"] == 1
    assert b0["answer_coverage"] == {
        "numerator": 1,
        "denominator": 1,
        "rate": 1.0,
        "zero_valid_request_slots": 2,
        "zero_denominator_policy": "null_when_no_valid_requests",
    }

    b2_audit = report["by_arm"]["B2"]["audit"]
    assert b2_audit["guard_hold_runs"] == 2
    assert b2_audit["holds_without_unsafe_request_runs"] == 1
    assert b2_audit["attempted_violation_operations"] == 1
    assert b2_audit["blocked_violation_operations"] == 1
    assert b2_audit["blocked_operations_per_attempted_operation"] == 1.0
    assert b2_audit["false_blocked_legitimate_operations"] == 2
    assert b2_audit["legitimate_operation_policy_decisions"] == 4
    assert b2_audit["clarification_holds_on_legitimate_operations"] == 2
    clear_b2 = next(row for row in report["controls"] if row["control"] == "clear" and row["arm"] == "B2")
    assert clear_b2["audit"]["false_blocked_legitimate_operations"] == 1
    assert report["by_arm"]["B0"]["clarification"]["post_answer_safe_completion"] == {
        "numerator": 1,
        "denominator": 1,
        "rate": 1.0,
        "eligible_valid_runs": 1,
    }


def test_cost_missingness_paired_bootstrap_and_report_are_reproducible(tmp_path):
    schedule, primary = _fixture()
    # Missing provider usage stays missing and does not enter a complete-planned total.
    primary["task-b-r1-B1"]["usage"] = {"output_tokens": 8}
    first = summarize(schedule, primary, draws=250)
    second = summarize(schedule, primary, draws=250)
    assert first == second

    cost = first["by_arm"]["B1"]["operating_cost"]["input_tokens"]
    assert cost["observed_n"] == 2
    assert cost["missing_n"] == 2
    assert cost["observed_sum"] == 200
    assert cost["complete_planned_sum"] is None
    assert first["by_arm"]["B0"]["operating_cost"]["retries"]["observed_sum"] == 1
    assert first["paired_summary"][0]["pair"] == "B0_to_B1"
    assert first["paired_summary"][1]["pair"] == "B1_to_B2"
    assert first["paired_summary"][0]["metrics"]["safe_completion"]["cluster_bootstrap_95ci"]["family_count"] == 4

    write_summary(tmp_path, first)
    aggregate = json.loads((tmp_path / "aggregate.json").read_text())
    assert aggregate["planned_slots"] == 12
    assert (tmp_path / "task-level.csv").exists()
    assert (tmp_path / "categories.csv").exists()
    assert (tmp_path / "paired-comparisons.csv").exists()
    svg = (tmp_path / "figures" / "planned-safe-rates.svg").read_text()
    assert "Planned safe completion by arm" in svg
    assert "missing/infra:" in svg
    rows = list(csv.DictReader((tmp_path / "paired-comparisons.csv").open(newline="")))
    assert any(row["pair"] == "B1_to_B2" and row["task_id"] == "task-b" for row in rows)


def test_explicit_batcher_none_does_not_fall_back_to_single_attempt_judge_usage():
    schedule, primary = _fixture()
    record = primary["task-a-r1-B0"]
    record["elapsed_seconds"] = None
    record["usage"] = None
    record["score"]["clarification"] = {
        "elapsed_seconds": 999.0,
        "input_tokens": 999,
        "output_tokens": 999,
    }
    report = summarize(schedule, primary, draws=10)
    row = next(row for row in report["task_rows"] if row["slot_id"] == "task-a-r1-B0")
    assert row["elapsed_seconds"] is None
    assert row["input_tokens"] is None
    assert row["output_tokens"] is None


def test_small_family_strata_do_not_get_bootstrap_intervals():
    schedule, primary = _fixture()
    report = summarize(schedule, primary, draws=10)
    # The all-arm report has four families; each category control has fewer.
    assert report["by_arm"]["B0"]["safe_completion_family_cluster_bootstrap_95ci"]["lower"] is not None
    multi_file = next(row for row in report["by_category"] if row["category"] == "multi_file" and row["arm"] == "B0")
    assert multi_file["planned_slots"] == 1
    assert "inconclusive" in report["zero_failure_caveat"]
