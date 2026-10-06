"""JSON serialization helpers for validation result artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from pipelines.validation.validation_result import ValidationResult


def write_validation_results(
    results: list[ValidationResult],
    path: Path | str,
) -> Path:
    """Write validation results as newline-terminated JSON and return the path."""
    payload = validation_results_to_json_bytes(results)
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(payload)
    return output_path


def validation_results_to_json_bytes(results: list[ValidationResult]) -> bytes:
    """Serialize validation results to deterministic pretty-printed JSON bytes."""
    return (
        json.dumps([result.to_dict() for result in results], indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")
