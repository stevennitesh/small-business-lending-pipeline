"""BLS LAUS request chunking, fetching, and response normalization."""

from __future__ import annotations

from typing import Any, Iterable, Sequence

import requests

from pipelines.extract.bls_laus_periods import parse_monthly_period
from pipelines.utils.source_config_models import BLSLAUSConfig, BLSSeriesConfig


DEFAULT_CHUNK_SIZE = 25
REGISTERED_YEAR_WINDOW_SIZE = 20
PUBLIC_YEAR_WINDOW_SIZE = 10


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
    if year_window_size is not None:
        if year_window_size < 1:
            raise ValueError("year_window_size must be at least 1")
        return year_window_size
    return REGISTERED_YEAR_WINDOW_SIZE if api_key else PUBLIC_YEAR_WINDOW_SIZE


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
                        "footnotes": _clean_footnotes(observation.get("footnotes", [])),
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
