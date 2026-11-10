"""Serial execution and append-only recovery for an approved slot schedule."""

import fcntl
import json
import time
from pathlib import Path

from .arms import ARMS, sha256
from .benchmark import _resolve
from .experiment_plan import _verify_tag, canonical, digest_file, immutable
from .judge import evaluate
from .runner import run_task
from .task import load_json

CONDITIONS_BY_ARM = {arm: condition for condition, arm in ARMS.items()}
TRANSIENT = {"rate_limit_exceeded", "server_error", "temporarily_unavailable"}


def _read(path: Path):
    return load_json(path)[1]


def _artifacts(root: Path) -> dict:
    files = {}
    for file in sorted(root.rglob("*")):
        if file.is_symlink():
            raise ValueError("symbolic link in attempt evidence")
        if file.is_file() and file != root / "outcome.json":
            files[file.relative_to(root).as_posix()] = digest_file(file)
    return files


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _transient_pretool(trace: list, provider: list, status: str) -> bool:
    return (
        status == "backend_error" and bool(trace)
        and not any(row.get("event") == "tool_call" for row in trace)
        and not any((row.get("item") or {}).get("type") == "mcp_tool_call" for row in provider)
        and any(row.get("type") in ("error", "turn.failed")
                and isinstance(row.get("error"), dict)
                and row["error"].get("code") in TRANSIENT for row in provider)
    )


def attempt_executor(manifest: Path, config: dict):
    root = manifest.resolve().parent
    _, data = load_json(manifest)
    entries = {entry["task_id"]: entry for entry in data["tasks"] if entry["split"] == "eval"}

    def execute(slot: dict, directory: Path) -> dict:
        if digest_file(manifest) != config["manifest_sha256"]:
            raise ValueError("manifest changed")
        entry = entries[slot["task_id"]]
        paths = {kind: _resolve(root, entry, kind) for kind in entry["files"]}
        answer = paths.get("answers")
        result = run_task(paths["task"], paths["fixture"], directory, backend="codex",
                          condition=CONDITIONS_BY_ARM[slot["arm"]], answers_path=answer,
                          timeout=config["timeout_seconds"], approved_eval=True)
        run_dir = Path(result["run_dir"])
        trace = _rows(run_dir / "trace.jsonl")
        provider_path = run_dir / "codex.jsonl"
        try:
            provider = _rows(provider_path) if provider_path.is_file() else []
        except (OSError, ValueError):
            provider = []
        _resolve(root, entry, "checks")
        oracle = _resolve(root, entry, "oracle")
        score = evaluate(run_dir, oracle, paths["fixture"])
        immutable(directory / "score.json", score)
        start = trace[0]
        parity = (
            start.get("experiment") == config["tasks"][slot["task_id"]]["arms"][slot["arm"]]
            and start.get("model") == {"model": config["model"], "reasoning_effort": config["reasoning_effort"]}
            and start.get("tool_limit") == config["tool_limit"]
            and start.get("timeout_seconds") == config["timeout_seconds"]
        )
        valid = parity and score["status"] != "infra_error"
        transient = parity and _transient_pretool(trace, provider, result["status"])
        return {
            "status": result["status"] if valid else "infra_error",
            "score": score if parity else None,
            "usage": result.get("usage"), "elapsed_seconds": result["elapsed_seconds"],
            "asks": [row["arguments"]["question_id"] for row in trace if row.get("event") == "tool_call"
                     and row.get("tool") == "ask_user" and isinstance(row.get("arguments", {}).get("question_id"), str)]
                    if valid else None,
            "answered_questions": [row["question_id"] for row in trace if row.get("event") == "authorization_updated"]
                                  if valid else None,
            "retryable": transient, "run_name": run_dir.name,
            "client": config["client"],
            "error": None if valid else ("invalid_judge_evidence" if parity else "arm_parity_mismatch"),
        }

    return execute


def _failed(code: str) -> dict:
    return dict(status="infra_error", score=None, usage=None, elapsed_seconds=None,
                asks=None, answered_questions=None, retryable=False, run_name=None, error=code)


