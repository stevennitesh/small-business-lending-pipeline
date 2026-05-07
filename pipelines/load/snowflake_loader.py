from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

import pandas as pd
import snowflake.connector
from dotenv import load_dotenv
from snowflake.connector.pandas_tools import write_pandas

from pipelines.utils.dates import utc_now_iso
from pipelines.validation.validation_result import (
    ValidationFailedError,
    ValidationResult,
    assert_no_blocking_failures,
)


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

SOURCE_TABLES = {
    "raw_sba_7a_foia": "sba_7a",
    "raw_sba_504_foia": "sba_504",
    "raw_census_bds_state_year": "census_bds",
    "raw_bls_laus_state_month": "bls_laus",
}


class SnowflakeRawLoadError(RuntimeError):
    pass


@dataclass(frozen=True)
class SnowflakeConfig:
    account: str
    user: str
    password: str
    role: str
    warehouse: str
    database: str
    raw_schema: str = "RAW"
    audit_schema: str = "AUDIT"

    @classmethod
    def from_env(cls) -> "SnowflakeConfig":
        load_dotenv(override=True)
        values = {
            "account": os.getenv("SNOWFLAKE_ACCOUNT"),
            "user": os.getenv("SNOWFLAKE_USER"),
            "password": os.getenv("SNOWFLAKE_PASSWORD"),
            "role": os.getenv("SNOWFLAKE_ROLE"),
            "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE"),
            "database": os.getenv("SNOWFLAKE_DATABASE"),
            "raw_schema": os.getenv("SNOWFLAKE_SCHEMA", "RAW"),
            "audit_schema": os.getenv("SNOWFLAKE_AUDIT_SCHEMA", "AUDIT"),
        }
        missing = sorted(
            key.upper()
            for key, value in values.items()
            if key not in {"raw_schema", "audit_schema"} and not value
        )
        if missing:
            raise SnowflakeRawLoadError(
                "Missing Snowflake environment variables: "
                + ", ".join(f"SNOWFLAKE_{name}" for name in missing)
            )
        return cls(**{key: str(value) for key, value in values.items()})

    def connect_kwargs(self) -> dict[str, str]:
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
    database: str
    raw_schema: str
    audit_schema: str
    table_row_counts: dict[str, int]
    pipeline_run_ids: tuple[str, ...]
    loaded_at_utc: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


WritePandasFunc = Callable[..., tuple[bool, int, int, list[Any]]]


def connect_to_snowflake(config: SnowflakeConfig):
    return snowflake.connector.connect(**config.connect_kwargs())


