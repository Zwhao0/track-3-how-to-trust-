"""Verify a finite archive catalog and project it into public replay views."""

from collections import Counter
from csv import DictReader
from dataclasses import dataclass
from difflib import unified_diff
from hashlib import sha256
from pathlib import Path, PurePosixPath
import re

from ..judge import evaluate
from ..judge._codec import decode

ROOT = Path(__file__).resolve().parents[3]
LOCK = "src/scopeguard/demo/archive-lock.json"
MANIFEST = "benchmarks/manifest.v0.1.json"
PACKET = "docs/evidence/m6/freeze-packet"
FORMAL_BUNDLE = "docs/evidence/m6-formal/scopeguard-v01-f850fbfd20dd"
FORMAL_COMMIT = "8a123c50e47eccc999dec08230752a73564f3edf"
FORMAL_FILES = (
    "approval.json", "signed-tag.txt", "archive-index.json", "independent-rescore.json",
    "public-export-verification.json", "summary/aggregate.json", "summary/task-level.csv",
    "summary/paired-comparisons.csv",
)
STRESS_RESULTS = "docs/evidence/stress-v0.2/summary"
CONTROLS = "docs/evidence/finalization/controls.json"
ARCHIVE_LIMIT = 1024 * 1024
COMMITS = {
    "m3": "7369baa062bac204cead5a027dea730f09d64e8d",
    "m4": "ef9dc55d63e0ba17b6864f41f08142ef09ee0ef9",
    "m5": "470d8d8653dc0eb4fa70222de56b55a8a3373919",
    "m6": "2b9614f9e302204285b3d8c04e3cae4f4f73a911",
}
M6_PILOT = "search-stale-window-ambiguous"
PRIVATE_PATTERN = re.compile(
    r"/(?:Users|home|private/var/folders|var/folders|tmp)/|[A-Za-z]:\\\\Users\\\\|"
    r"sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{18,}|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"BEGIN [A-Z ]*PRIVATE KEY"
)
PUBLIC_EVENTS = {
    "run_started": (),
    "tool_server_started": (),
    "tool_call": ("tool", "arguments"),
    "tool_result": ("tool", "result"),
    "policy_decision": ("decision", "reason_code", "path", "question_id", "authorization_revision", "applied", "proposed_diff"),
    "commit_intent": ("decision", "path", "authorization_revision"),
    "clarification_requested": ("question_id",),
    "clarification_reply": ("question_id", "reply"),
    "authorization_updated": ("question_id", "revision", "selected_path", "removed_paths"),
    "run_finished": ("status",),
}


@dataclass(frozen=True)
class Spec:
    milestone: str
    run_id: str
    backend: str
    score_key: str
    title: str
    task_id: str = ""
    split: str = ""

    @property
    def directory(self) -> str:
        prefix = f"docs/evidence/{self.milestone}"
        if self.milestone == "m5":
            prefix += "/pilot"
        return f"{prefix}/{self.run_id}"

    @property
    def fixture(self) -> str:
        if self.milestone == "m3":
            return "examples/m1-smoke/fixture.json"
        if self.milestone == "m4":
            return "examples/m4-smoke/fixture.json"
        return f"benchmarks/{self.split}/{self.task_id}/fixture.json"

    @property
    def oracle(self) -> str:
        if self.milestone in ("m3", "m4"):
            return f"tests/fixtures/{self.milestone}-smoke/oracle.json"
        return f"benchmarks/private/{self.split}/{self.task_id}/oracle.json"


