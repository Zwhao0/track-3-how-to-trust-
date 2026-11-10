"""Bounded readers for the judge's versioned inputs."""

import json
from pathlib import Path

from ..task import _unique_pairs

MAX_ARTIFACT_BYTES = 32 * 1024 * 1024


def _nonfinite(value: str):
    raise ValueError("nonfinite_json_number")


def decode(data: bytes | str):
    return json.loads(data, object_pairs_hook=_unique_pairs, parse_constant=_nonfinite)


def read_bytes(path: Path) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(MAX_ARTIFACT_BYTES + 1)
    if len(data) > MAX_ARTIFACT_BYTES:
        raise ValueError("artifact_too_large")
    return data


def read_json(path: Path):
    return decode(read_bytes(path).decode("utf-8"))


def fields(value, required: str, optional: str = "") -> bool:
    return (
        isinstance(value, dict)
        and set(required.split()) <= value.keys()
        and value.keys() <= set(required.split() + optional.split())
    )


def canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False)
