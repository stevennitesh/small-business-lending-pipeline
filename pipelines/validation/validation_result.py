"""Validation result model and factory helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from pipelines.utils.dates import utc_now_iso
from pipelines.utils.source_resources import SourceIdentity
from pipelines.validation.raw_validation_check_catalog import ValidationCheckDefinition
from pipelines.validation.raw_validation_models import RawManifest
from pipelines.validation.raw_validation_resources import (
    VALIDATION_RESULTS_DATASET_NAME,
    VALIDATION_RESULTS_SOURCE_SYSTEM,
)


VALID_SEVERITIES = frozenset({"fail", "warning", "info"})
VALID_STATUSES = frozenset({"passed", "warning", "failed"})


@dataclass(frozen=True)
class ValidationResult:
    """One raw validation check outcome ready for JSON persistence."""

    pipeline_run_id: str
    validation_check_id: str
    validation_scope: str
    source_system: str
    source_dataset: str
    source_resource_name: str
    check_name: str
    check_type: str
    severity: str
    status: str
    expected_value: Any
    observed_value: Any
    message: str
    checked_at_utc: str

    def __post_init__(self) -> None:
        """Validate severity and status values after dataclass creation."""
        # Validation result JSON is loaded later into raw metadata tables; keep
        # severity/status constrained so failure gating can rely on fixed values.
        if self.severity not in VALID_SEVERITIES:
            raise ValueError(f"Invalid validation severity: {self.severity}")
        if self.status not in VALID_STATUSES:
            raise ValueError(f"Invalid validation status: {self.status}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize the validation result for JSON output."""
        return asdict(self)


def make_validation_result(
    *,
    pipeline_run_id: str,
    validation_check_id: str,
    source_system: str,
    source_dataset: str,
    source_resource_name: str,
    check_name: str,
    check_type: str,
    severity: str,
    passed: bool,
    expected_value: Any,
    observed_value: Any,
    failed_message: str,
    passed_message: str | None = None,
    validation_scope: str = "raw",
) -> ValidationResult:
    """Build a validation result from explicit check metadata."""
    status = "passed" if passed else ("warning" if severity == "warning" else "failed")
    resolved_passed_message = passed_message or f"{check_name} check passed."
    return ValidationResult(
        pipeline_run_id=pipeline_run_id,
        validation_check_id=validation_check_id,
        validation_scope=validation_scope,
        source_system=source_system,
        source_dataset=source_dataset,
        source_resource_name=source_resource_name,
        check_name=check_name,
        check_type=check_type,
        severity=severity,
        status=status,
        expected_value=expected_value,
        observed_value=observed_value,
        message=resolved_passed_message if passed else failed_message,
        checked_at_utc=utc_now_iso(),
    )


def make_check_validation_result(
    *,
    pipeline_run_id: str,
    check_definition: ValidationCheckDefinition,
    source_system: str,
    source_dataset: str,
    source_resource_name: str,
    passed: bool,
    expected_value: Any,
    observed_value: Any,
    failed_message: str,
    passed_message: str | None = None,
    validation_scope: str = "raw",
) -> ValidationResult:
    """Build a validation result from a catalog check definition."""
    return make_validation_result(
        pipeline_run_id=pipeline_run_id,
        validation_check_id=check_definition.validation_check_id,
        validation_scope=validation_scope,
        source_system=source_system,
        source_dataset=source_dataset,
        source_resource_name=source_resource_name,
        check_name=check_definition.check_name,
        check_type=check_definition.check_type,
        severity=check_definition.severity,
        passed=passed,
        expected_value=expected_value,
        observed_value=observed_value,
        failed_message=failed_message,
        passed_message=passed_message,
    )


def make_manifest_validation_result(
    *,
    manifest: RawManifest,
    check_definition: ValidationCheckDefinition,
    passed: bool,
    expected_value: Any,
    observed_value: Any,
    failed_message: str,
) -> ValidationResult:
    """Build a validation result scoped to a raw manifest."""
    return make_check_validation_result(
        pipeline_run_id=str(manifest.get("pipeline_run_id", "unknown")),
        check_definition=check_definition,
        source_system=str(manifest.get("source_system", "unknown")),
        source_dataset=str(manifest.get("dataset_name", "unknown")),
        source_resource_name=str(manifest.get("resource_name", "unknown")),
        passed=passed,
        expected_value=expected_value,
        observed_value=observed_value,
        failed_message=failed_message,
    )


def make_pipeline_validation_result(
    *,
    pipeline_run_id: str,
    check_definition: ValidationCheckDefinition,
    source_resource_name: str,
    passed: bool,
    expected_value: Any,
    observed_value: Any,
    failed_message: str,
    source_system: str = VALIDATION_RESULTS_SOURCE_SYSTEM,
    source_dataset: str = VALIDATION_RESULTS_DATASET_NAME,
    passed_message: str | None = None,
) -> ValidationResult:
    """Build a validation result scoped to pipeline-owned validation artifacts."""
    return make_check_validation_result(
        pipeline_run_id=pipeline_run_id,
        check_definition=check_definition,
        validation_scope="raw",
        source_system=source_system,
        source_dataset=source_dataset,
        source_resource_name=source_resource_name,
        passed=passed,
        expected_value=expected_value,
        observed_value=observed_value,
        failed_message=failed_message,
        passed_message=passed_message,
    )


def make_source_identity_validation_result(
    *,
    check_definition: ValidationCheckDefinition,
    source_identity: SourceIdentity,
    source_resource_name: str,
    passed: bool,
    expected_value: Any,
    observed_value: Any,
    failed_message: str,
    pipeline_run_id: str | None = None,
    manifest: RawManifest | None = None,
) -> ValidationResult:
    """Build a validation result using configured source identity metadata."""
    return make_check_validation_result(
        pipeline_run_id=pipeline_run_id
        or str((manifest or {}).get("pipeline_run_id", "unknown")),
        check_definition=check_definition,
        source_system=source_identity.source_system,
        source_dataset=source_identity.dataset_name,
        source_resource_name=source_resource_name,
        passed=passed,
        expected_value=expected_value,
        observed_value=observed_value,
        failed_message=failed_message,
    )
