"""Load a public TaskSpec and its digest-pinned text fixture."""

import hashlib
import json
import re
from pathlib import Path
from typing import Any

MAX_FILE_BYTES = 32_768
MAX_FILES = 128
MAX_JSON_BYTES = 1_048_576
PART = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}")
RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
}


def canonical_path(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) <= 512
        and all(
            PART.fullmatch(part)
            and not part.endswith(".")
            and part.split(".")[0].upper() not in RESERVED_NAMES
            for part in value.split("/")
        )
    )


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def load_json(path: Path) -> tuple[bytes, Any]:
    with path.open("rb") as stream:
        raw = stream.read(MAX_JSON_BYTES + 1)
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError("JSON input exceeds size limit")
    return raw, json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs)


def _fields(value: object, names: str) -> None:
    if not isinstance(value, dict) or set(value) != set(names.split()):
        raise ValueError(f"expected exactly these fields: {names}")


def _identifier(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", value))


def _unique_list(items: object, validate) -> None:
    if (
        not isinstance(items, list)
        or not all(validate(item) for item in items)
        or len(items) != len(set(items))
    ):
        raise ValueError("invalid or duplicate list entries")


def load_task(task_path: Path, fixture_path: Path) -> tuple[dict, dict[str, str]]:
    _, task = load_json(task_path)
    _fields(task, "schema_version task_id fixture request scope public_check_ids")
    if type(task["schema_version"]) is not int or task["schema_version"] != 1:
        raise ValueError("unsupported TaskSpec version")
    if not _identifier(task["task_id"]):
        raise ValueError("invalid task ID")
    request = task["request"]
    if not isinstance(request, str) or not request.strip() or len(request.encode("utf-8")) > 8192:
        raise ValueError("invalid request")
    fixture = task["fixture"]
    _fields(fixture, "id sha256")
    if not _identifier(fixture["id"]):
        raise ValueError("invalid fixture ID")
    raw, files = load_json(fixture_path)
    if fixture["sha256"] != hashlib.sha256(raw).hexdigest():
        raise ValueError("fixture digest mismatch")
    validate_files(files)
    _unique_list(task["public_check_ids"], _identifier)
    if set(task["public_check_ids"]) - {"python-syntax"}:
        raise ValueError("unregistered public check")

    scope = task["scope"]
    _fields(scope, "allowed_write_paths protected_paths unresolved")
    for key in ("allowed_write_paths", "protected_paths"):
        _unique_list(scope[key], canonical_path)
    if set(scope["allowed_write_paths"]) - files.keys():
        raise ValueError("allowed path is not an existing fixture file")
    if not isinstance(scope["unresolved"], list):
        raise ValueError("invalid unresolved questions")
    question_ids = []
    for question in scope["unresolved"]:
        _fields(question, "id question candidate_paths")
        question_ids.append(question["id"])
        prompt = question["question"]
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt.encode("utf-8")) > 1024:
            raise ValueError("invalid question")
        candidates = question["candidate_paths"]
        _unique_list(candidates, canonical_path)
        if len(candidates) < 2 or set(candidates) - set(scope["allowed_write_paths"]):
            raise ValueError("invalid unresolved candidates")
        if any(
            candidate == protected or candidate.startswith(protected + "/")
            for candidate in candidates
            for protected in scope["protected_paths"]
        ):
            raise ValueError("a candidate is protected")
    _unique_list(question_ids, _identifier)
    return task, files


def validate_files(files: object) -> None:
    if not isinstance(files, dict) or not 1 <= len(files) <= MAX_FILES:
        raise ValueError("invalid fixture file count")
    prefixes: dict[str, str] = {}
    for path, content in files.items():
        if not canonical_path(path) or not valid_text(content):
            raise ValueError("invalid fixture path or content")
        parts = path.split("/")
        for depth in range(1, len(parts) + 1):
            prefix = "/".join(parts[:depth])
            if prefixes.setdefault(prefix.lower(), prefix) != prefix:
                raise ValueError("fixture contains case aliases")
            if depth < len(parts) and prefix in files:
                raise ValueError("fixture path is both a file and a directory")


def valid_text(value: object) -> bool:
    if not isinstance(value, str) or "\0" in value:
        return False
    try:
        return len(value.encode("utf-8")) <= MAX_FILE_BYTES
    except UnicodeEncodeError:
        return False
