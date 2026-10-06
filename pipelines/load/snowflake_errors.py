from __future__ import annotations


class SnowflakeRawLoadError(RuntimeError):
    """Raised when the Snowflake raw load route cannot satisfy its contracts."""
