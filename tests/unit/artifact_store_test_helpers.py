from __future__ import annotations

from typing import Any

from botocore.exceptions import ClientError


class FakeBody:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return self.payload


class FakeS3ObjectClient:
    def __init__(self, objects: dict[tuple[str, str], bytes] | None = None) -> None:
        self.objects: dict[tuple[str, str], bytes] = dict(objects or {})
        self.body_types: dict[tuple[str, str], str] = {}
        self.get_calls: list[tuple[str, str]] = []
        self.put_calls: list[tuple[str, str]] = []

    def put_object(self, *, Bucket: str, Key: str, Body: Any) -> None:
        object_key = (Bucket, Key)
        self.put_calls.append(object_key)
        self.body_types[object_key] = type(Body).__name__
        self.objects[object_key] = Body.read() if hasattr(Body, "read") else Body

    def get_object(self, *, Bucket: str, Key: str, **kwargs):
        del kwargs
        object_key = (Bucket, Key)
        self.get_calls.append(object_key)
        if object_key not in self.objects:
            raise ClientError(
                {
                    "Error": {
                        "Code": "NoSuchKey",
                        "Message": f"The specified key does not exist: {Key}",
                    }
                },
                "GetObject",
            )
        return {"Body": FakeBody(self.objects[(Bucket, Key)])}
