"""Raw validation check definitions and stable check IDs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ValidationCheckDefinition:
    """Catalog entry used to create consistent validation results."""

    validation_check_id: str
    check_name: str
    check_type: str
    severity: str


RAW_FILE_EXISTS = ValidationCheckDefinition(
    validation_check_id="RAW_001",
    check_name="Raw file exists",
    check_type="completeness",
    severity="fail",
)
RAW_FILE_SIZE_POSITIVE = ValidationCheckDefinition(
    validation_check_id="RAW_002",
    check_name="Raw file size is positive",
    check_type="completeness",
    severity="fail",
)
RAW_CHECKSUM_GENERATED = ValidationCheckDefinition(
    validation_check_id="RAW_003",
    check_name="SHA-256 checksum generated",
    check_type="lineage",
    severity="fail",
)
RAW_MANIFEST_CREATED = ValidationCheckDefinition(
    validation_check_id="RAW_004",
    check_name="Manifest created",
    check_type="lineage",
    severity="fail",
)
RAW_REQUIRED_METADATA = ValidationCheckDefinition(
    validation_check_id="RAW_005",
    check_name="Required metadata populated",
    check_type="lineage",
    severity="fail",
)
RAW_ROW_COUNT_CAPTURED = ValidationCheckDefinition(
    validation_check_id="RAW_006",
    check_name="Row count captured",
    check_type="completeness",
    severity="fail",
)
RAW_SCHEMA_HASH_GENERATED = ValidationCheckDefinition(
    validation_check_id="RAW_007",
    check_name="Schema hash generated",
    check_type="lineage",
    severity="warning",
)
RAW_COLUMN_COUNT_CAPTURED = ValidationCheckDefinition(
    validation_check_id="RAW_008",
    check_name="Column count captured",
    check_type="completeness",
    severity="warning",
)
RAW_VALIDATION_RESULT_CREATED = ValidationCheckDefinition(
    validation_check_id="RAW_009",
    check_name="Validation result created",
    check_type="lineage",
    severity="fail",
)
RAW_MANIFEST_SOURCE_IDENTITY = ValidationCheckDefinition(
    validation_check_id="RAW_010",
    check_name="Manifest source identity matches config",
    check_type="lineage",
    severity="fail",
)
RAW_REQUIRED_MANIFEST_RESOURCE = ValidationCheckDefinition(
    validation_check_id="RAW_011",
    check_name="Required raw manifest resource present",
    check_type="lineage",
    severity="fail",
)
RAW_CLOUD_MANIFEST_STORAGE = ValidationCheckDefinition(
    validation_check_id="RAW_012",
    check_name="Cloud raw manifest is S3-backed",
    check_type="lineage",
    severity="fail",
)
RAW_ARTIFACT_IDENTITY = ValidationCheckDefinition(
    validation_check_id="RAW_013",
    check_name="Raw artifact identity populated",
    check_type="lineage",
    severity="fail",
)
RAW_MANIFEST_READABLE_JSON = ValidationCheckDefinition(
    validation_check_id="RAW_014",
    check_name="Manifest readable JSON",
    check_type="lineage",
    severity="fail",
)

SBA_REQUIRED_RESOURCES_FOUND = ValidationCheckDefinition(
    validation_check_id="SBA_RAW_001",
    check_name="SBA required resources found",
    check_type="completeness",
    severity="fail",
)
SBA_REQUIRED_RESOURCES_READABLE = ValidationCheckDefinition(
    validation_check_id="SBA_RAW_002",
    check_name="SBA required resources readable",
    check_type="validity",
    severity="fail",
)

BDS_REQUIRED_VARIABLES = ValidationCheckDefinition(
    validation_check_id="BDS_RAW_001",
    check_name="Census BDS required variables returned",
    check_type="validity",
    severity="fail",
)
BDS_STATE_COVERAGE = ValidationCheckDefinition(
    validation_check_id="BDS_RAW_002",
    check_name="Census BDS state coverage",
    check_type="completeness",
    severity="fail",
)

BLS_EXPECTED_SERIES = ValidationCheckDefinition(
    validation_check_id="BLS_RAW_001",
    check_name="BLS expected series returned",
    check_type="completeness",
    severity="fail",
)
BLS_MONTHLY_PERIODS = ValidationCheckDefinition(
    validation_check_id="BLS_RAW_002",
    check_name="BLS monthly periods valid",
    check_type="validity",
    severity="fail",
)
BLS_NUMERIC_VALUES = ValidationCheckDefinition(
    validation_check_id="BLS_RAW_003",
    check_name="BLS values numeric",
    check_type="validity",
    severity="fail",
)
BLS_VALUE_RANGE = ValidationCheckDefinition(
    validation_check_id="BLS_RAW_004",
    check_name="BLS unemployment rates in configured range",
    check_type="validity",
    severity="fail",
)