SPECS = (
    Spec("m3", "run-ez2r8iwv", "mock", "mock_baseline", "Mock Baseline"),
    Spec("m3", "run-2ny9f4zf", "mock", "mock_guard", "Mock Guard"),
    Spec("m3", "run-uduuyvw3", "codex", "codex_guard_final", "Codex Guard"),
    Spec("m3", "run-4rb2yann", "codex", "codex_guard_initial_failure", "Codex audit failure"),
    Spec("m4", "run-ipwb50oo", "codex", "codex_guard_answered", "Clarification and authorization"),
    Spec("m5", "run-gs7drso7", "codex", "worker-cache-window-clear", "Worker cache", "worker-cache-window-clear", "dev"),
    Spec("m5", "run-6bdis92w", "codex", M6_PILOT, "Search window", M6_PILOT, "pilot"),
    Spec("m5", "run-425md2lv", "codex", "support-audit-region-clear", "Support audit", "support-audit-region-clear", "pilot"),
    Spec("m6", "run-85e5s2l0", "codex", "B0", "B0 · Baseline", M6_PILOT, "pilot"),
    Spec("m6", "run-ii3f_9t5", "codex", "B1", "B1 · Safety Prompt", M6_PILOT, "pilot"),
    Spec("m6", "run-jzk00hyz", "codex", "B2", "B2 · ScopeGuard", M6_PILOT, "pilot"),
)


class EvidenceError(ValueError):
    """An archive could not be verified."""


def _read(root: Path, name: str) -> bytes:
    relative = PurePosixPath(name)
    if relative.is_absolute() or ".." in relative.parts:
        raise EvidenceError("Invalid evidence path")
    path = root
    for part in relative.parts:
        path /= part
        if path.is_symlink():
            raise EvidenceError(f"Symlink refused for {name}")
    if not path.is_file():
        raise EvidenceError(f"Missing evidence file: {name}")
    with path.open("rb") as stream:
        data = stream.read(ARCHIVE_LIMIT + 1)
    if len(data) > ARCHIVE_LIMIT:
        raise EvidenceError(f"Oversized evidence file: {name}")
    return data


class Reader:
    def __init__(self, root: Path):
        self.root = root
        self.hashes = decode(_read(root, LOCK))
        if not isinstance(self.hashes, dict):
            raise EvidenceError("Invalid evidence lock")

    def data(self, name: str) -> bytes:
        if name not in self.hashes:
            raise EvidenceError("Evidence path is outside the pinned catalog")
        data = _read(self.root, name)
        if sha256(data).hexdigest() != self.hashes.get(name):
            raise EvidenceError(f"Fingerprint mismatch: {name}")
        return data

    def json(self, name: str):
        return decode(self.data(name))

    def public(self, name: str) -> bytes:
        data = self.data(name)
        if PRIVATE_PATTERN.search(data.decode("utf-8")):
            raise EvidenceError(f"Redaction check failed: {name}")
        return data


@dataclass(frozen=True)
class Run:
    spec: Spec
    task: dict
    events: tuple[dict, ...]
    score: dict
    patches: dict[str, str]
    usage: dict
    elapsed: float
    trace_version: int
    score_version: int
    archived_score_version: int
    trace_hash: str
    prompt_hash: str | None
    fixture_hash: str
    model: dict | None

    @property
    def label(self) -> str:
        return "MOCK SCRIPT" if self.spec.backend == "mock" else "REAL CODEX PILOT"

    def step(self, count: int) -> dict:
        if not 0 <= count <= len(self.events):
            raise EvidenceError("Replay step is out of range")
        complete = count == len(self.events)
        return {
            "events": self.events[:count],
            "complete": complete,
            "score": self.score if complete else None,
            "patches": self.patches if complete else {},
        }


def _events(trace: list[dict]) -> tuple[dict, ...]:
    projected = []
    for row in trace:
        kind = row["event"]
        if kind not in PUBLIC_EVENTS:
            continue
        event = {"event": kind}
        if "call" in row:
            event["call"] = row["call"]
        for key in PUBLIC_EVENTS[kind]:
            if key in row:
                event[key] = row[key]
        if kind == "tool_call":
            event["arguments"] = {key: value for key, value in event["arguments"].items() if key != "content"}
        if kind == "tool_result":
            event["result"] = {key: value for key, value in event["result"].items() if key != "content"}
        projected.append(event)
    return tuple(projected)


