"""Extract and validate Census BDS state-year business dynamics data."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import requests

from pipelines.extract.extraction_cli import (
    add_common_extraction_arguments,
    add_year_range_arguments,
)
from pipelines.extract.extraction_run import (
    DEFAULT_EXTRACTION_S3_BUCKET,
    JsonExtractionArtifactSpec,
    SingleResourceExtractionSummary,
    build_extraction_run,
    resolve_api_key,
    resolve_year_range,
    write_json_extraction_artifact,
)
from pipelines.storage.raw_artifacts import (
    ArtifactLocation,
    LocalArtifactStore,
    LocalRawArtifactStore,
    S3ArtifactStore,
    S3RawArtifactStore,
)
from pipelines.utils.manifest import ExtractionResult
from pipelines.utils.source_config_models import (
    CENSUS_BDS_CONFIG_FILE,
    CensusBDSConfig,
    load_census_bds_config,
)
from pipelines.utils.source_resources import (
    CENSUS_BDS_RESOURCE,
    SourceIdentity,
)


@dataclass(frozen=True)
class CensusBDSResponseSummary:
    """Validated Census BDS response metadata used for raw manifests."""

    header: list[str]
    row_count: int
    latest_available_year: int


@dataclass(frozen=True)
class CensusBDSExtractionSummary(SingleResourceExtractionSummary):
    """Summary returned after a Census BDS state-year extraction completes."""

    source_resource = CENSUS_BDS_RESOURCE

    result: ExtractionResult
    manifest_path: Path
    latest_available_year: int
    manifest_location: ArtifactLocation | None = None


def extract_census_bds(
    *,
    config: CensusBDSConfig | None = None,
    source_identity: SourceIdentity | None = None,
    session: requests.Session | None = None,
    data_root: Path | str = "data",
    s3_bucket: str = DEFAULT_EXTRACTION_S3_BUCKET,
    pipeline_run_id: str | None = None,
    extracted_at_utc: str | None = None,
    start_year: int | None = None,
    end_year: int | None = None,
    api_key: str | None = None,
    timeout: int = 120,
    raw_artifact_store: LocalRawArtifactStore | S3RawArtifactStore | None = None,
    manifest_artifact_store: LocalArtifactStore | S3ArtifactStore | None = None,
) -> CensusBDSExtractionSummary:
    """Fetch, validate, persist, and manifest Census BDS state-year data."""
    active_config = config or load_census_bds_config()
    resolved_start_year, resolved_end_year = resolve_year_range(
        default_start_year=active_config.start_year,
        start_year=start_year,
        end_year=end_year,
    )
    active_api_key = resolve_api_key(api_key, env_var="CENSUS_API_KEY")
    extraction_run = build_extraction_run(
        data_root=data_root,
        s3_bucket=s3_bucket,
        pipeline_run_id=pipeline_run_id,
        extracted_at_utc=extracted_at_utc,
        raw_artifact_store=raw_artifact_store,
    )

    response_rows = fetch_census_bds_response(
        active_config,
        session=session,
        start_year=resolved_start_year,
        end_year=resolved_end_year,
        api_key=active_api_key,
        timeout=timeout,
    )
    response_summary = validate_bds_response(
        response_rows,
        required_variables=active_config.required_variables,
    )

    artifact = write_json_extraction_artifact(
        extraction_run=extraction_run,
        spec=JsonExtractionArtifactSpec(
            source_resource=CENSUS_BDS_RESOURCE,
            source_url=active_config.endpoint,
            raw_filename=(
                f"{CENSUS_BDS_RESOURCE.resource_name}_{resolved_start_year}_"
                f"{resolved_end_year}.json"
            ),
            raw_payload=response_rows,
            row_count=response_summary.row_count,
            schema_fields=response_summary.header,
            request_parameters={
                "start_year": resolved_start_year,
                "end_year": resolved_end_year,
                "geography": active_config.geography,
                "variables": list(active_config.required_variables),
            },
            source_identity=source_identity,
            manifest_payload_extras={
                "latest_available_year": response_summary.latest_available_year,
            },
        ),
        manifest_artifact_store=manifest_artifact_store,
    )

    return CensusBDSExtractionSummary(
        result=artifact.result,
        manifest_path=artifact.manifest_path,
        manifest_location=artifact.manifest_location,
        latest_available_year=response_summary.latest_available_year,
    )


def build_census_bds_params(
    config: CensusBDSConfig,
    *,
    start_year: int | None = None,
    end_year: int | None = None,
    api_key: str | None = None,
) -> dict[str, str]:
    """Build Census API query parameters from configured variables and years."""
    resolved_start_year, resolved_end_year = resolve_year_range(
        default_start_year=config.start_year,
        start_year=start_year,
        end_year=end_year,
    )
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
    """Fetch raw Census BDS rows from the Census API."""
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
    """Validate Census BDS row shape, required fields, and state-year uniqueness."""
    if len(response_rows) < 2:
        raise ValueError("Census BDS response must include a header row and data rows")

    header = response_rows[0]
    data_rows = response_rows[1:]
    if not isinstance(header, list) or not all(
        isinstance(row, list) for row in data_rows
    ):
        raise ValueError("Census BDS response rows must be lists")

    # The Census API returns a header row followed by positional data rows; keep
    # validation here so manifest row counts and dbt grain assumptions agree.
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


def _time_predicate(start_year: int, end_year: int) -> str:
    """Format the Census API time predicate for one year or an inclusive range."""
    if start_year > end_year:
        raise ValueError("start_year cannot be greater than end_year")
    if start_year == end_year:
        return str(start_year)
    return f"from {start_year} to {end_year}"


def main() -> None:
    """Run the Census BDS extraction command-line entry point."""
    parser = argparse.ArgumentParser(description="Extract Census BDS state-year data.")
    add_common_extraction_arguments(
        parser,
        config_default=f"config/{CENSUS_BDS_CONFIG_FILE}",
        s3_bucket_default=DEFAULT_EXTRACTION_S3_BUCKET,
    )
    add_year_range_arguments(parser)
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


if __name__ == "__main__":
    main()
