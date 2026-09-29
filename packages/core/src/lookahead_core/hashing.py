"""Stable hashes for specs, plans and pre-registrations.

A design hash is the SHA-256 of the canonical JSON of the design, sorted keys,
no whitespace, floats printed at a stated precision. Two designs that differ in
any field hash differently; the same design hashes the same on every machine.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_normalise(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def design_hash(payload: Mapping[str, Any]) -> str:
    """The pre-registration hash: sixteen hex characters of the canonical design."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()[:16]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalise(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _normalise(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, list | tuple):
        return [_normalise(v) for v in value]
    if isinstance(value, bool | int | str) or value is None:
        return value
    if isinstance(value, float):
        return float(f"{value:.10g}")
    if hasattr(value, "model_dump"):
        return _normalise(value.model_dump(mode="json"))
    return str(value)