def _patches(before: dict, after: dict) -> dict[str, str]:
    patches = {}
    for path in sorted(before.keys() | after.keys()):
        if before.get(path) == after.get(path):
            continue
        lines = unified_diff(before.get(path, "").splitlines(), after.get(path, "").splitlines(),
                             fromfile=f"before/{path}" if path in before else "/dev/null",
                             tofile=f"after/{path}" if path in after else "/dev/null", lineterm="")
        patches[path] = "\n".join(lines) or "Only the final newline or line endings changed."
    return patches


def _record(reader: Reader, spec: Spec) -> dict:
    if spec.milestone == "m6":
        return reader.json("docs/evidence/m6/pilot.json")["arms"][spec.score_key]["score"]
    return reader.json(f"{spec.directory.rsplit('/', 1)[0]}/scores.json")[spec.score_key]


def _comparable_score(record: dict, spec: Spec) -> dict:
    if spec.milestone != "m4" or record["score_schema_version"] != 2:
        return record
    # M5 named the distinct-answer coverage explicitly and bumped the score schema.
    clarification = dict(record["clarification"])
    clarification["answered_question_rate"] = clarification.pop("meaningful_clarification_rate")
    return {**record, "score_schema_version": 3, "clarification": clarification}


def _run(reader: Reader, spec: Spec) -> Run:
    files = {name: reader.public(f"{spec.directory}/{name}")
             for name in ("trace.jsonl", "task.json", "initial.json", "final.json")}
    if spec.backend == "codex":
        provider = reader.public(f"{spec.directory}/codex.jsonl")
        if not all(row.get("thread_id", "[redacted]") == "[redacted]"
                   for row in map(decode, provider.splitlines())):
            raise EvidenceError(f"Unredacted Codex thread ID: {spec.run_id}")
    trace = [decode(line) for line in files["trace.jsonl"].splitlines()]
    start, finish = trace[0], trace[-1]
    if start["backend"] != spec.backend or finish["run_dir"] != spec.run_id:
        raise EvidenceError(f"Run identity mismatch: {spec.run_id}")
    for name in (spec.fixture, spec.oracle, str(PurePosixPath(spec.oracle).with_name("checks.json"))):
        reader.data(name)
    prompt_hash = None
    if spec.milestone == "m6":
        prompt_hash = sha256(reader.public(f"{spec.directory}/prompt.txt")).hexdigest()
        if prompt_hash != start["experiment"]["prompt_sha256"]:
            raise EvidenceError(f"Prompt fingerprint mismatch: {spec.run_id}")
    score = evaluate(reader.root / spec.directory, reader.root / spec.oracle, reader.root / spec.fixture)
    record = _record(reader, spec)
    if score != _comparable_score(record, spec) or score["score_schema_version"] not in (2, 3):
        raise EvidenceError(f"Independent score mismatch: {spec.run_id}")
    before, after = decode(files["initial.json"]), decode(files["final.json"])
    changes = _patches(before, after)
    if score["audit"]["status"] == "valid" and set(changes) != {
        path for paths in score["diff"].values() for path in paths
    }:
        raise EvidenceError(f"Snapshot diff mismatch: {spec.run_id}")
    summary = {
        "outcome": score["status"],
        "function": score["functional"]["status"],
        "state_safe": score["state_safe"],
        "safe_completion": score["safe_success"],
        "actual_violation": score["safety"]["actual_violation"],
        "attempted": None if score["audit"]["status"] != "valid" else len(score["audit"]["attempted_violations"]),
        "blocked": None if score["audit"]["status"] != "valid" else len(score["audit"]["blocked_attempts"]),
        "audit": score["audit"]["status"],
    }
    return Run(spec, start["public_input"], _events(trace), summary, changes,
               {key: (finish.get("usage") or {}).get(key)
                for key in ("input_tokens", "cached_input_tokens", "output_tokens")},
               finish["elapsed_seconds"], start["trace_schema_version"], score["score_schema_version"],
               record["score_schema_version"],
               sha256(files["trace.jsonl"]).hexdigest(), prompt_hash, start["fixture_sha256"], start["model"])


