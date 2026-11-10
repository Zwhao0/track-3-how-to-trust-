"""Create reproducible plans and require a signed freeze before formal execution."""

import hashlib
import itertools
import json
import os
import random
import re
import shutil
import subprocess
import urllib.request
from pathlib import Path

from .arms import ARMS, arm_metadata, sha256
from .benchmark import REPO_ROOT, _resolve, validate_manifest
from .codex_backend import DISABLED_FEATURES, EFFORT, MODEL
from .task import load_json, load_task
from .workspace import MAX_TOOL_CALLS, TOOLS

SEED = 20261110
TIMEOUT = 90
BUDGET = {"input_tokens": 6_000_000, "output_tokens": 200_000, "elapsed_seconds": 9000}
REMOTE = "Zwhao0/track-3-how-to-trust-"
BATCH_ID = re.compile(r"[a-z0-9][a-z0-9-]{7,79}")


def canonical(data) -> bytes:
    return (json.dumps(data, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + "\n").encode()


def digest_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def immutable(path: Path, data) -> None:
    """Publish a durable record without replacing an existing record."""
    import tempfile

    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(canonical(data))
            stream.flush()
            os.fsync(stream.fileno())
            os.link(temporary, path)
        finally:
            temporary.unlink()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True, timeout=20).strip()


def client_identity(*, signed_in: bool = False) -> dict:
    binary = shutil.which("codex")
    if binary is None:
        raise ValueError("codex CLI unavailable")
    version = subprocess.check_output([binary, "--version"], text=True, timeout=10).strip()
    if signed_in:
        login = subprocess.run([binary, "login", "status"], capture_output=True, text=True, timeout=10)
        if login.returncode or "Logged in using ChatGPT" not in login.stdout + login.stderr:
            raise ValueError("Codex ChatGPT login unavailable")
    return {"version": version, "sha256": digest_file(Path(binary))}


def make_plan(manifest_path: Path, code_sha: str, client: dict) -> tuple[list[dict], dict]:
    manifest_path = manifest_path.resolve()
    report = validate_manifest(manifest_path)
    if not report["ok"]:
        raise ValueError("manifest validation failed")
    _, manifest = load_json(manifest_path)
    root = manifest_path.parent
    entries = sorted((entry for entry in manifest["tasks"] if entry["split"] == "eval"), key=lambda e: e["task_id"])
    if len(entries) != 12 or manifest["split_seed"] != SEED:
        raise ValueError("formal plan requires the registered 12 tasks and ordering seed")

    registry = {}
    for entry in entries:
        paths = {kind: _resolve(root, entry, kind) for kind in entry["files"]}
        task, _ = load_task(paths["task"], paths["fixture"])
        _, controls = load_json(paths["controls"])
        registry[entry["task_id"]] = {
            "required_questions": controls["required_questions"],
            "answers_sha256": entry["files"].get("answers", {}).get("sha256"),
            "arms": {arm: arm_metadata(task, condition, TOOLS) for condition, arm in ARMS.items()},
        }
    rng = random.Random(SEED)
    orders = list(itertools.permutations(ARMS.values()))
    offset = rng.randrange(len(orders))
    schedule = []
    for repeat in (1, 2):
        block = entries[:]
        rng.shuffle(block)
        for index, entry in enumerate(block):
            for arm in orders[(offset + index + repeat - 1) % len(orders)]:
                task_id = entry["task_id"]
                schedule.append({
                    "slot_id": f"{task_id}-r{repeat}-{arm}",
                    **{key: entry[key] for key in ("task_id", "family", "category", "variant")},
                    "repeat": repeat, "arm": arm, "position": len(schedule) + 1, "seed": SEED,
                    "required_questions": registry[task_id]["required_questions"],
                })
    return schedule, {
        "schema_version": 1, "code_sha": code_sha, "manifest_sha256": digest_file(manifest_path),
        "protocol_sha256": digest_file(REPO_ROOT / "docs/PREREGISTRATION.md"),
        "protocol_revision": 2, "seed": SEED, "planned_slots": len(schedule),
        "schedule_sha256": sha256(canonical(schedule)), "client": client,
        "backend": "codex", "model": MODEL, "reasoning_effort": EFFORT,
        "tool_limit": MAX_TOOL_CALLS, "timeout_seconds": TIMEOUT, "concurrency": 1, "budget": BUDGET,
        "disabled_features": list(DISABLED_FEATURES), "tasks": registry,
        "retry": "one fresh retry only for a verified transient provider error before the first tool call",
    }


