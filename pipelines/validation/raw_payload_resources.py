"""Shared helpers for validating required JSON raw payload resources."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

from pipelines.storage.raw_artifacts import RawArtifactReader
from pipelines.utils.source_resources import SourceIdentity
from pipelines.validation.raw_manifest_rule_checks import (
    check_required_manifest_resource,
)
from pipelines.validation.raw_validation_models import JsonPayload, RawManifestIndex
from pipelines.validation.raw_validation_check_catalog import RAW_PAYLOAD_READABLE_JSON
from pipelines.validation.validation_result import (
    ValidationResult,
    make_source_identity_validation_result,
)


PayloadValidator = Callable[[JsonPayload], list[ValidationResult]]


@dataclass(frozen=True)
class RequiredPayloadResource:
    """Manifest check result plus decoded payload when the manifest exists."""

    manifest_result: ValidationResult
    payload: JsonPayload | None


def validate_required_json_payload_resource(
    manifest_index: RawManifestIndex,
    *,
    resource_name: str,
    pipeline_run_id: str,
    source_identity: SourceIdentity,
    artifact_reader: RawArtifactReader,
    validate_payload: PayloadValidator,
) -> list[ValidationResult]:
    """Validate a required manifest before running payload-specific checks."""
    try:
        payload_resource = required_payload_resource(
            manifest_index,
            resource_name=resource_name,
            pipeline_run_id=pipeline_run_id,
            source_identity=source_identity,
            artifact_reader=artifact_reader,
        )
    except (json.JSONDecodeError, UnicodeDecodeError, FileNotFoundError) as exc:
        return [
            make_source_identity_validation_result(
                pipeline_run_id=pipeline_run_id,
                source_identity=source_identity,
                source_resource_name=resource_name,
                check_definition=RAW_PAYLOAD_READABLE_JSON,
                passed=False,
                expected_value="readable JSON payload",
                observed_value=str(exc),
                failed_message="Raw JSON payload cannot be read or decoded.",
            )
        ]
    validation_results = [payload_resource.manifest_result]
    if payload_resource.manifest_result.status == "passed":
        validation_results.extend(validate_payload(payload_resource.payload))
    return validation_results


def required_payload_resource(
    manifest_index: RawManifestIndex,
    *,
    resource_name: str,
    pipeline_run_id: str,
    source_identity: SourceIdentity,
    artifact_reader: RawArtifactReader,
) -> RequiredPayloadResource:
    """Load a required JSON payload only when its manifest is present."""
    manifest_result = check_required_manifest_resource(
        manifest_index.manifests,
        resource_name=resource_name,
        pipeline_run_id=pipeline_run_id,
        source_identity=source_identity,
    )
    payload = (
        read_payload_json(manifest_index, resource_name, artifact_reader)
        if manifest_result.status == "passed"
        else None
    )
    return RequiredPayloadResource(
        manifest_result=manifest_result,
        payload=payload,
    )


def read_payload_json(
    manifest_index: RawManifestIndex,
    resource_name: str,
    artifact_reader: RawArtifactReader,
) -> JsonPayload:
    """Read and decode the JSON payload referenced by a manifest resource."""
    return json.loads(
        artifact_reader.read_text(manifest_index.manifest_for(resource_name))
    )