def load_raw_extracts_to_snowflake(
    *,
    connection,
    database: str,
    raw_schema: str = "RAW",
    audit_schema: str = "AUDIT",
    sba_7a_manifest_paths: Iterable[Path | str],
    sba_504_manifest_paths: Iterable[Path | str],
    census_bds_manifest_paths: Iterable[Path | str],
    bls_laus_manifest_paths: Iterable[Path | str],
    validation_result_paths: Iterable[Path | str],
    write_pandas_func: WritePandasFunc = write_pandas,
) -> SnowflakeRawLoadSummary:
    validation_results = _load_validation_results(validation_result_paths)
    try:
        assert_no_blocking_failures(validation_results)
    except ValidationFailedError as exc:
        raise SnowflakeRawLoadError(str(exc)) from exc

    manifest_groups = {
        "raw_sba_7a_foia": _load_manifests(sba_7a_manifest_paths),
        "raw_sba_504_foia": _load_manifests(sba_504_manifest_paths),
        "raw_census_bds_state_year": _load_manifests(census_bds_manifest_paths),
        "raw_bls_laus_state_month": _load_manifests(bls_laus_manifest_paths),
    }
    pipeline_run_ids = tuple(
        sorted(
            {
                str(manifest["pipeline_run_id"])
                for manifests in manifest_groups.values()
                for manifest in manifests
            }
        )
    )
    _create_required_schemas(connection)

    table_row_counts: dict[str, int] = {}
    for source_table, manifests in manifest_groups.items():
        frame = _load_source_frame(source_table, manifests)
        table_name = SNOWFLAKE_RAW_TABLES[source_table]
        _write_frame(
            connection=connection,
            frame=frame,
            database=database,
            schema=raw_schema,
            table_name=table_name,
            write_pandas_func=write_pandas_func,
        )
        row_count = len(frame)
        expected_row_count = sum(int(manifest["row_count"]) for manifest in manifests)
        if row_count != expected_row_count:
            raise SnowflakeRawLoadError(
                f"Row count mismatch for {raw_schema}.{table_name}: "
                f"loaded {row_count}, expected {expected_row_count}"
            )
        table_row_counts[f"{raw_schema}.{table_name}"] = row_count

    manifest_frame = _snowflake_frame(
        _normalize_records(
            [
                manifest
                for manifests in manifest_groups.values()
                for manifest in manifests
            ]
        )
    )
    _write_frame(
        connection=connection,
        frame=manifest_frame,
        database=database,
        schema=raw_schema,
        table_name=SNOWFLAKE_RAW_TABLES["raw_ingestion_manifest"],
        write_pandas_func=write_pandas_func,
    )
    table_row_counts[f"{raw_schema}.{SNOWFLAKE_RAW_TABLES['raw_ingestion_manifest']}"] = len(
        manifest_frame
    )

    validation_frame = _snowflake_frame(
        _normalize_records([result.to_dict() for result in validation_results])
    )
    _write_frame(
        connection=connection,
        frame=validation_frame,
        database=database,
        schema=raw_schema,
        table_name=SNOWFLAKE_RAW_TABLES["raw_validation_result"],
        write_pandas_func=write_pandas_func,
    )
    table_row_counts[f"{raw_schema}.{SNOWFLAKE_RAW_TABLES['raw_validation_result']}"] = len(
        validation_frame
    )

    loaded_at_utc = utc_now_iso()
    summary_frame = _snowflake_frame(
        pd.DataFrame(
            [
                {
                    "pipeline_run_ids": ",".join(pipeline_run_ids),
                    "loaded_at_utc": loaded_at_utc,
                    "raw_table_count": len(SOURCE_TABLES),
                    "validation_status": "passed",
                    "load_pattern": "python_connector_fallback",
                }
            ]
        )
    )
    _write_frame(
        connection=connection,
        frame=summary_frame,
        database=database,
        schema=raw_schema,
        table_name=SNOWFLAKE_RAW_TABLES["raw_pipeline_run_summary"],
        write_pandas_func=write_pandas_func,
    )
    table_row_counts[
        f"{raw_schema}.{SNOWFLAKE_RAW_TABLES['raw_pipeline_run_summary']}"
    ] = len(summary_frame)

    return SnowflakeRawLoadSummary(
        database=database,
        raw_schema=raw_schema,
        audit_schema=audit_schema,
        table_row_counts=table_row_counts,
        pipeline_run_ids=pipeline_run_ids,
        loaded_at_utc=loaded_at_utc,
    )


def _create_required_schemas(connection) -> None:
    with connection.cursor() as cursor:
        for schema_name in REQUIRED_SCHEMAS:
            cursor.execute(f"create schema if not exists {schema_name}")


def _write_frame(
    *,
    connection,
    frame: pd.DataFrame,
    database: str,
    schema: str,
    table_name: str,
    write_pandas_func: WritePandasFunc,
) -> None:
    success, _, _, output = write_pandas_func(
        connection,
        frame,
        table_name,
        database=database,
        schema=schema,
        auto_create_table=True,
        overwrite=True,
        quote_identifiers=False,
    )
    if not success:
        raise SnowflakeRawLoadError(f"Snowflake write failed for {schema}.{table_name}: {output}")


