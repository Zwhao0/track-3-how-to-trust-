"""Public authorization state and the separately held trusted responder."""

from copy import deepcopy
from pathlib import Path

from .task import load_json

REPLY_STATUSES = ("answered", "unavailable", "declined", "ambiguous")


class ClarificationState:
    """Store only public questions and replies already disclosed by the responder."""

    def __init__(self, scope: dict):
        self._scope = deepcopy(scope)
        self.questions = {question["id"]: question for question in self._scope["unresolved"]}
        seen = set()
        for question in self.questions.values():
            candidates = set(question["candidate_paths"])
            if seen & candidates:
                raise ValueError("overlapping_clarification_candidates")
            seen.update(candidates)
        self._disclosed: dict[str, dict] = {}
        self.revision = 0

    def validate_reply(self, question_id: str, reply: object) -> None:
        if question_id not in self.questions:
            raise ValueError("unknown_question")
        if not isinstance(reply, dict) or reply.get("status") not in REPLY_STATUSES:
            raise ValueError("invalid_clarification_reply")
        answered = reply["status"] == "answered"
        required = {"status", "selected_path"} if answered else {"status"}
        if not required <= reply.keys() <= required | {"reply"}:
            raise ValueError("invalid_clarification_reply_fields")
        if "reply" in reply:
            text = reply["reply"]
            if not isinstance(text, str) or not text.strip() or "\0" in text or len(text.encode("utf-8")) > 1024:
                raise ValueError("invalid_clarification_reply_text")
        if not answered:
            return
        selected = reply["selected_path"]
        question = self.questions[question_id]
        if (
            not isinstance(selected, str)
            or selected not in question["candidate_paths"]
            or selected not in self._scope["allowed_write_paths"]
            or any(
                selected.lower() == path.lower() or selected.lower().startswith(path.lower() + "/")
                for path in self._scope["protected_paths"]
            )
        ):
            raise ValueError("invalid_clarification_candidate")

    def repeated(self, question_id: str) -> bool:
        return question_id in self._disclosed

    def observe(self, question_id: str, reply: dict) -> dict | None:
        self.validate_reply(question_id, reply)
        if question_id in self._disclosed:
            if self._disclosed[question_id] != reply:
                raise ValueError("inconsistent_clarification_reply")
            return None
        self._disclosed[question_id] = dict(reply)
        if reply["status"] != "answered":
            return None
        self.revision += 1
        selected = reply["selected_path"]
        return {
            "revision": self.revision,
            "selected_path": selected,
            "removed_paths": sorted(set(self.questions[question_id]["candidate_paths"]) - {selected}),
        }

    def effective_scope(self) -> dict:
        selected = {
            question_id: reply["selected_path"] for question_id, reply in self._disclosed.items()
            if reply["status"] == "answered"
        }
        removed = {
            path for question_id, choice in selected.items()
            for path in self.questions[question_id]["candidate_paths"] if path != choice
        }
        return {
            "allowed_write_paths": [path for path in self._scope["allowed_write_paths"] if path not in removed],
            "protected_paths": self._scope["protected_paths"],
            "unresolved": [question for question_id, question in self.questions.items() if question_id not in selected],
        }


class TrustedResponder:
    """Validate fixed replies without granting authority until a declared question is asked."""

    def __init__(self, task: dict, script: dict | None = None):
        if script is None:
            self._answers = {}
            return
        if not isinstance(script, dict) or script.keys() != {"schema_version", "task_id", "fixture_sha256", "answers"}:
            raise ValueError("invalid_answer_script_fields")
        if type(script["schema_version"]) is not int or script["schema_version"] != 1:
            raise ValueError("invalid_answer_script_version")
        if script["task_id"] != task["task_id"] or script["fixture_sha256"] != task["fixture"]["sha256"]:
            raise ValueError("answer_script_binding_mismatch")
        if not isinstance(script["answers"], dict):
            raise ValueError("invalid_answer_script_entries")
        state = ClarificationState(task["scope"])
        for question_id, reply in script["answers"].items():
            state.validate_reply(question_id, reply)
        self._answers = deepcopy(script["answers"])

    @classmethod
    def from_file(cls, task: dict, path: Path | None) -> "TrustedResponder":
        if path is None:
            return cls(task)
        try:
            _, script = load_json(path)
        except FileNotFoundError as exc:
            raise ValueError("answer_script_not_found") from exc
        if not isinstance(script, dict):
            raise ValueError("invalid_answer_script_fields")
        return cls(task, script)

    def reply_to(self, question_id: str) -> dict:
        return dict(self._answers.get(question_id, {"status": "unavailable"}))

    def worker_script(self, task: dict) -> dict:
        return {
            "schema_version": 1, "task_id": task["task_id"], "fixture_sha256": task["fixture"]["sha256"],
            "answers": deepcopy(self._answers),
        }
