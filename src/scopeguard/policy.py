"""Deterministic write policy over the validated public TaskSpec scope."""

from dataclasses import dataclass
from typing import Literal

from .task import canonical_path


@dataclass(frozen=True)
class Decision:
    decision: Literal["allow", "deny", "clarify"]
    reason_code: str
    path: str | None
    question_id: str | None = None


def decide(scope: dict, path: object) -> Decision:
    if not canonical_path(path):
        return Decision("deny", "invalid_path", None)
    folded = path.lower()
    for protected in scope["protected_paths"]:
        prefix = protected.lower()
        if folded == prefix or folded.startswith(prefix + "/"):
            return Decision("deny", "protected_path", path)
    if path not in scope["allowed_write_paths"]:
        return Decision("deny", "path_not_allowed", path)
    for question in scope["unresolved"]:
        if path in question["candidate_paths"]:
            return Decision("clarify", "unresolved_target", path, question["id"])
    return Decision("allow", "allowed_path", path)
