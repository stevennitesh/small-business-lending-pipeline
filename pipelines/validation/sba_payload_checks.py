from __future__ import annotations

from pathlib import Path
from typing import Iterable

from pipelines.storage.raw_artifacts import RawArtifactReader
from pipelines.utils.config import SourceIdentity
from pipelines.utils.source_resources import SBA_FOIA_SOURCE_IDENTITY
from pipelines.validation.raw_validation_check_catalog import (
    SBA_REQUIRED_RESOURCES_FOUND,
    SBA_REQUIRED_RESOURCES_READABLE,
)
from pipelines.validation.raw_validation_models import RawManifest
from pipelines.validation.raw_validation_resources import SBA_REQUIRED_RESOURCES_NAME
from pipelines.validation.validation_result import (
    ValidationResult,
    make_source_identity_validation_result,
)


DEFAULT_SBA_IDENTITY = SBA_FOIA_SOURCE_IDENTITY


def check_sba_required_resources(
    manifests: Iterable[RawManifest],
    *,
    required_resource_names: list[str],
    source_identity: SourceIdentity = DEFAULT_SBA_IDENTITY,
    artifact_reader: RawArtifactReader | None = None,
    raw_file_exists_resource_names: set[str] | None = None,
) -> list[ValidationResult]:
    manifest_list = list(manifests)
    resources_by_name = {
        str(manifest.get("resource_name")): manifest
        for manifest in manifest_list
    }
    missing_resources = sorted(set(required_resource_names) - set(resources_by_name))
    unreadable_resources = _unreadable_required_resources(
        resources_by_name,
        required_resource_names=required_resource_names,
        artifact_reader=artifact_reader,
        raw_file_exists_resource_names=raw_file_exists_resource_names,
    )
    base_manifest = manifest_list[0] if manifest_list else {}
    return [
        make_source_identity_validation_result(
            manifest=base_manifest,
            source_identity=source_identity,
            source_resource_name=SBA_REQUIRED_RESOURCES_NAME,
            check_definition=SBA_REQUIRED_RESOURCES_FOUND,
            passed=missing_resources == [],
            expected_value=required_resource_names,
            observed_value={"missing_resources": missing_resources},
            failed_message="Required SBA resources are missing.",
        ),
        make_source_identity_validation_result(
            manifest=base_manifest,
            source_identity=source_identity,
            source_resource_name=SBA_REQUIRED_RESOURCES_NAME,
            check_definition=SBA_REQUIRED_RESOURCES_READABLE,
            passed=unreadable_resources == [],
            expected_value="all required raw files readable",
            observed_value={"unreadable_resources": unreadable_resources},
            failed_message="One or more required SBA raw files are unreadable.",
        ),
    ]


def _manifest_artifact_exists(
    manifest: RawManifest,
    *,
    artifact_reader: RawArtifactReader | None,
) -> bool:
    if artifact_reader is not None:
        return artifact_reader.exists(manifest)
    local_raw_path = manifest.get("local_raw_path")
    if not local_raw_path:
        return False
    return Path(str(local_raw_path)).is_file()


def _unreadable_required_resources(
    resources_by_name: dict[str, RawManifest],
    *,
    required_resource_names: list[str],
    artifact_reader: RawArtifactReader | None,
    raw_file_exists_resource_names: set[str] | None,
) -> list[str]:
    required_resources = set(required_resource_names)
    if raw_file_exists_resource_names is not None:
        return sorted(
            resource_name
            for resource_name in resources_by_name
            if resource_name in required_resources
            and resource_name not in raw_file_exists_resource_names
        )
    return sorted(
        resource_name
        for resource_name, manifest in resources_by_name.items()
        if resource_name in required_resources
        and not _manifest_artifact_exists(manifest, artifact_reader=artifact_reader)
    )