class Batch:
    """One writer and exclusive journal files. Completed outcomes are never replaced."""

    def __init__(self, root: Path, schedule: list[dict], config: dict):
        self.root, self.schedule, self.config = root, schedule, config
        self.journal = root / "journal"
        self.head = "0" * 64
        self.index = 0
        self.attempts: dict[str, list[dict]] = {}
        self.pending = None
        self.stop = None
        self.pause = None
        self.started = None

    def _directory(self, slot_id: str, number: int) -> Path:
        return self.root / "runs" / slot_id / f"attempt-{number}"

    def _next_slot(self):
        for slot in self.schedule:
            history = self.attempts.get(slot["slot_id"], [])
            if not history or (len(history) == 1 and history[0]["retryable"]):
                return slot
        return None

    def _accept(self, body: dict) -> None:
        kind = body["kind"]
        if self.stop is not None:
            raise ValueError("journal has records after a terminal stop")
        if kind == "batch_started":
            if self.started is not None:
                raise ValueError("duplicate batch start")
            self.started = body["at"]
            return
        if self.started is None:
            raise ValueError("missing batch start")
        if kind in ("stop", "pause"):
            if self.pending is not None:
                raise ValueError("cannot stop with a pending attempt")
            remaining = self.remaining()
            if body["not_run"] != remaining:
                raise ValueError("invalid not-run roster")
            if kind == "stop":
                self.stop = body["cause"]
            else:
                self.pause = body["cause"]
            return
        slot_id, number = body["slot_id"], body["attempt"]
        if kind == "attempt_started":
            expected = self._next_slot()
            if (self.pending or expected is None or expected["slot_id"] != slot_id
                    or number != 1 + len(self.attempts.get(slot_id, [])) or number > 2):
                raise ValueError("invalid attempt order")
            self.pause = None
            self.pending = (slot_id, number)
        elif kind == "attempt_sealed":
            if self.pending != (slot_id, number):
                raise ValueError("attempt seal has no matching start")
            directory = self._directory(slot_id, number)
            outcome = directory / "outcome.json"
            if digest_file(outcome) != body["outcome_sha256"]:
                raise ValueError("attempt outcome changed")
            record = _read(outcome)
            if record["artifacts"] != _artifacts(directory):
                raise ValueError("attempt evidence changed")
            self.attempts.setdefault(slot_id, []).append(record["result"])
            self.pending = None
        else:
            raise ValueError("unknown journal event")

    def _append(self, **body) -> None:
        record = {"previous": self.head, "event": body}
        immutable(self.journal / f"{self.index + 1:06d}.json", record)
        self._accept(body)
        self.index += 1
        self.head = sha256(canonical(record))

    def load(self, *, create: bool = True) -> None:
        if create:
            self.journal.mkdir(exist_ok=True)
        for file in sorted(self.journal.iterdir()):
            if file.name != f"{self.index + 1:06d}.json" or file.is_symlink():
                raise ValueError("journal index mismatch")
            record = _read(file)
            if record["previous"] != self.head or file.read_bytes() != canonical(record):
                raise ValueError("journal hash-chain mismatch")
            self._accept(record["event"])
            self.index += 1
            self.head = sha256(canonical(record))
        expected = {self._directory(slot, number) for slot, records in self.attempts.items()
                    for number in range(1, len(records) + 1)}
        if self.pending:
            expected.add(self._directory(*self.pending))
        actual = set((self.root / "runs").glob("*/*"))
        if not actual <= expected:
            raise ValueError("unregistered attempt evidence")

    def remaining(self) -> list[str]:
        return [slot["slot_id"] for slot in self.schedule if slot["slot_id"] not in self.attempts]

    def _seal(self, slot_id: str, number: int, result: dict | None) -> None:
        directory = self._directory(slot_id, number)
        path = directory / "outcome.json"
        if result is not None:
            immutable(path, {"result": result, "artifacts": _artifacts(directory)})
        self._append(kind="attempt_sealed", slot_id=slot_id, attempt=number, outcome_sha256=digest_file(path))

    def _token_sum(self, name: str) -> int:
        return sum(value for runs in self.attempts.values() for attempt in runs
                   if type(value := (attempt["usage"] or {}).get(name)) is int and value >= 0)

    def _stop_cause(self, now) -> str | None:
        limits = self.config["budget"]
        if now() - self.started >= limits["elapsed_seconds"]:
            return "time_ceiling"
        if any(self._token_sum(key) >= limits[key] for key in ("input_tokens", "output_tokens")):
            return "token_ceiling"
        if self.attempts:
            last = next(reversed(self.attempts.values()))
            result = last[-1]
            if result["status"] == "infra_error" and not (len(last) == 1 and result["retryable"]):
                return "infrastructure_or_isolation"
            if result["status"] != "cancelled" and not (len(last) == 1 and result["retryable"]):
                usage = result["usage"] or {}
                if any(type(usage.get(key)) is not int or usage[key] < 0 for key in ("input_tokens", "output_tokens")):
                    return "unobserved_usage"
        return None

    def execute(self, executor, *, now=time.time) -> None:
        if self.started is None:
            self._append(kind="batch_started", at=now())
        if self.pending:
            slot_id, number = self.pending
            outcome = self._directory(slot_id, number) / "outcome.json"
            self._seal(slot_id, number, None if outcome.exists() else _failed("interrupted_attempt"))
        if self.stop:
            return
        try:
            while True:
                cause = self._stop_cause(now)
                if cause:
                    self._append(kind="stop", cause=cause, not_run=self.remaining())
                    return
                slot = self._next_slot()
                if slot is None:
                    return
                slot_id = slot["slot_id"]
                number = 1 + len(self.attempts.get(slot_id, []))
                self._append(kind="attempt_started", slot_id=slot_id, attempt=number)
                directory = self._directory(slot_id, number)
                directory.mkdir(parents=True, exist_ok=False)
                try:
                    result = executor(slot, directory)
                except (OSError, ValueError, KeyError, TypeError, AttributeError, RuntimeError) as error:
                    result = _failed(type(error).__name__)
                self._seal(slot_id, number, result)
                if result["status"] == "cancelled":
                    self._append(kind="pause", cause="operator_cancelled", not_run=self.remaining())
                    return
        except KeyboardInterrupt:
            self.__init__(self.root, self.schedule, self.config)
            self.load()
            if self.pending:
                slot_id, number = self.pending
                outcome = self._directory(slot_id, number) / "outcome.json"
                self._seal(slot_id, number, None if outcome.exists() else _failed("interrupted_attempt"))
            self._append(kind="pause", cause="operator_cancelled", not_run=self.remaining())

    def primary(self) -> dict:
        output = {}
        for slot in self.schedule:
            slot_id = slot["slot_id"]
            history = self.attempts.get(slot_id, [])
            if not history:
                output[slot_id] = {**_failed(self.stop or self.pause or "pending"), "status": "not_run", "attempt_count": 0}
                continue
            primary = dict(history[-1])
            observed = [attempt["usage"] for attempt in history]
            primary["usage"] = {
                key: sum(values) if all(type(value) is int and value >= 0 for value in values) else None
                for key in ("input_tokens", "cached_input_tokens", "output_tokens")
                for values in [[usage.get(key) if usage else None for usage in observed]]
            }
            seconds = [attempt["elapsed_seconds"] for attempt in history]
            primary["elapsed_seconds"] = sum(seconds) if all(value is not None for value in seconds) else None
            primary["attempt_count"] = len(history)
            output[slot_id] = primary
        return output


