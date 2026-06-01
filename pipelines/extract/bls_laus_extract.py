"""Extract and normalize BLS LAUS state-month unemployment data."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import requests

from pipelines.extract.bls_laus_periods import parse_monthly_period
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
    BLS_LAUS_CONFIG_FILE,
    BLSLAUSConfig,
    BLSSeriesConfig,
    load_bls_laus_config,
)
from pipelines.utils.source_resources import (
    BLS_LAUS_RESOURCE,
    SourceIdentity,
)


DEFAULT_CHUNK_SIZE = 25
REGISTERED_YEAR_WINDOW_SIZE = 20
PUBLIC_YEAR_WINDOW_SIZE = 10
RAW_FILENAME_PREFIX = "bls_laus_state_month"


@dataclass(frozen=True)
class BLSLAUSExtractionSummary(SingleResourceExtractionSummary):
    """Summary returned after a BLS LAUS state-month extraction completes."""

    source_resource = BLS_LAUS_RESOURCE

    result: ExtractionResult
    manifest_path: Path
    latest_observed_month: str
    series_count: int
    manifest_location: ArtifactLocation | None = None


def extract_bls_laus(
    *,
    config: BLSLAUSConfig | None = None,
    source_identity: SourceIdentity | None = None,
    session: requests.Session | None = None,
    data_root: Path | str = "data",
    s3_bucket: str = DEFAULT_EXTRACTION_S3_BUCKET,
    pipeline_run_id: str | None = None,
    extracted_at_utc: str | None = None,
    start_year: int | None = None,
    end_year: int | None = None,
    api_key: str | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    year_window_size: int | None = None,
    timeout: int = 120,
    raw_artifact_store: LocalRawArtifactStore | S3RawArtifactStore | None = None,
    manifest_artifact_store: LocalArtifactStore | S3ArtifactStore | None = None,
) -> BLSLAUSExtractionSummary:
    """Fetch, normalize, persist, and manifest BLS LAUS state-month data."""
    active_config = config or load_bls_laus_config()
    resolved_start_year, resolved_end_year = resolve_year_range(
        default_start_year=active_config.start_year,
        start_year=start_year,
        end_year=end_year,
    )
    active_api_key = resolve_api_key(api_key, env_var="BLS_API_KEY")
    resolved_year_window_size = resolve_bls_year_window_size(
        api_key=active_api_key,
        year_window_size=year_window_size,
    )
    request_parameters = {
        "start_year": resolved_start_year,
        "end_year": resolved_end_year,
        "chunk_size": chunk_size,
        "year_window_size": resolved_year_window_size,
        "series_count": len(active_config.series),
    }
    extraction_run = build_extraction_run(
        data_root=data_root,
        s3_bucket=s3_bucket,
        pipeline_run_id=pipeline_run_id,
        extracted_at_utc=extracted_at_utc,
        raw_artifact_store=raw_artifact_store,
    )

    responses = fetch_bls_laus_responses(
        active_config,
        session=session,
        start_year=resolved_start_year,
        end_year=resolved_end_year,
        api_key=active_api_key,
        chunk_size=chunk_size,
        year_window_size=resolved_year_window_size,
        timeout=timeout,
    )
    series_by_id = {series.series_id: series for series in active_config.series}
    normalized_rows = normalize_bls_response(responses, series_by_id=series_by_id)
    if not normalized_rows:
        raise ValueError("BLS LAUS response did not include monthly observations")

    latest_observed_month = max(row["observed_month"] for row in normalized_rows)
    raw_payload = {
        "request": {
            **request_parameters,
            "measure_name": active_config.measure_name,
            "seasonal_adjustment": active_config.seasonal_adjustment,
        },
        "responses": responses,
        "normalized_rows": normalized_rows,
    }
    artifact = write_json_extraction_artifact(
        extraction_run=extraction_run,
        spec=JsonExtractionArtifactSpec(
            source_resource=BLS_LAUS_RESOURCE,
            source_url=active_config.endpoint,
            raw_filename=(
                f"{RAW_FILENAME_PREFIX}_{resolved_start_year}_{resolved_end_year}.json"
            ),
            raw_payload=raw_payload,
            row_count=len(normalized_rows),
            schema_fields=list(normalized_rows[0]),
            request_parameters=request_parameters,
            source_identity=source_identity,
            manifest_payload_extras={
                "series_count": len(active_config.series),
                "latest_observed_month": latest_observed_month,
            },
        ),
        manifest_artifact_store=manifest_artifact_store,
    )

    return BLSLAUSExtractionSummary(
        result=artifact.result,
        manifest_path=artifact.manifest_path,
        manifest_location=artifact.manifest_location,
        latest_observed_month=latest_observed_month,
        series_count=len(active_config.series),
    )


# BLS API request helpers.
def chunk_series(
    series: Sequence[Any],
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> Iterable[tuple[Any, ...]]:
    """Yield BLS series IDs in request-sized chunks."""
    if chunk_size < 1:
        raise ValueError("chunk_size must be at least 1")

    for index in range(0, len(series), chunk_size):
        yield tuple(series[index : index + chunk_size])


def chunk_year_range(
    start_year: int,
    end_year: int,
    *,
    window_size: int,
) -> Iterable[tuple[int, int]]:
    """Yield inclusive year windows that respect BLS API range limits."""
    if start_year > end_year:
        raise ValueError("start_year cannot be greater than end_year")
    if window_size < 1:
        raise ValueError("window_size must be at least 1")

    for year in range(start_year, end_year + 1, window_size):
        yield year, min(year + window_size - 1, end_year)


def build_bls_payload(
    series_ids: Sequence[str],
    *,
    start_year: int,
    end_year: int,
    api_key: str | None = None,
) -> dict[str, object]:
    """Build the JSON request body expected by the BLS public API."""
    if start_year > end_year:
        raise ValueError("start_year cannot be greater than end_year")

    payload: dict[str, object] = {
        "seriesid": list(series_ids),
        "startyear": str(start_year),
        "endyear": str(end_year),
    }
    if api_key:
        payload["registrationkey"] = api_key
    return payload


def fetch_bls_laus_responses(
    config: BLSLAUSConfig,
    *,
    session: requests.Session | None = None,
    start_year: int,
    end_year: int,
    api_key: str | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    year_window_size: int | None = None,
    timeout: int = 120,
) -> list[dict[str, Any]]:
    """Fetch all configured BLS LAUS series across series and year chunks."""
    active_session = session or requests.Session()
    responses: list[dict[str, Any]] = []
    series_ids = tuple(series.series_id for series in config.series)
    resolved_year_window_size = resolve_bls_year_window_size(
        api_key=api_key,
        year_window_size=year_window_size,
    )

    for year_start, year_end in chunk_year_range(
        start_year,
        end_year,
        window_size=resolved_year_window_size,
    ):
        for series_id_chunk in chunk_series(series_ids, chunk_size=chunk_size):
            response = active_session.post(
                config.endpoint,
                json=build_bls_payload(
                    series_id_chunk,
                    start_year=year_start,
                    end_year=year_end,
                    api_key=api_key,
                ),
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json()
            _validate_bls_response_status(payload)
            responses.append(payload)

    return responses


def resolve_bls_year_window_size(
    *,
    api_key: str | None,
    year_window_size: int | None = None,
) -> int:
    """Choose the BLS year-window limit for public or registered API access."""
    # Registered API access can request wider year windows.
    return year_window_size or (
        REGISTERED_YEAR_WINDOW_SIZE if api_key else PUBLIC_YEAR_WINDOW_SIZE
    )


# Response normalization keeps BLS source metadata beside each observation.
def normalize_bls_response(
    responses: list[dict[str, Any]],
    *,
    series_by_id: dict[str, BLSSeriesConfig],
) -> list[dict[str, Any]]:
    """Convert BLS API series payloads into state-month observation rows."""
    rows: list[dict[str, Any]] = []

    for response in responses:
        _validate_bls_response_status(response)
        response_series = response.get("Results", {}).get("series", [])
        if not isinstance(response_series, list):
            raise ValueError("BLS LAUS response Results.series must be a list")

        for series_payload in response_series:
            series_id = str(series_payload["seriesID"])
            if series_id not in series_by_id:
                raise ValueError(f"Unexpected BLS LAUS series ID: {series_id}")

            series_config = series_by_id[series_id]
            for observation in series_payload.get("data", []):
                observed_month = parse_monthly_period(
                    str(observation["year"]),
                    str(observation["period"]),
                )
                if observed_month is None:
                    continue

                try:
                    value = float(observation["value"])
                except ValueError:
                    continue

                rows.append(
                    {
                        "series_id": series_id,
                        "state_fips": series_config.state_fips,
                        "state_abbr": series_config.state_abbr,
                        "state_name": series_config.state_name,
                        "year": int(observation["year"]),
                        "period": str(observation["period"]),
                        "observed_month": observed_month.isoformat(),
                        "value": value,
                        "footnotes": _clean_footnotes(
                            observation.get("footnotes", [])
                        ),
                    }
                )

    return rows


def _validate_bls_response_status(response: dict[str, Any]) -> None:
    status = response.get("status")
    if status != "REQUEST_SUCCEEDED":
        messages = response.get("message") or []
        raise ValueError(f"BLS LAUS request failed with status {status}: {messages}")


def _clean_footnotes(footnotes: Any) -> list[dict[str, str]]:
    if not isinstance(footnotes, list):
        return []
    return [
        footnote
        for footnote in footnotes
        if isinstance(footnote, dict) and any(footnote.values())
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract BLS LAUS state-month data.")
    add_common_extraction_arguments(
        parser,
        config_default=f"config/{BLS_LAUS_CONFIG_FILE}",
        s3_bucket_default=DEFAULT_EXTRACTION_S3_BUCKET,
    )
    add_year_range_arguments(parser)
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    args = parser.parse_args()

    summary = extract_bls_laus(
        config=load_bls_laus_config(args.config),
        data_root=args.data_root,
        s3_bucket=args.s3_bucket,
        pipeline_run_id=args.pipeline_run_id,
        start_year=args.start_year,
        end_year=args.end_year,
        chunk_size=args.chunk_size,
    )
    print(
        "Downloaded BLS LAUS state-month extract: "
        f"{summary.result.row_count} rows, latest month {summary.latest_observed_month}"
    )


if __name__ == "__main__":
    main()
