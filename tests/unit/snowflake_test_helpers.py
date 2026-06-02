from __future__ import annotations

import pandas as pd

from tests.unit.artifact_store_test_helpers import FakeBody


class FakeSnowflakeConnection:
    """Fake Snowflake connection used by loader tests."""

    def __init__(self, table_counts: dict[str, int] | None = None) -> None:
        """Initialize the test double."""
        self.sql_statements: list[str] = []
        self.table_counts = table_counts or {}
        self.closed = False

    def cursor(self):
        """Return the fake Snowflake cursor."""
        return FakeSnowflakeCursor(self)

    def close(self) -> None:
        """Close the fake Snowflake connection."""
        self.closed = True


class FakeSnowflakeCursor:
    """Fake Snowflake cursor used by loader tests."""

    def __init__(self, connection: FakeSnowflakeConnection) -> None:
        """Initialize the test double."""
        self.connection = connection
        self.result: tuple[int] | None = None

    def __enter__(self):
        """Enter the test double context manager."""
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        """Exit the test double context manager."""
        return None

    def execute(self, sql: str):
        """Record a fake Snowflake SQL statement."""
        normalized_sql = " ".join(sql.split())
        self.connection.sql_statements.append(normalized_sql)
        # Row-count queries drive loader reconciliation checks; other statements
        # only need to be recorded for assertions about generated SQL.
        if normalized_sql.lower().startswith("select count(*) from "):
            table_name = normalized_sql.rsplit(" ", 1)[-1]
            self.result = (self.connection.table_counts[table_name],)
        return self

    def fetchone(self):
        """Return the fake cursor row count."""
        if self.result is None:
            raise AssertionError("No fake result available")
        return self.result


class FakeSnowflakeWriter:
    """Fake write_pandas callable used by Snowflake tests."""

    def __init__(self) -> None:
        """Initialize the test double."""
        self.written_frames: dict[str, pd.DataFrame] = {}

    def __call__(
        self,
        connection,
        frame: pd.DataFrame,
        table_name: str,
        **kwargs,
    ) -> tuple[bool, int, int, list[tuple[str, str]]]:
        """Record the test double call."""
        self.written_frames[table_name] = frame.copy()
        return True, 1, len(frame), []


class FakeS3Client:
    """Fake S3 client used by Snowflake stage tests."""

    def __init__(
        self,
        headers: dict[str, str],
        *,
        objects: dict[tuple[str, str], bytes] | None = None,
    ) -> None:
        """Initialize the test double."""
        self.headers = headers
        self.objects = objects or {}

    def get_object(self, **kwargs):
        """Return a fake S3 get_object response."""
        object_key = (kwargs["Bucket"], kwargs["Key"])
        if object_key in self.objects:
            return {"Body": FakeBody(self.objects[object_key])}
        return {"Body": FakeBody(self.headers[kwargs["Key"]].encode("utf-8"))}