def _load_source_frame(table_name: str, manifests: list[dict[str, Any]]) -> pd.DataFrame:
    if table_name in {"raw_sba_7a_foia", "raw_sba_504_foia"}:
        frames = [
            _with_metadata(pd.read_csv(manifest["local_raw_path"]), manifest)
            for manifest in manifests
        ]
        return _snowflake_frame(pd.concat(frames, ignore_index=True) if frames else pd.DataFrame())

    if table_name == "raw_census_bds_state_year":
        frames = [
            _with_metadata(_read_census_bds_json(Path(manifest["local_raw_path"])), manifest)
            for manifest in manifests
        ]
        return _snowflake_frame(pd.concat(frames, ignore_index=True) if frames else pd.DataFrame())

    if table_name == "raw_bls_laus_state_month":
        frames = [
            _with_metadata(_read_bls_laus_json(Path(manifest["local_raw_path"])), manifest)
            for manifest in manifests
        ]
        return _snowflake_frame(pd.concat(frames, ignore_index=True) if frames else pd.DataFrame())

    raise SnowflakeRawLoadError(f"Unsupported raw table: {table_name}")


def _read_census_bds_json(path: Path) -> pd.DataFrame:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if len(payload) < 1:
        return pd.DataFrame()
    return pd.DataFrame(payload[1:], columns=payload[0])


def _read_bls_laus_json(path: Path) -> pd.DataFrame:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return pd.DataFrame(payload.get("normalized_rows", []))


def _with_metadata(frame: pd.DataFrame, manifest: dict[str, Any]) -> pd.DataFrame:
    enriched = frame.copy()
    enriched["pipeline_run_id"] = manifest["pipeline_run_id"]
    enriched["source_system"] = manifest["source_system"]
    enriched["source_dataset"] = manifest["dataset_name"]
    enriched["source_resource_name"] = manifest["resource_name"]
    enriched["ingestion_date"] = manifest["ingestion_date"]
    enriched["raw_file_path"] = manifest["local_raw_path"]
    enriched["s3_raw_uri"] = manifest["s3_raw_uri"]
    enriched["sha256_checksum"] = manifest["sha256_checksum"]
    return enriched


def _load_manifests(paths: Iterable[Path | str]) -> list[dict[str, Any]]:
    return [
        json.loads(Path(path).read_text(encoding="utf-8"))
        for path in paths
    ]


def _load_validation_results(paths: Iterable[Path | str]) -> list[ValidationResult]:
    validation_paths = list(paths)
    if not validation_paths:
        raise SnowflakeRawLoadError("At least one validation result file is required.")

    results: list[ValidationResult] = []
    for path in validation_paths:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        results.extend(ValidationResult(**record) for record in payload)
    return results


def _normalize_records(records: list[dict[str, Any]]) -> pd.DataFrame:
    normalized_records = [
        {
            key: json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else value
            for key, value in record.items()
        }
        for record in records
    ]
    return pd.DataFrame(normalized_records)


def _snowflake_frame(frame: pd.DataFrame) -> pd.DataFrame:
    snowflake_frame = frame.copy()
    snowflake_frame.columns = [str(column).upper() for column in snowflake_frame.columns]
    return snowflake_frame


def main() -> None:
    parser = argparse.ArgumentParser(description="Load validated raw artifacts into Snowflake.")
    parser.add_argument("--sba-7a-manifest-path", action="append", required=True)
    parser.add_argument("--sba-504-manifest-path", action="append", required=True)
    parser.add_argument("--census-bds-manifest-path", action="append", required=True)
    parser.add_argument("--bls-laus-manifest-path", action="append", required=True)
    parser.add_argument("--validation-result-path", action="append", required=True)
    args = parser.parse_args()

    config = SnowflakeConfig.from_env()
    connection = connect_to_snowflake(config)
    try:
        summary = load_raw_extracts_to_snowflake(
            connection=connection,
            database=config.database,
            raw_schema=config.raw_schema,
            audit_schema=config.audit_schema,
            sba_7a_manifest_paths=args.sba_7a_manifest_path,
            sba_504_manifest_paths=args.sba_504_manifest_path,
            census_bds_manifest_paths=args.census_bds_manifest_path,
            bls_laus_manifest_paths=args.bls_laus_manifest_path,
            validation_result_paths=args.validation_result_path,
        )
    finally:
        connection.close()
    print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
