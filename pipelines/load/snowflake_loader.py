from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any, Iterable

import snowflake.connector
from dotenv import load_dotenv
from snowflake.connector.pandas_tools import write_pandas

from pipelines.load.raw_load_inputs import (
    ManifestReference,
    expected_manifest_row_count,
    prepare_raw_load_inputs,
)
from pipelines.load.snowflake_errors import SnowflakeRawLoadError
from pipelines.load.snowflake_metadata_load import (
    WritePandasFunc,
    write_raw_metadata_tables,
)
from pipelines.load.snowflake_stage_sources import load_s3_manifest_group
from pipelines.load.snowflake_stage_load import (
    create_s3_stage_load_objects,
)
from pipelines.storage.raw_artifacts import ArtifactReader, parse_s3_uri
from pipelines.utils.dates import utc_now_iso


REQUIRED_SCHEMAS = ("RAW", "STAGING", "INTERMEDIATE", "MARTS", "BI", "AUDIT")

SNOWFLAKE_RAW_TABLES = {
    "raw_sba_7a_foia": "RAW_SBA_7A_FOIA",
    "raw_sba_504_foia": "RAW_SBA_504_FOIA",
    "raw_census_bds_state_year": "RAW_CENSUS_BDS_STATE_YEAR",
    "raw_bls_laus_state_month": "RAW_BLS_LAUS_STATE_MONTH",
    "raw_ingestion_manifest": "RAW_INGESTION_MANIFEST",
    "raw_validation_result": "RAW_VALIDATION_RESULT",
    "raw_pipeline_run_summary": "RAW_PIPELINE_RUN_SUMMARY",
}


@dataclass(frozen=True)
class SnowflakeConfig:
    """Connection and schema configuration for Snowflake raw loads."""

    account: str
    user: str
    password: str
    role: str
    warehouse: str
    database: str
    raw_schema: str = "RAW"
    audit_schema: str = "AUDIT"
    storage_integration: str | None = None

    @classmethod
    def from_env(cls) -> "SnowflakeConfig":
        """Build Snowflake configuration from environment variables."""
        load_dotenv(override=False)
        values = {
            "account": os.getenv("SNOWFLAKE_ACCOUNT"),
            "user": os.getenv("SNOWFLAKE_USER"),
            "password": os.getenv("SNOWFLAKE_PASSWORD"),
            "role": os.getenv("SNOWFLAKE_ROLE"),
            "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE"),
            "database": os.getenv("SNOWFLAKE_DATABASE"),
            "raw_schema": os.getenv("RAW_SCHEMA", "RAW"),
            "audit_schema": os.getenv("SNOWFLAKE_AUDIT_SCHEMA", "AUDIT"),
            "storage_integration": os.getenv("SNOWFLAKE_STORAGE_INTEGRATION"),
        }
        missing = sorted(
            key.upper()
            for key, value in values.items()
            if key not in {"raw_schema", "audit_schema", "storage_integration"}
            and not value
        )
        if missing:
            raise SnowflakeRawLoadError(
                "Missing Snowflake environment variables: "
                + ", ".join(f"SNOWFLAKE_{name}" for name in missing)
            )
        return cls(
            account=str(values["account"]),
            user=str(values["user"]),
            password=str(values["password"]),
            role=str(values["role"]),
            warehouse=str(values["warehouse"]),
            database=str(values["database"]),
            raw_schema=str(values["raw_schema"]),
            audit_schema=str(values["audit_schema"]),
            storage_integration=(
                str(values["storage_integration"])
                if values["storage_integration"]
                else None
            ),
        )

    def connect_kwargs(self) -> dict[str, str]:
        """Return keyword arguments accepted by Snowflake connector."""
        return {
            "account": self.account,
            "user": self.user,
            "password": self.password,
            "role": self.role,
            "warehouse": self.warehouse,
            "database": self.database,
            "schema": self.raw_schema,
        }


