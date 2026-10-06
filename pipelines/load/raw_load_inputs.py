from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from pipelines.storage.raw_artifacts import ArtifactLocation, ArtifactReader
from pipelines.utils.manifest import normalize_manifest_storage_fields
from pipelines.validation.raw_validation_check_catalog import (
    RAW_CHECKSUM_GENERATED,
    RAW_FILE_EXISTS,
)
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
    # Validation must pass before callers replace destination raw tables.
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
    assert_manifest_validation_matches(
        manifest_groups, validation_results, error_cls=error_cls
    )
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
    """Load source manifests into the raw table groups expected by loaders."""
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
    """Read manifest JSON documents from local paths or artifact locations."""
    reader = artifact_reader or ArtifactReader()
    return [json.loads(_read_reference_text(path, reader)) for path in paths]


def load_validation_results(
    paths: Iterable[ManifestReference],
    *,
    error_cls: type[Exception],
    missing_message: str,
    artifact_reader: ArtifactReader | None = None,
) -> list[ValidationResult]:
    """Read validation-result JSON documents and expand their records."""
    validation_paths = list(paths)
    if not validation_paths:
        raise error_cls(missing_message)

    reader = artifact_reader or ArtifactReader()
    results: list[ValidationResult] = []
    for path in validation_paths:
        payload = json.loads(_read_reference_text(path, reader))
        if not payload:
            raise error_cls(f"Raw validation result file is empty: {path}")
        results.extend(ValidationResult(**record) for record in payload)
    return results


def assert_validation_passed(
    validation_results: list[ValidationResult],
    *,
    error_cls: type[Exception],
) -> None:
    """Raise the loader-specific error type when validation blocks loading."""
    try:
        assert_no_blocking_failures(validation_results)
    except ValidationFailedError as exc:
        raise error_cls(str(exc)) from exc


def require_manifest_groups(
    manifest_groups: dict[str, list[dict[str, Any]]],
    *,
    error_cls: type[Exception],
) -> None:
    """Require every raw source table to have at least one manifest."""
    empty_group_names = [
        table_name for table_name, manifests in manifest_groups.items() if not manifests
    ]
    if empty_group_names:
        raise error_cls(
            "Required manifest group is empty: " + ", ".join(sorted(empty_group_names))
        )


def assert_manifest_validation_matches(
    manifest_groups: dict[str, list[dict[str, Any]]],
    validation_results: list[ValidationResult],
    *,
    error_cls: type[Exception],
) -> None:
    """Require passing raw evidence for each selected run, resource and artifact."""
    passed_results = [
        result
        for result in validation_results
        if result.validation_scope == "raw"
        and result.severity == "fail"
        and result.status == "passed"
    ]
    seen_artifacts = set()
    for manifest in flatten_manifest_groups(manifest_groups):
        identity = (
            manifest.get("pipeline_run_id"),
            manifest.get("resource_name"),
            normalize_manifest_storage_fields(manifest).get("raw_uri"),
        )
        if identity in seen_artifacts:
            raise error_cls(
                f"Duplicate raw manifest selected: {manifest.get('resource_name')}"
            )
        seen_artifacts.add(identity)
        normalized_manifest = normalize_manifest_storage_fields(manifest)
        raw_uri = normalized_manifest.get("raw_uri")
        checksum = manifest.get("sha256_checksum")
        matching_results = [
            result
            for result in passed_results
            if result.pipeline_run_id == manifest.get("pipeline_run_id")
            and result.source_system == manifest.get("source_system")
            and result.source_dataset == manifest.get("dataset_name")
            and result.source_resource_name == manifest.get("resource_name")
        ]
        has_artifact_evidence = bool(raw_uri) and any(
            result.validation_check_id == RAW_FILE_EXISTS.validation_check_id
            and result.observed_value == raw_uri
            for result in matching_results
        )
        has_checksum_evidence = bool(checksum) and any(
            result.validation_check_id == RAW_CHECKSUM_GENERATED.validation_check_id
            and result.expected_value == checksum
            and result.observed_value == checksum
            for result in matching_results
        )
        if not (has_artifact_evidence and has_checksum_evidence):
            raise error_cls(
                "Raw validation evidence does not match selected manifest: "
                f"{manifest.get('resource_name')} "
                f"(pipeline_run_id={manifest.get('pipeline_run_id')}). "
                "Matching passed raw artifact and checksum checks are required."
            )


def pipeline_run_ids_from_manifest_groups(
    manifest_groups: dict[str, list[dict[str, Any]]],
) -> tuple[str, ...]:
    """Return the unique pipeline run IDs represented by manifest groups."""
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
    """Flatten table-keyed manifest groups into manifest order by group."""
    return [
        manifest for manifests in manifest_groups.values() for manifest in manifests
    ]


def expected_manifest_row_count(manifests: Iterable[dict[str, Any]]) -> int:
    """Return the total row count promised by a manifest collection."""
    return sum(int(manifest["row_count"]) for manifest in manifests)


def _read_reference_text(
    reference: ManifestReference,
    artifact_reader: ArtifactReader,
) -> str:
    """Read a local or routed artifact reference as UTF-8 text."""
    if isinstance(reference, ArtifactLocation):
        return artifact_reader.read_text(reference)
    return Path(reference).read_text(encoding="utf-8")
