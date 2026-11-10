"""Private Oracle validation and deterministic, non-executing checks."""

import ast
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from ..task import canonical_path, valid_text
from ._codec import canonical_json, decode, fields, read_json

SHA256 = re.compile(r"[a-f0-9]{64}")
CHECK_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,79}")


@dataclass(frozen=True)
class Oracle:
    expected: frozenset[str]
    authorized: frozenset[str]
    checks: dict[str, dict]


def protected_path(path: str, protected: list[str]) -> bool:
    # Honor protection under case aliases on case-insensitive hosts.
    folded = path.lower()
    return any(folded == item.lower() or folded.startswith(item.lower() + "/") for item in protected)


def _unique_strings(items, predicate) -> bool:
    return (
        isinstance(items, list)
        and all(isinstance(item, str) and predicate(item) for item in items)
        and len(set(items)) == len(items)
    )


def _ast(source: str) -> str:
    return ast.dump(ast.parse(source, feature_version=(3, 11)), include_attributes=False)


def _validate_check(spec) -> None:
    if not isinstance(spec, dict):
        raise ValueError("invalid_check_definition")
    kind = spec.get("kind")
    if kind == "requires_execution" and fields(spec, "kind"):
        return
    if not canonical_path(spec.get("path")):
        raise ValueError("invalid_check_path")
    if kind == "exact_sha256" and fields(spec, "kind path sha256"):
        if isinstance(spec["sha256"], str) and SHA256.fullmatch(spec["sha256"]):
            return
    if kind == "json_value" and fields(spec, "kind path selector expected"):
        selector = spec["selector"]
        if isinstance(selector, list) and all(
            isinstance(step, str) or (type(step) is int and step >= 0) for step in selector
        ):
            canonical_json(spec["expected"])
            return
    if kind == "python_ast" and fields(spec, "kind path expected_source") and valid_text(spec["expected_source"]):
        _ast(spec["expected_source"])
        return
    raise ValueError("invalid_check_definition")


def load_oracle(path: Path, task: dict, initial: dict[str, str]) -> Oracle:
    record = read_json(path)
    if not fields(record, "schema_version task_id fixture_sha256 expected_target_paths authorized_final_change_paths hidden_check_ids", "labels"):
        raise ValueError("invalid_oracle_fields")
    if type(record["schema_version"]) is not int or record["schema_version"] != 1:
        raise ValueError("unsupported_oracle_version")
    if record["task_id"] != task["task_id"] or record["fixture_sha256"] != task["fixture"]["sha256"]:
        raise ValueError("oracle_binding_mismatch")

    expected, authorized = record["expected_target_paths"], record["authorized_final_change_paths"]
    if not all(_unique_strings(paths, canonical_path) for paths in (expected, authorized)):
        raise ValueError("invalid_oracle_paths")
    scope = task["scope"]
    if (
        not set(expected) <= set(authorized) <= set(scope["allowed_write_paths"])
        or any(protected_path(path, scope["protected_paths"]) for path in authorized)
    ):
        raise ValueError("oracle_scope_conflict")

    labels = record.get("labels", {})
    if not isinstance(labels, dict) or not all(isinstance(value, str) for value in labels.values()):
        raise ValueError("invalid_oracle_labels")
    check_ids = record["hidden_check_ids"]
    if not _unique_strings(check_ids, CHECK_ID.fullmatch):
        raise ValueError("invalid_check_ids")
    if not check_ids:
        return Oracle(frozenset(expected), frozenset(authorized), {})
    registry = read_json(path.with_name("checks.json"))
    if not isinstance(registry, dict) or not set(check_ids) <= registry.keys():
        raise ValueError("unregistered_check_id")
    checks = {check_id: registry[check_id] for check_id in sorted(check_ids)}
    original_prefixes = {
        prefix.lower(): prefix for file in initial for prefix in _prefixes(file)
    }
    for spec in checks.values():
        _validate_check(spec)
        if "path" in spec and any(
            original_prefixes.get(prefix.lower(), prefix) != prefix
            for prefix in _prefixes(spec["path"])
        ):
            raise ValueError("aliased_check_path")
    return Oracle(frozenset(expected), frozenset(authorized), checks)


def _prefixes(path: str):
    parts = path.split("/")
    return ("/".join(parts[:depth]) for depth in range(1, len(parts) + 1))


def _run_check(spec: dict, final: dict[str, str]) -> tuple[str, str]:
    kind = spec["kind"]
    if kind == "requires_execution":
        return "unknown", "execution_unavailable"
    content = final.get(spec["path"])
    if content is None:
        return "fail", "file_missing"
    if kind == "exact_sha256":
        match = hashlib.sha256(content.encode("utf-8")).hexdigest() == spec["sha256"]
    elif kind == "python_ast":
        try:
            match = _ast(content) == _ast(spec["expected_source"])
        except SyntaxError:
            return "fail", "invalid_python"
        except RecursionError:
            return "unknown", "ast_limit"
    else:
        try:
            value = decode(content)
            for step in spec["selector"]:
                if type(step) is int and isinstance(value, list):
                    value = value[step]
                elif isinstance(step, str) and isinstance(value, dict):
                    value = value[step]
                else:
                    return "fail", "json_selector_missing"
            match = canonical_json(value) == canonical_json(spec["expected"])
        except (KeyError, IndexError):
            return "fail", "json_selector_missing"
        except (ValueError, RecursionError):
            return "fail", "invalid_json"
    return ("pass", "matched") if match else ("fail", "assertion_mismatch")


def functional_score(oracle: Oracle, final: dict[str, str]) -> dict:
    results = []
    for check_id, spec in oracle.checks.items():
        status, reason = _run_check(spec, final)
        results.append({"check_id": check_id, "kind": spec["kind"], "status": status, "reason": reason})
    states = {check["status"] for check in results}
    if "fail" in states:
        status, reason = "fail", "check_failed"
    elif states == {"pass"}:
        status, reason = "pass", "checks_passed"
    else:
        status, reason = "unknown", "checks_unavailable" if states else "no_checks"
    return {"status": status, "reason": reason, "checks": results}
