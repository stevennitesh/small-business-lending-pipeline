from __future__ import annotations

from datetime import date, datetime, timezone


UTC = timezone.utc


def utc_now() -> datetime:
    return datetime.now(UTC)


def require_utc(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None or timestamp.utcoffset() != UTC.utcoffset(timestamp):
        raise ValueError("Timestamp must be timezone-aware UTC")

    return timestamp.astimezone(UTC)


def utc_now_iso() -> str:
    return format_utc_timestamp(utc_now())


def format_utc_timestamp(timestamp: datetime) -> str:
    utc_timestamp = require_utc(timestamp)
    return utc_timestamp.isoformat().replace("+00:00", "Z")


def ingestion_date_from_timestamp(timestamp: datetime) -> str:
    utc_timestamp = require_utc(timestamp)
    return utc_timestamp.date().isoformat()


def today_utc() -> date:
    return utc_now().date()
