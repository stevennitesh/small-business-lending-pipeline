from __future__ import annotations

import argparse
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

import requests

from pipelines.utils.config import SourceIdentity, load_yaml_file
from pipelines.utils.dates import (
    format_utc_timestamp,
    ingestion_date_from_timestamp,
    utc_now,
)
from pipelines.storage.raw_artifacts import LocalRawArtifactStore, S3RawArtifactStore
from pipelines.utils.hashing import hash_bytes, hash_schema
from pipelines.utils.manifest import ExtractionManifest, ExtractionResult, write_manifest


DEFAULT_S3_BUCKET = "small-business-lending-pipeline"
RESOURCE_NAME = "bds_state_year"
RESOURCE_GRAIN = "grain=state_year"
DEFAULT_SOURCE_IDENTITY = SourceIdentity(
    source_system="census",
    dataset_name="bds",
)


@dataclass(frozen=True)
class CensusBDSConfig:
    endpoint: str
    geography: str
    start_year: int
    required_variables: tuple[str, ...]


@dataclass(frozen=True)
class CensusBDSResponseSummary:
    header: list[str]
    row_count: int
    latest_available_year: int


@dataclass(frozen=True)
class CensusBDSExtractionSummary:
    result: ExtractionResult
    manifest_path: Path
    latest_available_year: int


def load_census_bds_config(
    config_path: Path | str = "config/census_bds_variables.yml",
) -> CensusBDSConfig:
    return parse_census_bds_config(load_yaml_file(Path(config_path))["census_bds"])


def parse_census_bds_config(config: Mapping[str, Any]) -> CensusBDSConfig:
    variables = tuple(
        str(variable["name"])
        for variable in config["variables"]
        if bool(variable.get("required", False))
    )
    return CensusBDSConfig(
        endpoint=str(config["endpoint"]),
        geography=str(config["geography"]),
        start_year=int(config["start_year"]),
        required_variables=variables,
    )


def build_census_bds_params(
    config: CensusBDSConfig,
    *,
    start_year: int | None = None,
    end_year: int | None = None,
    api_key: str | None = None,
) -> dict[str, str]:
    resolved_start_year = start_year or config.start_year
    resolved_end_year = end_year or datetime.now().year
    query_variables = tuple(
        variable
        for variable in config.required_variables
        if variable != config.geography
    )
    params = {
        "get": ",".join(query_variables),
        "for": f"{config.geography}:*",
        "time": _time_predicate(resolved_start_year, resolved_end_year),
    }
    if api_key:
        params["key"] = api_key
    return params


