from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from pipelines.storage.raw_artifacts import ArtifactLocation, ArtifactReader
from pipelines.validation.validation_failures import (
    ValidationFailedError,
    assert_no_blocking_failures,
)
from pipelines.validation.validation_result import ValidationResult


ManifestReference = Path | str | ArtifactLocation


@dataclass(frozen=True)
class PreparedRawLoadInputs:
    """Validated manifest and validation-result inputs for a raw load route."""

    manifest_groups: dict[str, list[dict[str, Any]]]
    validation_results: list[ValidationResult]
    pipeline_run_ids: tuple[str, ...]


def prepare_raw_load_inputs(
    *,
    sba_7a_manifest_paths: Iterable[ManifestReference],
    sba_504_manifest_paths: Iterable[ManifestReference],
    census_bds_manifest_paths: Iterable[ManifestReference],
    bls_laus_manifest_paths: Iterable[ManifestReference],
    validation_result_paths: Iterable[ManifestReference],
    error_cls: type[Exception],
    missing_validation_message: str,
    table_prefix: str = "",
    artifact_reader: ArtifactReader | None = None,
) -> PreparedRawLoadInputs:
    """Load, validate, and group raw-load manifests for a warehouse route."""
    validation_results = load_validation_results(
        validation_result_paths,
        error_cls=error_cls,
        missing_message=missing_validation_message,
        artifact_reader=artifact_reader,
    )
    assert_validation_passed(validation_results, error_cls=error_cls)

    manifest_groups = load_raw_manifest_groups(
        sba_7a_manifest_paths=sba_7a_manifest_paths,
        sba_504_manifest_paths=sba_504_manifest_paths,
        census_bds_manifest_paths=census_bds_manifest_paths,
        bls_laus_manifest_paths=bls_laus_manifest_paths,
        table_prefix=table_prefix,
        artifact_reader=artifact_reader,
    )
    require_manifest_groups(manifest_groups, error_cls=error_cls)
    return PreparedRawLoadInputs(
        manifest_groups=manifest_groups,
        validation_results=validation_results,
        pipeline_run_ids=pipeline_run_ids_from_manifest_groups(manifest_groups),
    )


def load_raw_manifest_groups(
    *,
    sba_7a_manifest_paths: Iterable[ManifestReference],
    sba_504_manifest_paths: Iterable[ManifestReference],
    census_bds_manifest_paths: Iterable[ManifestReference],
    bls_laus_manifest_paths: Iterable[ManifestReference],
    table_prefix: str = "",
    artifact_reader: ArtifactReader | None = None,
) -> dict[str, list[dict[str, Any]]]:
    return {
        f"{table_prefix}raw_sba_7a_foia": load_manifests(
            sba_7a_manifest_paths,
            artifact_reader=artifact_reader,
        ),
        f"{table_prefix}raw_sba_504_foia": load_manifests(
            sba_504_manifest_paths,
            artifact_reader=artifact_reader,
        ),
        f"{table_prefix}raw_census_bds_state_year": load_manifests(
            census_bds_manifest_paths,
            artifact_reader=artifact_reader,
        ),
        f"{table_prefix}raw_bls_laus_state_month": load_manifests(
            bls_laus_manifest_paths,
            artifact_reader=artifact_reader,
        ),
    }


def load_manifests(
    paths: Iterable[ManifestReference],
    *,
    artifact_reader: ArtifactReader | None = None,
) -> list[dict[str, Any]]:
    reader = artifact_reader or ArtifactReader()
    return [json.loads(_read_reference_text(path, reader)) for path in paths]


def load_validation_results(
    paths: Iterable[ManifestReference],
    *,
    error_cls: type[Exception],
    missing_message: str,
    artifact_reader: ArtifactReader | None = None,
) -> list[ValidationResult]:
    validation_paths = list(paths)
    if not validation_paths:
        raise error_cls(missing_message)

    reader = artifact_reader or ArtifactReader()
    results: list[ValidationResult] = []
    for path in validation_paths:
        payload = json.loads(_read_reference_text(path, reader))
        results.extend(ValidationResult(**record) for record in payload)
    return results


def assert_validation_passed(
    validation_results: list[ValidationResult],
    *,
    error_cls: type[Exception],
) -> None:
    try:
        assert_no_blocking_failures(validation_results)
    except ValidationFailedError as exc:
        raise error_cls(str(exc)) from exc


def require_manifest_groups(
    manifest_groups: dict[str, list[dict[str, Any]]],
    *,
    error_cls: type[Exception],
) -> None:
    empty_group_names = [
        table_name for table_name, manifests in manifest_groups.items() if not manifests
    ]
    if empty_group_names:
        raise error_cls(
            "Required manifest group is empty: " + ", ".join(sorted(empty_group_names))
        )


def pipeline_run_ids_from_manifest_groups(
    manifest_groups: dict[str, list[dict[str, Any]]],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                str(manifest["pipeline_run_id"])
                for manifests in manifest_groups.values()
                for manifest in manifests
            }
        )
    )


def flatten_manifest_groups(
    manifest_groups: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    return [
        manifest for manifests in manifest_groups.values() for manifest in manifests
    ]


def expected_manifest_row_count(manifests: Iterable[dict[str, Any]]) -> int:
    return sum(int(manifest["row_count"]) for manifest in manifests)


def _read_reference_text(
    reference: ManifestReference,
    artifact_reader: ArtifactReader,
) -> str:
    if isinstance(reference, ArtifactLocation):
        return artifact_reader.read_text(reference)
    return Path(reference).read_text(encoding="utf-8")