def _formal(reader: Reader, candidate: dict, schedule: list) -> tuple[dict, dict]:
    # These fixed files were verified with verify-export.py at the signed evidence commit.
    files = {name: reader.public(f"{FORMAL_BUNDLE}/{name}") for name in FORMAL_FILES}
    approval = decode(files["approval.json"])
    index = decode(files["archive-index.json"])
    report = decode(files["summary/aggregate.json"])
    verification = decode(files["public-export-verification.json"])
    verified_scores = decode(files["independent-rescore.json"])["verified"]
    slots = list(DictReader(files["summary/task-level.csv"].decode().splitlines()))
    pairs = list(DictReader(files["summary/paired-comparisons.csv"].decode().splitlines()))
    if (
        approval["status"] != "owner_approved"
        or any(approval[key] != candidate[key] for key in (
            "batch_id", "tag", "code_sha", "config_sha256", "schedule_sha256", "manifest_sha256",
        ))
        or f"scopeguard-freeze-sha256 {sha256(files['approval.json']).hexdigest()}".encode()
        not in files["signed-tag.txt"]
        or verification["status"] != "verified"
        or verification["executed_slots"] != index["executed_slots"]
        or verification["recomputed_export_scores"] != len(verified_scores)
        or len(slots) != len(schedule) or len(slots) != report["planned_slots"]
        or len(slots) != index["planned_slots"]
        or [row["slot_id"] for row in slots] != [row["slot_id"] for row in schedule]
        or Counter(row["pair"] for row in pairs)
        != {row["pair"]: row["planned_pair_count"] for row in report["paired_summary"]}
    ):
        raise EvidenceError("正式实验归档校验失败")
    return ({
        "state": "completed" if not index["remaining"] else "partial",
        "planned": index["planned_slots"], "executed": index["executed_slots"],
        "scored": index["scored_slots"], "candidate": approval["batch_id"],
        "tag": approval["tag"], "code_sha": approval["code_sha"],
        "manifest_sha256": approval["manifest_sha256"],
    }, report)


@dataclass(frozen=True)
class Catalog:
    runs: dict[str, Run]
    roster: tuple[dict, ...]
    manifest_hash: str
    formal: dict
    ci: dict
    formal_report: dict
    controls: dict
    stress: dict | None
    mock_cases: int
    prompt_parity: bool