def write_plan(output: Path, manifest: Path) -> dict:
    schedule, config = make_plan(manifest, git("rev-parse", "HEAD"), client_identity())
    output.mkdir(parents=True, exist_ok=False)
    immutable(output / "schedule.json", schedule)
    immutable(output / "run_config.json", config)
    return config


def _verify_tag(tag: str, code: str, freeze_sha: str) -> None:
    if not re.fullmatch(r"scopeguard-freeze-[a-z0-9-]+", tag):
        raise ValueError("invalid freeze tag")
    signer = git("config", "--local", "--get", "scopeguard.freezeSigner").upper()
    if not re.fullmatch(r"[0-9A-F]{40,64}", signer):
        raise ValueError("owner signing fingerprint is not configured")
    ref = f"refs/tags/{tag}"
    check = subprocess.run(["git", "verify-tag", "--raw", ref], cwd=REPO_ROOT,
                           capture_output=True, text=True, timeout=20)
    valid = re.findall(r"^\[GNUPG:\] VALIDSIG ([0-9A-F]+) ", check.stderr + check.stdout, re.M)
    if check.returncode or signer not in valid:
        raise ValueError("freeze signature is not from the configured owner")
    if git("rev-parse", f"{ref}^{{commit}}") != code:
        raise ValueError("freeze tag does not match code")
    subject = git("for-each-ref", "--format=%(contents:subject)", ref)
    if subject != f"scopeguard-freeze-sha256 {freeze_sha}":
        raise ValueError("freeze tag does not bind the approval bytes")


def _verify_ci(run_id: int, code: str) -> None:
    if type(run_id) is not int or run_id <= 0:
        raise ValueError("invalid CI run ID")
    url = f"https://api.github.com/repos/{REMOTE}/actions/runs/{run_id}"
    with urllib.request.urlopen(url, timeout=15) as response:
        run = json.load(response)
    if run.get("head_sha") != code or run.get("conclusion") != "success" or run.get("name") != "Offline verification":
        raise ValueError("CI has not passed at the approved code SHA")
    with urllib.request.urlopen(url + "/jobs", timeout=15) as response:
        jobs = json.load(response)["jobs"]
    passed = {job["name"] for job in jobs if job["conclusion"] == "success"}
    if not {"pytest (3.11)", "pytest (3.12)"} <= passed:
        raise ValueError("required Python CI jobs did not pass")


def preflight(manifest: Path, packet: Path, approval: Path | None) -> tuple[list[dict], dict, dict]:
    if approval is None or not approval.is_file():
        raise ValueError("FORMAL_RUN_BLOCKED: signed owner approval required")
    approval_bytes, freeze = load_json(approval)
    keys = {"status", "batch_id", "tag", "code_sha", "config_sha256", "schedule_sha256",
            "manifest_sha256", "approved_eval_ids", "ci_run_id", "owner", "reviewer", "approved_budget"}
    if not isinstance(freeze, dict) or freeze.keys() != keys or freeze["status"] != "owner_approved":
        raise ValueError("invalid freeze approval")
    if approval_bytes != canonical(freeze):
        raise ValueError("approval JSON must use canonical bytes")
    if (
        not isinstance(freeze["batch_id"], str) or not BATCH_ID.fullmatch(freeze["batch_id"])
        or not all(isinstance(freeze[key], str) and freeze[key].strip() for key in ("owner", "reviewer", "tag"))
    ):
        raise ValueError("missing batch identity or owner/reviewer approval")
    code = git("rev-parse", "HEAD")
    if code != freeze["code_sha"] or git("status", "--porcelain"):
        raise ValueError("checkout must be clean and match the approved SHA")
    _verify_tag(freeze["tag"], code, sha256(approval_bytes))
    if os.name != "posix" or shutil.disk_usage(REPO_ROOT).free < 512 * 1024 * 1024:
        raise ValueError("POSIX and 512 MiB free space required")
    schedule, config = make_plan(manifest, code, client_identity(signed_in=True))
    for name, value in (("schedule.json", schedule), ("run_config.json", config)):
        if (packet / name).read_bytes() != canonical(value):
            raise ValueError("planned schedule or configuration has changed")
    if (
        freeze["manifest_sha256"] != config["manifest_sha256"]
        or freeze["schedule_sha256"] != config["schedule_sha256"]
        or freeze["config_sha256"] != sha256(canonical(config))
        or freeze["approved_eval_ids"] != sorted(config["tasks"])
        or freeze["approved_budget"] != config["budget"]
    ):
        raise ValueError("approval does not bind this plan and budget")
    _verify_ci(freeze["ci_run_id"], code)
    return schedule, config, freeze
