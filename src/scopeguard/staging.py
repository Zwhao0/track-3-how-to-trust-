"""Prepare, validate and commit a single text replacement in Guard mode."""

import os
import stat
import tempfile
from contextlib import ExitStack
from pathlib import Path
from typing import Callable

from .policy import decide
from .task import MAX_FILE_BYTES, canonical_path, valid_text

def _signature(info: os.stat_result) -> tuple:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _open(stack: ExitStack, name: str | Path, flags: int, parent: int | None = None) -> int:
    fd = os.open(name, flags | os.O_NOFOLLOW, dir_fd=parent)
    stack.callback(os.close, fd)
    return fd


def _snapshot(root: int, paths: list[str]) -> tuple[dict[str, str], dict[str, tuple]]:
    """Read the whole fixture through anchored descriptors, checking file identity."""
    expected = set(paths)
    directories = {
        path.rsplit("/", depth)[0]
        for path in paths
        for depth in range(1, path.count("/") + 1)
    }
    files, signatures = {}, {"": _signature(os.fstat(root))}

    def visit(parent: int, prefix: str) -> None:
        for name in sorted(os.listdir(parent)):
            path = prefix + name
            signature = _signature(os.stat(name, dir_fd=parent, follow_symlinks=False))
            with ExitStack() as stack:
                if path in directories:
                    fd = _open(stack, name, os.O_RDONLY | os.O_DIRECTORY, parent)
                    if _signature(os.fstat(fd)) != signature:
                        raise ValueError("directory changed")
                    visit(fd, path + "/")
                    if _signature(os.fstat(fd)) != signature:
                        raise ValueError("directory changed")
                elif path in expected and stat.S_ISREG(signature[2]) and signature[3] == 1:
                    fd = _open(stack, name, os.O_RDONLY | os.O_NONBLOCK, parent)
                    if _signature(os.fstat(fd)) != signature:
                        raise ValueError("file changed")
                    with os.fdopen(fd, "rb", closefd=False) as stream:
                        data = stream.read(MAX_FILE_BYTES + 1)
                    text = data.decode("utf-8")
                    if not valid_text(text) or _signature(os.fstat(fd)) != signature:
                        raise ValueError("invalid or changed file")
                    files[path] = text
                else:
                    raise ValueError("unexpected entry")
                signatures[path] = signature

    visit(root, "")
    if files.keys() != expected or _signature(os.fstat(root)) != signatures[""]:
        raise ValueError("incomplete or changed tree")
    return files, signatures


def _prepare(stage: Path, before: dict[str, str], path: str, content: str, mode: int) -> None:
    for relative, text in before.items():
        target = stage / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((content if relative == path else text).encode("utf-8"))
    (stage / path).chmod(mode)


def _parent(stack: ExitStack, root: int, parts: list[str], signatures: dict[str, tuple]) -> int:
    parent = root
    for depth, name in enumerate(parts, start=1):
        parent = _open(stack, name, os.O_RDONLY | os.O_DIRECTORY, parent)
        if _signature(os.fstat(parent)) != signatures["/".join(parts[:depth])]:
            raise ValueError("directory changed")
    return parent


def _commit(
    root: Path, live_fd: int, staged_fd: int, path: str, live_info: dict, stage_info: dict,
) -> None:
    parts = path.split("/")
    name = parts[-1]
    with ExitStack() as stack:
        target = _parent(stack, live_fd, parts[:-1], live_info)
        source = _parent(stack, staged_fd, parts[:-1], stage_info)
        if (
            _signature(root.lstat()) != live_info[""]
            or _signature(os.stat(name, dir_fd=target, follow_symlinks=False)) != live_info[path]
            or _signature(os.stat(name, dir_fd=source, follow_symlinks=False)) != stage_info[path]
        ):
            raise ValueError("replacement identity changed")
        os.replace(name, name, src_dir_fd=source, dst_dir_fd=target)


def replace_guarded(
    root: Path, paths: list[str], scope: dict, path: str, content: str,
    audit: Callable[..., None],
) -> dict:
    if os.name != "posix" or not canonical_path(path) or path not in paths or not valid_text(content):
        raise ValueError("staging_failed")
    with ExitStack() as stack:
        try:
            live_fd = _open(stack, root, os.O_RDONLY | os.O_DIRECTORY)
            before, live_info = _snapshot(live_fd, paths)
            mode = stat.S_IMODE(live_info[path][2])
            stage = Path(stack.enter_context(tempfile.TemporaryDirectory(dir=root.parent, ignore_cleanup_errors=True)))
            _prepare(stage, before, path, content, mode)
            staged_fd = _open(stack, stage, os.O_RDONLY | os.O_DIRECTORY)
            after, stage_info = _snapshot(staged_fd, paths)
            changed = sorted(name for name in before if before[name] != after[name])
            if after != {**before, path: content} or stat.S_IMODE(stage_info[path][2]) != mode:
                raise ValueError("unexpected staged changes")
        except (OSError, ValueError) as exc:
            raise ValueError("staging_failed") from exc

        decision = decide(scope, path)
        diff = {"added": [], "removed": [], "changed": changed}
        applied = False
        try:
            if decision.decision == "deny":
                return {"ok": False, "error": "scope_denied"}
            if decision.decision == "clarify":
                return {"ok": False, "error": "clarification_required", "question_id": decision.question_id}
            try:
                if _snapshot(live_fd, paths) != (before, live_info):
                    raise ValueError("live snapshot changed")
                _commit(root, live_fd, staged_fd, path, live_info, stage_info)
            except ValueError as exc:
                raise ValueError("workspace_changed") from exc
            except OSError as exc:
                raise ValueError("commit_failed") from exc
            applied = True
            return {"ok": True, "path": path}
        finally:
            audit(
                path=path, decision=decision.decision, reason_code=decision.reason_code,
                question_id=decision.question_id, proposed_diff=diff, applied=applied,
            )