def load_catalog(root: Path = ROOT) -> Catalog:
    try:
        reader = Reader(root)
        runs = {spec.run_id: _run(reader, spec) for spec in SPECS}
        mock_traces = [[decode(line) for line in reader.data(f"{spec.directory}/trace.jsonl").splitlines()]
                       for spec in SPECS[:2]]
        left, right = mock_traces
        if (
            left[0]["public_input"] != right[0]["public_input"]
            or left[0]["fixture_sha256"] != right[0]["fixture_sha256"]
            or [(row["tool"], row["arguments"]) for row in left if row["event"] == "tool_call"]
            != [(row["tool"], row["arguments"]) for row in right if row["event"] == "tool_call"]
        ):
            raise EvidenceError("M3 Mock comparison has different inputs or actions")
        pilot_specs = SPECS[-3:]
        pilot = [runs[spec.run_id] for spec in pilot_specs]
        metadata = reader.json("docs/evidence/m6/pilot.json")["arms"]
        starts = [decode(reader.data(f"{spec.directory}/trace.jsonl").splitlines()[0]) for spec in pilot_specs]
        shared = ("public_input", "fixture_sha256", "tool_limit", "timeout_seconds", "model")
        if (
            any(any(start[key] != starts[0][key] for key in shared) for start in starts)
            or len({start["experiment"]["tool_sha256"] for start in starts}) != 1
            or pilot[0].prompt_hash == pilot[1].prompt_hash or pilot[1].prompt_hash != pilot[2].prompt_hash
            or any(metadata[run.spec.score_key]["elapsed_seconds"] != run.elapsed
                   or any(metadata[run.spec.score_key]["usage"][key] != value for key, value in run.usage.items())
                   or metadata[run.spec.score_key]["run_id"] != run.spec.run_id
                   or metadata[run.spec.score_key]["experiment"] != start["experiment"]
                   for run, start in zip(pilot, starts))
        ):
            raise EvidenceError("M6 pilot parity or usage mismatch")
        manifest = reader.json(MANIFEST)
        roster = []
        for entry in manifest["tasks"]:
            if entry["split"] != "eval":
                continue
            task_id = entry["task_id"]
            if not re.fullmatch(r"[a-z0-9-]+", task_id):
                raise EvidenceError("Invalid public task ID")
            public_path = f"benchmarks/eval/{task_id}/task.json"
            task_bytes = reader.public(public_path)
            if sha256(task_bytes).hexdigest() != entry["files"]["task"]["sha256"]:
                raise EvidenceError("Public task fingerprint differs from manifest")
            roster.append({**{key: entry[key] for key in ("task_id", "family", "category", "variant")},
                           "request": decode(task_bytes)["request"], "path": public_path})
        manifest_hash = reader.hashes[MANIFEST]
        candidate = reader.json(f"{PACKET}/pending_approval.json")
        config = reader.json(f"{PACKET}/run_config.json")
        schedule = reader.json(f"{PACKET}/schedule.json")
        ci = reader.json(f"{PACKET}/ci.json")
        preflight = decode(reader.data(f"{PACKET}/preflight.txt").splitlines()[0])
        validation = reader.json("docs/evidence/m6/validation_report.json")
        if (
            candidate["status"] != "review_candidate" or candidate["owner"] or candidate["reviewer"]
            or candidate["code_sha"] != COMMITS["m6"] or ci["head_sha"] != COMMITS["m6"]
            or ci["conclusion"] != "success" or type(ci["id"]) is not int or candidate["ci_run_id"] != ci["id"]
            or candidate["manifest_sha256"] != manifest_hash or validation["manifest_sha256"] != manifest_hash
            or candidate["config_sha256"] != reader.hashes[f"{PACKET}/run_config.json"]
            or config["schedule_sha256"] != reader.hashes[f"{PACKET}/schedule.json"]
            or candidate["schedule_sha256"] != config["schedule_sha256"]
            or candidate["approved_eval_ids"] != sorted(row["task_id"] for row in roster)
            or config["planned_slots"] != len(schedule) or not validation["ok"]
            or preflight["status"] != "FORMAL_RUN_BLOCKED"
        ):
            raise EvidenceError("Freeze review sources do not agree")
        cases = sum(case["ok"] for task in validation["tasks"].values() for case in task["cases"].values())
        formal, formal_report = _formal(reader, candidate, schedule)
        controls = decode(reader.public(CONTROLS))
        if controls["source"] != "controlled_mock":
            raise EvidenceError("受控脚本来源校验失败")
        stress = None
        if f"{STRESS_RESULTS}/observation.json" in reader.hashes:
            observation = reader.json(f"{STRESS_RESULTS}/observation.json")
            aggregate = reader.data(f"{STRESS_RESULTS}/aggregate.json")
            if sha256(aggregate).hexdigest() != observation["analysis_sha256"]:
                raise EvidenceError("探索实验汇总校验失败")
            stress = {"observation": observation, "aggregate": decode(aggregate)}
        return Catalog(runs, tuple(roster), manifest_hash, formal, ci, formal_report,
                       controls["cases"], stress, cases, True)
    except EvidenceError:
        raise
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError) as error:
        raise EvidenceError("Archive is missing or malformed. Run scopeguard demo verify from the repository.") from error
