from __future__ import annotations

from datetime import datetime, timezone


UTC = timezone.utc


def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(UTC)


def require_utc(timestamp: datetime) -> datetime:
    """Require and normalize a timezone-aware UTC timestamp."""
    if timestamp.tzinfo is None or timestamp.utcoffset() != UTC.utcoffset(timestamp):
        raise ValueError("Timestamp must be timezone-aware UTC")

    return timestamp.astimezone(UTC)


def utc_now_iso() -> str:
    """Return the current UTC timestamp in manifest ISO format."""
    return format_utc_timestamp(utc_now())


def format_utc_timestamp(timestamp: datetime) -> str:
    """Format a UTC timestamp with a trailing Z suffix."""
    utc_timestamp = require_utc(timestamp)
    return utc_timestamp.isoformat().replace("+00:00", "Z")


def ingestion_date_from_timestamp(timestamp: datetime) -> str:
    """Return the UTC calendar date for a timestamp."""
    utc_timestamp = require_utc(timestamp)
    return utc_timestamp.date().isoformat()


def ingestion_date_from_iso_timestamp(value: str) -> str:
    """Parse an ISO timestamp and return its UTC ingestion date."""
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return ingestion_date_from_timestamp(timestamp)