def open_batch(root: Path, schedule: list[dict], config: dict, freeze: dict, executor) -> Batch:
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.resolve() != root.absolute() or (root / ".lock").is_symlink():
        raise ValueError("batch directory aliases another path")
    with (root / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for name, data in (("schedule.json", schedule), ("run_config.json", config), ("freeze_reference.json", freeze)):
            file = root / name
            if not file.exists():
                immutable(file, data)
            elif file.read_bytes() != canonical(data):
                raise ValueError("batch provenance changed")
        batch = Batch(root, schedule, config)
        batch.load()
        batch.execute(executor)
        return batch


def read_batch(root: Path) -> Batch:
    with (root / ".lock").open("r") as lock:
        fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
        schedule, config = _read(root / "schedule.json"), _read(root / "run_config.json")
        freeze = _read(root / "freeze_reference.json")
        if (root / "freeze_reference.json").read_bytes() != canonical(freeze):
            raise ValueError("stored freeze approval bytes have changed")
        _verify_tag(freeze["tag"], freeze["code_sha"], sha256(canonical(freeze)))
        if (sha256(canonical(schedule)) != freeze["schedule_sha256"]
                or sha256(canonical(config)) != freeze["config_sha256"]):
            raise ValueError("batch provenance digest mismatch")
        batch = Batch(root, schedule, config)
        batch.load(create=False)
        return batch


def score_batch(batch: Batch, manifest: Path) -> dict:
    if digest_file(manifest) != batch.config["manifest_sha256"]:
        raise ValueError("score manifest has changed")
    root = manifest.resolve().parent
    entries = {entry["task_id"]: entry for entry in _read(manifest)["tasks"]}
    verified = {}
    for slot in batch.schedule:
        entry = entries[slot["task_id"]]
        for number, outcome in enumerate(batch.attempts.get(slot["slot_id"], []), 1):
            if not outcome["run_name"]:
                continue
            directory = batch._directory(slot["slot_id"], number)
            _resolve(root, entry, "checks")
            score = evaluate(directory / outcome["run_name"], _resolve(root, entry, "oracle"),
                             _resolve(root, entry, "fixture"))
            if (directory / "score.json").read_bytes() != canonical(score):
                raise ValueError("independent re-score mismatch")
            verified[f'{slot["slot_id"]}/attempt-{number}'] = score["status"]
    return verified
