from __future__ import annotations

import argparse
import json
import os
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

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
DEFAULT_CHUNK_SIZE = 25
REGISTERED_YEAR_WINDOW_SIZE = 20
PUBLIC_YEAR_WINDOW_SIZE = 10
RESOURCE_NAME = "laus_state_month"
RESOURCE_GRAIN = "grain=state_month"
RAW_FILENAME_PREFIX = "bls_laus_state_month"
DEFAULT_SOURCE_IDENTITY = SourceIdentity(
    source_system="bls",
    dataset_name="laus",
)


@dataclass(frozen=True)
class BLSSeriesConfig:
    state_fips: str
    state_abbr: str
    state_name: str
    series_id: str


@dataclass(frozen=True)
class BLSLAUSConfig:
    endpoint: str
    measure_name: str
    seasonal_adjustment: str
    series: tuple[BLSSeriesConfig, ...]
    start_year: int = 1990


@dataclass(frozen=True)
class BLSLAUSExtractionSummary:
    result: ExtractionResult
    manifest_path: Path
    latest_observed_month: str
    series_count: int


def load_bls_laus_config(
    config_path: Path | str = "config/bls_laus_state_series.yml",
) -> BLSLAUSConfig:
    return parse_bls_laus_config(load_yaml_file(Path(config_path))["bls_laus"])


def parse_bls_laus_config(config: Mapping[str, Any]) -> BLSLAUSConfig:
    return BLSLAUSConfig(
        endpoint=str(config["endpoint"]),
        measure_name=str(config["measure_name"]),
        seasonal_adjustment=str(config["seasonal_adjustment"]),
        series=tuple(
            BLSSeriesConfig(
                state_fips=str(row["state_fips"]),
                state_abbr=str(row["state_abbr"]),
                state_name=str(row["state_name"]),
                series_id=str(row["series_id"]),
            )
            for row in config["series"]
        ),
        start_year=int(config["start_year"]),
    )


def chunk_series(
    series: Sequence[Any],
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> Iterable[tuple[Any, ...]]:
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


def parse_monthly_period(year: str, period: str) -> date | None:
    if not period.startswith("M"):
        return None

    try:
        month = int(period[1:])
    except ValueError:
        return None

    if month < 1 or month > 12:
        return None

    return date(int(year), month, 1)


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
    active_session = session or requests.Session()
    responses: list[dict[str, Any]] = []
    series_ids = tuple(series.series_id for series in config.series)
    resolved_year_window_size = year_window_size or (
        REGISTERED_YEAR_WINDOW_SIZE if api_key else PUBLIC_YEAR_WINDOW_SIZE
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


def normalize_bls_response(
    responses: list[dict[str, Any]],
    *,
    series_by_id: dict[str, BLSSeriesConfig],
) -> list[dict[str, Any]]:
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
                        "footnotes": _clean_footnotes(observation.get("footnotes", [])),
                    }
                )

    return rows


