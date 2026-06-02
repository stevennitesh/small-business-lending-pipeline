from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests

from pipelines.utils.source_config_models import BLSSeriesConfig, SBAResourceSpec


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


def sample_sba_package_metadata() -> dict:
    resources = [
        (
            "7a_504_FOIA Data Dictionary as of 260331.xlsx",
            "xlsx",
            "https://example.test/dictionary.xlsx",
        ),
        (
            "FOIA - 7(a)(FY1991-FY1999) asof 260331.csv",
            "csv",
            "https://example.test/7a_1991_1999.csv",
        ),
        (
            "FOIA - 7(a)(FY2000-FY2009) asof 260331.csv",
            "csv",
            "https://example.test/7a_2000_2009.csv",
        ),
        (
            "FOIA - 7(a) (FY2010-FY2019) asof 260331.csv",
            "csv",
            "https://example.test/7a_2010_2019.csv",
        ),
        (
            "FOIA - 7(a) (FY2020-Present) asof 260331.csv",
            "csv",
            "https://example.test/7a_2020_present.csv",
        ),
        (
            "FOIA - 504 (FY1991-FY2009) asof 260331.csv",
            "csv",
            "https://example.test/504_1991_2009.csv",
        ),
        (
            "FOIA - 504 (FY2010-Present) asof 260331.csv",
            "csv",
            "https://example.test/504_2010_present.csv",
        ),
    ]
    return {
        "resources": [
            {
                "name": name,
                "format": file_format,
                "url": url,
                "size": len(url),
            }
            for name, file_format, url in resources
        ]
    }


def census_bds_fixture_response() -> list[list[str]]:
    return [
        [
            "NAME",
            "YEAR",
            "ESTAB",
            "ESTABS_ENTRY",
            "ESTABS_ENTRY_RATE",
            "ESTABS_EXIT",
            "ESTABS_EXIT_RATE",
            "FIRM",
            "JOB_CREATION",
            "JOB_DESTRUCTION",
            "time",
            "state",
        ],
        [
            "Alabama",
            "2022",
            "97218",
            "8966",
            "9.260",
            "8190",
            "8.459",
            "70912",
            "226550",
            "177056",
            "2022",
            "01",
        ],
        [
            "Alabama",
            "2023",
            "98246",
            "9094",
            "9.306",
            "8044",
            "8.232",
            "71429",
            "223092",
            "179480",
            "2023",
            "01",
        ],
        [
            "Alaska",
            "2022",
            "18583",
            "1896",
            "10.250",
            "1633",
            "8.827",
            "14667",
            "36076",
            "27925",
            "2022",
            "02",
        ],
    ]


def bls_laus_series_configs() -> tuple[BLSSeriesConfig, ...]:
    return (
        BLSSeriesConfig(
            state_fips="01",
            state_abbr="AL",
            state_name="Alabama",
            series_id="LASST010000000000003",
        ),
        BLSSeriesConfig(
            state_fips="02",
            state_abbr="AK",
            state_name="Alaska",
            series_id="LASST020000000000003",
        ),
    )


def bls_laus_fixture_response() -> dict:
    return {
        "status": "REQUEST_SUCCEEDED",
        "Results": {
            "series": [
                {
                    "seriesID": "LASST010000000000003",
                    "data": [
                        {
                            "year": "2023",
                            "period": "M02",
                            "periodName": "February",
                            "value": "2.7",
                            "footnotes": [{}],
                        },
                        {
                            "year": "2023",
                            "period": "M01",
                            "periodName": "January",
                            "value": "2.6",
                            "footnotes": [{"code": "P", "text": "Preliminary"}],
                        },
                        {
                            "year": "2023",
                            "period": "M13",
                            "periodName": "Annual",
                            "value": "2.9",
                            "footnotes": [{}],
                        },
                        {
                            "year": "2024",
                            "period": "M01",
                            "periodName": "January",
                            "value": "-",
                            "footnotes": [{}],
                        },
                    ],
                },
                {
                    "seriesID": "LASST020000000000003",
                    "data": [
                        {
                            "year": "2023",
                            "period": "M01",
                            "periodName": "January",
                            "value": "3.8",
                            "footnotes": [{}],
                        }
                    ],
                },
            ]
        },
    }


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
        if not self.payloads:
            raise AssertionError(
                "FakePostSession received more POST calls than configured payloads."
            )
        return FakeResponse(self.payloads.pop(0))
