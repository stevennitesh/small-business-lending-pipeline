"""BLS LAUS period parsing helpers shared by extractors and fixtures."""

from __future__ import annotations

from datetime import date


def parse_monthly_period(year: str, period: str) -> date | None:
    """Return month-start dates for BLS monthly periods; skip non-monthly codes."""
    if not period.startswith("M"):
        return None

    try:
        month = int(period[1:])
    except ValueError:
        return None

    if not 1 <= month <= 12:
        return None

    return date(int(year), month, 1)
