from __future__ import annotations

import pandas as pd


class FakeSnowflakeConnection:
    def __init__(self, table_counts: dict[str, int] | None = None) -> None:
        self.sql_statements: list[str] = []
        self.table_counts = table_counts or {}

    def cursor(self):
        return FakeSnowflakeCursor(self)


class FakeSnowflakeCursor:
    def __init__(self, connection: FakeSnowflakeConnection) -> None:
        self.connection = connection
        self.result: tuple[int] | None = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, sql: str):
        normalized_sql = " ".join(sql.split())
        self.connection.sql_statements.append(normalized_sql)
        if normalized_sql.lower().startswith("select count(*) from "):
            table_name = normalized_sql.rsplit(" ", 1)[-1]
            self.result = (self.connection.table_counts[table_name],)
        return self

    def fetchone(self):
        if self.result is None:
            raise AssertionError("No fake result available")
        return self.result


class FakeSnowflakeWriter:
    def __init__(self) -> None:
        self.written_frames: dict[str, pd.DataFrame] = {}

    def __call__(
        self,
        connection,
        frame: pd.DataFrame,
        table_name: str,
        **kwargs,
    ) -> tuple[bool, int, int, list[tuple[str, str]]]:
        self.written_frames[table_name] = frame.copy()
        return True, 1, len(frame), []


class FakeS3Client:
    def __init__(
        self,
        headers: dict[str, str],
        *,
        objects: dict[tuple[str, str], bytes] | None = None,
    ) -> None:
        self.headers = headers
        self.objects = objects or {}

    def get_object(self, **kwargs):
        object_key = (kwargs["Bucket"], kwargs["Key"])
        if object_key in self.objects:
            return {"Body": FakeBody(self.objects[object_key])}
        return {"Body": FakeBody(self.headers[kwargs["Key"]].encode("utf-8"))}


class FakeBody:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self) -> bytes:
        return self.body