@dataclass(frozen=True)
class SnowflakeRawLoadSummary:
    """Summary of a completed Snowflake raw load."""

    database: str
    raw_schema: str
    audit_schema: str
    table_row_counts: dict[str, int]
    pipeline_run_ids: tuple[str, ...]
    loaded_at_utc: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize the Snowflake raw load summary."""
        return asdict(self)


def connect_to_snowflake(config: SnowflakeConfig):
    """Open a Snowflake connection from raw-load configuration."""
    return snowflake.connector.connect(**config.connect_kwargs())


def load_raw_extracts_to_snowflake_from_s3(
    *,
    connection,
    database: str,
    raw_schema: str = "RAW",
    audit_schema: str = "AUDIT",
    sba_7a_manifest_paths: Iterable[ManifestReference],
    sba_504_manifest_paths: Iterable[ManifestReference],
    census_bds_manifest_paths: Iterable[ManifestReference],
    bls_laus_manifest_paths: Iterable[ManifestReference],
    validation_result_paths: Iterable[ManifestReference],
    write_pandas_func: WritePandasFunc = write_pandas,
    stage_name: str = "RAW_S3_STAGE",
    storage_integration: str | None = None,
    s3_client: Any | None = None,
) -> SnowflakeRawLoadSummary:
    """Production-style cloud raw load from S3-backed artifacts."""
    artifact_reader = ArtifactReader(s3_client=s3_client)
    # Snowflake loads only from manifests and validation outputs already promoted
    # to S3, so all references are read through the artifact route reader.
    prepared_inputs = prepare_raw_load_inputs(
        sba_7a_manifest_paths=sba_7a_manifest_paths,
        sba_504_manifest_paths=sba_504_manifest_paths,
        census_bds_manifest_paths=census_bds_manifest_paths,
        bls_laus_manifest_paths=bls_laus_manifest_paths,
        validation_result_paths=validation_result_paths,
        error_cls=SnowflakeRawLoadError,
        missing_validation_message="At least one validation result file is required.",
        artifact_reader=artifact_reader,
    )
    manifest_groups = prepared_inputs.manifest_groups
    _require_s3_backed_manifests(manifest_groups)
    bucket = _single_s3_bucket(manifest_groups)

    _create_required_schemas(
        connection,
        raw_schema=raw_schema,
        audit_schema=audit_schema,
    )
    create_s3_stage_load_objects(
        connection,
        raw_schema=raw_schema,
        bucket=bucket,
        stage_name=stage_name,
        storage_integration=storage_integration,
    )

    table_row_counts: dict[str, int] = {}
    for source_table, manifests in manifest_groups.items():
        table_name = SNOWFLAKE_RAW_TABLES[source_table]
        load_s3_manifest_group(
            connection,
            raw_schema=raw_schema,
            source_table=source_table,
            table_name=table_name,
            manifests=manifests,
            stage_name=stage_name,
            s3_client=s3_client,
        )
        expected_row_count = expected_manifest_row_count(manifests)
        row_count = _snowflake_table_count(connection, raw_schema, table_name)
        if row_count != expected_row_count:
            raise SnowflakeRawLoadError(
                f"Row count mismatch for {raw_schema}.{table_name}: "
                f"loaded {row_count}, expected {expected_row_count}"
            )
        table_row_counts[f"{raw_schema}.{table_name}"] = row_count

    loaded_at_utc = utc_now_iso()
    write_raw_metadata_tables(
        connection=connection,
        database=database,
        raw_schema=raw_schema,
        raw_table_names=SNOWFLAKE_RAW_TABLES,
        manifest_groups=manifest_groups,
        validation_results=prepared_inputs.validation_results,
        pipeline_run_ids=prepared_inputs.pipeline_run_ids,
        loaded_at_utc=loaded_at_utc,
        load_pattern="s3_stage_copy",
        table_row_counts=table_row_counts,
        write_pandas_func=write_pandas_func,
    )

    return SnowflakeRawLoadSummary(
        database=database,
        raw_schema=raw_schema,
        audit_schema=audit_schema,
        table_row_counts=table_row_counts,
        pipeline_run_ids=prepared_inputs.pipeline_run_ids,
        loaded_at_utc=loaded_at_utc,
    )


def _create_required_schemas(
    connection,
    *,
    raw_schema: str = "RAW",
    audit_schema: str = "AUDIT",
) -> None:
    """Create the schemas needed by the raw load route."""
    schema_names = {raw_schema, audit_schema}
    # The default local-first model expects all dbt schemas; custom raw/audit
    # schemas keep the bootstrap limited to the explicitly requested schemas.
    if raw_schema.upper() == "RAW" and audit_schema.upper() == "AUDIT":
        schema_names.update(REQUIRED_SCHEMAS)

    with connection.cursor() as cursor:
        for schema_name in sorted(schema_names):
            cursor.execute(f"create schema if not exists {schema_name}")


def _require_s3_backed_manifests(
    manifest_groups: dict[str, list[dict[str, Any]]],
) -> None:
    """Require every manifest to point at raw data already stored in S3."""
    non_s3_resources = [
        str(manifest.get("resource_name"))
        for manifests in manifest_groups.values()
        for manifest in manifests
        if str(manifest.get("storage_backend", "local")).lower() != "s3"
    ]
    if non_s3_resources:
        raise SnowflakeRawLoadError(
            "Snowflake S3 raw load requires S3-backed manifests: "
            + ", ".join(sorted(non_s3_resources))
        )


def _single_s3_bucket(manifest_groups: dict[str, list[dict[str, Any]]]) -> str:
    """Return the one S3 bucket shared by all manifest raw URIs."""
    buckets = {
        parse_s3_uri(str(manifest.get("raw_uri") or manifest["s3_raw_uri"])).bucket
        for manifests in manifest_groups.values()
        for manifest in manifests
    }
    if len(buckets) != 1:
        raise SnowflakeRawLoadError(
            "Snowflake S3 raw load requires one S3 bucket, found: "
            + ", ".join(sorted(buckets))
        )
    return next(iter(buckets))


def _snowflake_table_count(connection, raw_schema: str, table_name: str) -> int:
    """Return the row count for a Snowflake raw table."""
    with connection.cursor() as cursor:
        cursor.execute(f"select count(*) from {raw_schema}.{table_name}")
        row = cursor.fetchone()
    return int(row[0])