def extract_bls_laus(
    *,
    config: BLSLAUSConfig | None = None,
    source_identity: SourceIdentity | None = None,
    session: requests.Session | None = None,
    data_root: Path | str = "data",
    s3_bucket: str = DEFAULT_S3_BUCKET,
    pipeline_run_id: str | None = None,
    extracted_at_utc: str | None = None,
    start_year: int | None = None,
    end_year: int | None = None,
    api_key: str | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    year_window_size: int | None = None,
    timeout: int = 120,
    raw_artifact_store: LocalRawArtifactStore | S3RawArtifactStore | None = None,
) -> BLSLAUSExtractionSummary:
    active_config = config or load_bls_laus_config()
    active_identity = source_identity or DEFAULT_SOURCE_IDENTITY
    resolved_end_year = end_year or datetime.now().year
    resolved_start_year = start_year or active_config.start_year
    run_id = pipeline_run_id or str(uuid.uuid4())
    extracted_timestamp = extracted_at_utc or format_utc_timestamp(utc_now())
    ingestion_date = _ingestion_date_from_iso(extracted_timestamp)
    active_api_key = api_key or os.getenv("BLS_API_KEY") or None

    responses = fetch_bls_laus_responses(
        active_config,
        session=session,
        start_year=resolved_start_year,
        end_year=resolved_end_year,
        api_key=active_api_key,
        chunk_size=chunk_size,
        year_window_size=year_window_size,
        timeout=timeout,
    )
    series_by_id = {series.series_id: series for series in active_config.series}
    normalized_rows = normalize_bls_response(responses, series_by_id=series_by_id)
    if not normalized_rows:
        raise ValueError("BLS LAUS response did not include monthly observations")

    latest_observed_month = max(row["observed_month"] for row in normalized_rows)
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
        filename=f"{RAW_FILENAME_PREFIX}_{resolved_start_year}_{resolved_end_year}.json",
    )
    raw_payload = {
        "request": {
            "start_year": resolved_start_year,
            "end_year": resolved_end_year,
            "chunk_size": chunk_size,
            "year_window_size": year_window_size
            or (
                REGISTERED_YEAR_WINDOW_SIZE
                if active_api_key
                else PUBLIC_YEAR_WINDOW_SIZE
            ),
            "series_count": len(active_config.series),
            "measure_name": active_config.measure_name,
            "seasonal_adjustment": active_config.seasonal_adjustment,
        },
        "responses": responses,
        "normalized_rows": normalized_rows,
    }
    raw_payload_bytes = (json.dumps(raw_payload, indent=2) + "\n").encode("utf-8")
    store.write_bytes(location, raw_payload_bytes)
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
        row_count=len(normalized_rows),
        sha256_checksum=hash_bytes(raw_payload_bytes),
        schema_hash=hash_schema(list(normalized_rows[0])),
        validation_status="passed",
        raw_uri=str(manifest_fields["raw_uri"]),
        storage_backend=str(manifest_fields["storage_backend"]),
        request_parameters={
            "start_year": resolved_start_year,
            "end_year": resolved_end_year,
            "chunk_size": chunk_size,
            "year_window_size": year_window_size
            or (
                REGISTERED_YEAR_WINDOW_SIZE
                if active_api_key
                else PUBLIC_YEAR_WINDOW_SIZE
            ),
            "series_count": len(active_config.series),
        },
        column_count=len(normalized_rows[0]),
        file_size_bytes=len(raw_payload_bytes),
        validation_messages=[],
    )
    manifest_path = _build_local_manifest_path(
        data_root=Path(data_root),
        ingestion_date=ingestion_date,
        pipeline_run_id=run_id,
    )
    manifest_dict = {
        **manifest.to_dict(),
        "series_count": len(active_config.series),
        "latest_observed_month": latest_observed_month,
    }
    write_manifest(manifest_dict, manifest_path)

    return BLSLAUSExtractionSummary(
        result=ExtractionResult(
            manifest=manifest,
            local_raw_path=location.local_path,
            row_count=len(normalized_rows),
        ),
        manifest_path=manifest_path,
        latest_observed_month=latest_observed_month,
        series_count=len(active_config.series),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract BLS LAUS state-month data.")
    parser.add_argument("--config", default="config/bls_laus_state_series.yml")
    parser.add_argument("--data-root", default="data")
    parser.add_argument("--s3-bucket", default=DEFAULT_S3_BUCKET)
    parser.add_argument("--pipeline-run-id")
    parser.add_argument("--start-year", type=int)
    parser.add_argument("--end-year", type=int)
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


def _build_local_manifest_path(
    *,
    data_root: Path,
    ingestion_date: str,
    pipeline_run_id: str,
) -> Path:
    return (
        data_root
        / "manifests"
        / "bls"
        / f"ingestion_date={ingestion_date}"
        / f"pipeline_run_id={pipeline_run_id}"
        / f"{RESOURCE_NAME}.manifest.json"
    )


def _ingestion_date_from_iso(value: str) -> str:
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return ingestion_date_from_timestamp(timestamp)


if __name__ == "__main__":
    main()
