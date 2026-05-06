from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


def calculate_sha256(path: Path | str, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()

    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(chunk_size), b""):
            digest.update(chunk)

    return digest.hexdigest()


def hash_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def hash_text(content: str, encoding: str = "utf-8") -> str:
    return hash_bytes(content.encode(encoding))


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def hash_row(row: Mapping[str, Any]) -> str:
    return hash_text(canonical_json(dict(row)))


def hash_schema(schema: Sequence[Mapping[str, Any] | str]) -> str:
    return hash_text(canonical_json(list(schema)))
