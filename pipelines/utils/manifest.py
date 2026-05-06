from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


REQUIRED_MANIFEST_FIELDS = frozenset(
    {
        "pipeline_run_id",
        "source_system",
        "dataset_name",
        "resource_name",
        "source_url",
        "extracted_at_utc",
        "ingestion_date",
        "local_raw_path",
        "s3_raw_uri",
        "file_format",
        "row_count",
        "sha256_checksum",
        "schema_hash",
        "validation_status",
    }
)

VALIDATION_STATUSES = frozenset({"passed", "warning", "failed"})


@dataclass(frozen=True)
class ExtractionManifest:
    pipeline_run_id: str
    source_system: str
    dataset_name: str
    resource_name: str
    source_url: str
    extracted_at_utc: str
    ingestion_date: str
    local_raw_path: str
    s3_raw_uri: str
    file_format: str
    row_count: int
    sha256_checksum: str
    schema_hash: str
    validation_status: str
    request_parameters: dict[str, Any] = field(default_factory=dict)
    column_count: int | None = None
    file_size_bytes: int | None = None
    validation_messages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return validate_manifest(asdict(self))


@dataclass(frozen=True)
class ExtractionResult:
    manifest: ExtractionManifest
    local_raw_path: Path
    row_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest": self.manifest.to_dict(),
            "local_raw_path": str(self.local_raw_path),
            "row_count": self.row_count,
        }


def validate_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    missing_fields = sorted(REQUIRED_MANIFEST_FIELDS - set(manifest))
    if missing_fields:
        raise ValueError(
            "Missing required manifest fields: " + ", ".join(missing_fields)
        )

    blank_fields = sorted(
        field_name
        for field_name in REQUIRED_MANIFEST_FIELDS
        if manifest[field_name] in ("", None)
    )
    if blank_fields:
        raise ValueError("Blank required manifest fields: " + ", ".join(blank_fields))

    _validate_utc_timestamp(str(manifest["extracted_at_utc"]))
    _validate_ingestion_date(str(manifest["ingestion_date"]))
    _validate_non_negative_int("row_count", manifest["row_count"])

    validation_status = str(manifest["validation_status"]).lower()
    if validation_status not in VALIDATION_STATUSES:
        allowed = ", ".join(sorted(VALIDATION_STATUSES))
        raise ValueError(f"validation_status must be one of: {allowed}")

    return {**manifest, "validation_status": validation_status}


def write_manifest(manifest: ExtractionManifest | dict[str, Any], path: Path | str) -> Path:
    manifest_dict = (
        manifest.to_dict()
        if isinstance(manifest, ExtractionManifest)
        else validate_manifest(manifest)
    )
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(manifest_dict, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def _validate_utc_timestamp(value: str) -> None:
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None or timestamp.utcoffset().total_seconds() != 0:
        raise ValueError("extracted_at_utc must be UTC")


def _validate_ingestion_date(value: str) -> None:
    datetime.strptime(value, "%Y-%m-%d")


def _validate_non_negative_int(field_name: str, value: Any) -> None:
    if not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
