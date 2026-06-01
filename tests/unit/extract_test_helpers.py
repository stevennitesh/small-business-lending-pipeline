from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests

from pipelines.utils.source_config_models import SBAResourceSpec


def read_json_file(path: Path | str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_summary_manifest(summary) -> dict[str, Any]:
    return read_json_file(summary.manifest_path)


def read_sba_manifest(summary, resource_name: str) -> dict[str, Any]:
    return read_json_file(summary.manifest_paths[resource_name])


def sba_7a_fy2020_present_spec() -> SBAResourceSpec:
    return SBAResourceSpec(
        logical_name="sba_7a_fy2020_present",
        program="7a",
        source_period="fy2020_present",
        expected_format="csv",
        required=True,
        title_pattern="FOIA - 7(a) (FY2020-Present)",
    )


def sba_foia_data_dictionary_spec() -> SBAResourceSpec:
    return SBAResourceSpec(
        logical_name="sba_foia_data_dictionary",
        program="all",
        source_period="all",
        expected_format="xlsx",
        required=True,
        title_pattern="7a_504_FOIA Data Dictionary",
    )


class FakeResponse:
    def __init__(self, content, status_code: int = 200):
        self.content = content
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size: int):
        if isinstance(self.content, list):
            yield from self.content
            return
        if not isinstance(self.content, bytes):
            raise TypeError("FakeResponse content is not bytes")
        for index in range(0, len(self.content), chunk_size):
            yield self.content[index : index + chunk_size]

    def json(self):
        if isinstance(self.content, bytes):
            raise TypeError("FakeResponse content is not JSON")
        return self.content


class FakeDownloadSession:
    def __init__(self, downloads: dict[str, object]):
        self.downloads = downloads
        self.requested_urls: list[str] = []

    def get(self, url: str, timeout: int, stream: bool = False):
        self.requested_urls.append(url)
        payload = self.downloads[url]
        if isinstance(payload, Exception):
            raise payload
        return FakeResponse(payload)


class FakeGetSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls: list[dict] = []

    def get(self, url: str, params: dict[str, str], timeout: int):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return FakeResponse(self.payload)


class FakePostSession:
    def __init__(self, payloads: list[dict]):
        self.payloads = payloads
        self.calls: list[dict] = []

    def post(self, url: str, json: dict[str, object], timeout: int):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        return FakeResponse(self.payloads.pop(0))


class FakeBody:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return self.payload


class FakeS3ObjectClient:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.body_types: dict[tuple[str, str], str] = {}

    def put_object(self, *, Bucket: str, Key: str, Body) -> None:
        self.body_types[(Bucket, Key)] = type(Body).__name__
        self.objects[(Bucket, Key)] = Body.read() if hasattr(Body, "read") else Body

    def get_object(self, *, Bucket: str, Key: str):
        return {"Body": FakeBody(self.objects[(Bucket, Key)])}
