"""Resolve SBA package metadata into configured raw resources."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urljoin, urlparse

import requests

from pipelines.utils.source_config_models import (
    DEFAULT_SBA_PACKAGE_URL,
    SBAResourceSpec,
)
from pipelines.utils.source_resources import RawSourceResource, sba_raw_source_resource


@dataclass(frozen=True)
class ResolvedSBAResource:
    """SBA package resource matched to a configured logical raw resource."""

    spec: SBAResourceSpec
    source_resource: RawSourceResource
    title: str
    url: str
    file_format: str
    source_size_bytes: int | None = None

    @property
    def filename(self) -> str:
        """Return the source filename, falling back to the logical resource name."""
        parsed_name = Path(urlparse(self.url).path).name
        if parsed_name:
            return parsed_name

        extension = self.file_format.lower()
        return f"{self.spec.logical_name}.{extension}"


def fetch_sba_package_metadata(
    package_url: str = DEFAULT_SBA_PACKAGE_URL,
    session: requests.Session | None = None,
    cache_path: Path | str | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    """Read SBA dataset-page links or configured JSON metadata and cache them."""
    active_session = session or requests.Session()
    response = active_session.get(package_url, timeout=timeout)
    response.raise_for_status()
    if "text/html" in response.headers.get("Content-Type", "").lower():
        parser = _SBADistributionParser(package_url)
        parser.feed(response.text)
        if not parser.resources:
            raise ValueError("SBA dataset page contains no CSV/XLSX distribution links")
        metadata = {"source_url": package_url, "resources": parser.resources}
    else:
        payload = response.json()
        if payload.get("success") is False:
            raise ValueError(f"SBA metadata request failed: {payload}")
        metadata = payload.get("result", payload)
    if cache_path is not None:
        resolved_cache_path = Path(cache_path)
        resolved_cache_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_cache_path.write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    return metadata


class _SBADistributionParser(HTMLParser):
    """Normalize the publisher's explicitly labeled download anchors."""

    def __init__(self, page_url: str):
        super().__init__(convert_charrefs=True)
        self.page_url = page_url
        self.resources: list[dict[str, str]] = []
        self._resource: dict[str, str] | None = None
        self._title: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attributes = dict(attrs)
        file_format = (attributes.get("data-format") or "").lower()
        if (
            "distribution-link" in (attributes.get("class") or "").split()
            and file_format in {"csv", "xlsx"}
            and attributes.get("href")
        ):
            self._resource = {
                "url": urljoin(self.page_url, attributes["href"]),
                "format": file_format,
            }
            self._title = []

    def handle_data(self, data: str) -> None:
        if self._resource is not None:
            self._title.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._resource is not None:
            self._resource["name"] = " ".join("".join(self._title).split())
            self.resources.append(self._resource)
            self._resource = None
            self._title = []


def resolve_sba_resources(
    specs: Sequence[SBAResourceSpec],
    package_metadata: dict[str, Any],
) -> dict[str, ResolvedSBAResource]:
    """Match configured SBA resource specs to package metadata entries."""
    metadata_resources = package_metadata.get("resources")
    if not isinstance(metadata_resources, list):
        raise ValueError("SBA package metadata must include a resources list")

    resolved: dict[str, ResolvedSBAResource] = {}
    for spec in specs:
        match = _find_resource_match(spec, metadata_resources)
        if match is None:
            if spec.required:
                raise ValueError(
                    f"Could not resolve required SBA resource: {spec.logical_name}"
                )
            continue

        resolved[spec.logical_name] = ResolvedSBAResource(
            spec=spec,
            source_resource=sba_raw_source_resource(
                logical_name=spec.logical_name,
                program=spec.program,
                source_period=spec.source_period,
            ),
            title=str(match.get("name") or match.get("title") or spec.logical_name),
            url=str(match["url"]),
            file_format=str(match.get("format") or spec.expected_format).lower(),
            source_size_bytes=_optional_int(match.get("size")),
        )

    return resolved


def _find_resource_match(
    spec: SBAResourceSpec,
    metadata_resources: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Find the published resource matching one configured SBA resource spec."""
    expected_format = spec.expected_format.lower()
    matches = []
    for resource in metadata_resources:
        resource_format = str(resource.get("format") or "").lower()
        resource_title = str(resource.get("name") or resource.get("title") or "")
        if resource_format != expected_format:
            continue
        if _title_matches(spec.title_pattern, resource_title):
            if not resource.get("url"):
                raise ValueError(
                    f"SBA resource has no download URL: {spec.logical_name}"
                )
            matches.append(resource)
    unique_matches = {str(resource["url"]): resource for resource in matches}
    if len(unique_matches) > 1:
        raise ValueError(f"Ambiguous SBA resource discovery: {spec.logical_name}")
    return next(iter(unique_matches.values()), None)


def _title_matches(pattern: str, title: str) -> bool:
    """Return whether the title contains all pattern tokens in order."""
    # Publisher resource titles drift in punctuation and spacing, so match ordered
    # tokens instead of depending on an exact title string.
    pattern_tokens = _title_tokens(pattern)
    title_tokens = _title_tokens(title)
    token_index = 0

    for expected_token in pattern_tokens:
        try:
            token_index = title_tokens.index(expected_token, token_index) + 1
        except ValueError:
            return False

    return True


def _title_tokens(value: str) -> list[str]:
    """Normalize titles, including the publisher's 7a versus 7(a) spelling."""
    return [
        part
        for token in re.findall(r"[a-z0-9]+", value.lower())
        for part in (["7", "a"] if token == "7a" else [token])
    ]


def _optional_int(value: Any) -> int | None:
    """Convert optional numeric metadata to an integer when present."""
    if value in ("", None):
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None