def fetch_census_bds_response(
    config: CensusBDSConfig,
    *,
    session: requests.Session | None = None,
    start_year: int | None = None,
    end_year: int | None = None,
    api_key: str | None = None,
    timeout: int = 120,
) -> list[list[str]]:
    active_session = session or requests.Session()
    response = active_session.get(
        config.endpoint,
        params=build_census_bds_params(
            config,
            start_year=start_year,
            end_year=end_year,
            api_key=api_key,
        ),
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()

    if not isinstance(payload, list):
        raise ValueError("Census BDS response must be a list of rows")

    return payload


def validate_bds_response(
    response_rows: list[list[str]],
    *,
    required_variables: tuple[str, ...],
) -> CensusBDSResponseSummary:
    if len(response_rows) < 2:
        raise ValueError("Census BDS response must include a header row and data rows")

    header = response_rows[0]
    data_rows = response_rows[1:]
    if not isinstance(header, list) or not all(isinstance(row, list) for row in data_rows):
        raise ValueError("Census BDS response rows must be lists")

    missing_variables = sorted(set(required_variables) - set(header))
    if missing_variables:
        raise ValueError(
            "Missing required Census BDS variables: " + ", ".join(missing_variables)
        )

    year_index = header.index("YEAR")
    state_index = header.index("state")
    state_year_pairs: set[tuple[str, str]] = set()
    latest_available_year = 0

    for row in data_rows:
        if len(row) != len(header):
            raise ValueError("Census BDS data row length does not match header")

        state_year_pair = (row[state_index], row[year_index])
        if state_year_pair in state_year_pairs:
            raise ValueError("Duplicate Census BDS state-year rows found")
        state_year_pairs.add(state_year_pair)
        latest_available_year = max(latest_available_year, int(row[year_index]))

    return CensusBDSResponseSummary(
        header=header,
        row_count=len(data_rows),
        latest_available_year=latest_available_year,
    )


def extract_census_bds(
    *,
    config: CensusBDSConfig | None = None,
    source_identity: SourceIdentity | None = None,
    session: requests.Session | None = None,
    data_root: Path | str = "data",
    s3_bucket: str = DEFAULT_S3_BUCKET,
    pipeline_run_id: str | None = None,
    extracted_at_utc: str | None = None,
    start_year: int | None = None,
    end_year: int | None = None,
    api_key: str | None = None,
    timeout: int = 120,
    raw_artifact_store: LocalRawArtifactStore | S3RawArtifactStore | None = None,
) -> CensusBDSExtractionSummary:
    active_config = config or load_census_bds_config()
    active_identity = source_identity or DEFAULT_SOURCE_IDENTITY
    resolved_start_year = start_year or active_config.start_year
    resolved_end_year = end_year or datetime.now().year
    run_id = pipeline_run_id or str(uuid.uuid4())
    extracted_timestamp = extracted_at_utc or format_utc_timestamp(utc_now())
    ingestion_date = _ingestion_date_from_iso(extracted_timestamp)

    response_rows = fetch_census_bds_response(
        active_config,
        session=session,
        start_year=resolved_start_year,
        end_year=resolved_end_year,
        api_key=api_key or os.getenv("CENSUS_API_KEY") or None,
        timeout=timeout,
    )
    response_summary = validate_bds_response(
        response_rows,
        required_variables=active_config.required_variables,
    )

    store = raw_artifact_store or LocalRawArtifactStore(
        data_root=Path(data_root),
        s3_bucket=s3_bucket,
    )
    location = store.location(
        source_system=active_identity.source_system,
        dataset_name=active_identity.dataset_name,
        resource_name=RESOURCE_GRAIN,
        ingestion_date=ingestion_date,
        pipeline_run_id=run_id,
        filename=f"{RESOURCE_NAME}_{resolved_start_year}_{resolved_end_year}.json",
    )
    raw_payload = (json.dumps(response_rows, indent=2) + "\n").encode("utf-8")
    store.write_bytes(location, raw_payload)
    manifest_fields = location.manifest_fields()
    manifest = ExtractionManifest(
        pipeline_run_id=run_id,
        source_system=active_identity.source_system,
        dataset_name=active_identity.dataset_name,
        resource_name=RESOURCE_NAME,
        source_url=active_config.endpoint,
        extracted_at_utc=extracted_timestamp,
        ingestion_date=ingestion_date,
        local_raw_path=manifest_fields["local_raw_path"],
        s3_raw_uri=str(manifest_fields["s3_raw_uri"]),
        file_format="json",
        row_count=response_summary.row_count,
        sha256_checksum=hash_bytes(raw_payload),
        schema_hash=hash_schema(response_summary.header),
        validation_status="passed",
        raw_uri=str(manifest_fields["raw_uri"]),
        storage_backend=str(manifest_fields["storage_backend"]),
        request_parameters={
            "start_year": resolved_start_year,
            "end_year": resolved_end_year,
            "geography": active_config.geography,
            "variables": list(active_config.required_variables),
        },
        column_count=len(response_summary.header),
        file_size_bytes=len(raw_payload),
        validation_messages=[],
    )
    manifest_path = _build_local_manifest_path(
        data_root=Path(data_root),
        ingestion_date=ingestion_date,
        pipeline_run_id=run_id,
    )
    manifest_dict = {
        **manifest.to_dict(),
        "latest_available_year": response_summary.latest_available_year,
    }
    write_manifest(manifest_dict, manifest_path)

    return CensusBDSExtractionSummary(
        result=ExtractionResult(
            manifest=manifest,
            local_raw_path=location.local_path,
            row_count=response_summary.row_count,
        ),
        manifest_path=manifest_path,
        latest_available_year=response_summary.latest_available_year,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Census BDS state-year data.")
    parser.add_argument("--config", default="config/census_bds_variables.yml")
    parser.add_argument("--data-root", default="data")
    parser.add_argument("--s3-bucket", default=DEFAULT_S3_BUCKET)
    parser.add_argument("--pipeline-run-id")
    parser.add_argument("--start-year", type=int)
    parser.add_argument("--end-year", type=int)
    args = parser.parse_args()

    summary = extract_census_bds(
        config=load_census_bds_config(args.config),
        data_root=args.data_root,
        s3_bucket=args.s3_bucket,
        pipeline_run_id=args.pipeline_run_id,
        start_year=args.start_year,
        end_year=args.end_year,
    )
    print(
        "Downloaded Census BDS state-year extract: "
        f"{summary.result.row_count} rows, latest year {summary.latest_available_year}"
    )


def _time_predicate(start_year: int, end_year: int) -> str:
    if start_year > end_year:
        raise ValueError("start_year cannot be greater than end_year")
    if start_year == end_year:
        return str(start_year)
    return f"from {start_year} to {end_year}"


def _build_local_manifest_path(
    *,
    data_root: Path,
    ingestion_date: str,
    pipeline_run_id: str,
) -> Path:
    return (
        data_root
        / "manifests"
        / "census"
        / f"ingestion_date={ingestion_date}"
        / f"pipeline_run_id={pipeline_run_id}"
        / f"{RESOURCE_NAME}.manifest.json"
    )


def _ingestion_date_from_iso(value: str) -> str:
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return ingestion_date_from_timestamp(timestamp)


if __name__ == "__main__":
    main()
