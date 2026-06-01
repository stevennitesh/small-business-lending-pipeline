from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

from pipelines.storage.raw_artifacts import RawArtifactReader
from pipelines.utils.config import SourceIdentity
from pipelines.validation.raw_manifest_rule_checks import (
    check_required_manifest_resource,
)
from pipelines.validation.raw_validation_models import JsonPayload, RawManifestIndex
from pipelines.validation.validation_result import ValidationResult


PayloadValidator = Callable[[JsonPayload], list[ValidationResult]]


@dataclass(frozen=True)
class RequiredPayloadResource:
    manifest_result: ValidationResult
    payload: JsonPayload


def validate_required_json_payload_resource(
    manifest_index: RawManifestIndex,
    *,
    resource_name: str,
    pipeline_run_id: str,
    source_identity: SourceIdentity,
    artifact_reader: RawArtifactReader,
    validate_payload: PayloadValidator,
) -> list[ValidationResult]:
    payload_resource = required_payload_resource(
        manifest_index,
        resource_name=resource_name,
        pipeline_run_id=pipeline_run_id,
        source_identity=source_identity,
        artifact_reader=artifact_reader,
    )
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
    return json.loads(
        artifact_reader.read_text(manifest_index.manifest_for(resource_name))
    )
