"""Resolve SBA package metadata into configured raw resources."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlparse

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
    """Fetch SBA open-data package metadata, optionally caching the result."""
    active_session = session or requests.Session()
    response = active_session.get(package_url, timeout=timeout)
    response.raise_for_status()
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
    """Find the CKAN resource that matches one configured SBA resource spec."""
    expected_format = spec.expected_format.lower()
    for resource in metadata_resources:
        resource_format = str(resource.get("format") or "").lower()
        resource_title = str(resource.get("name") or resource.get("title") or "")
        if resource_format != expected_format:
            continue
        if _title_matches(spec.title_pattern, resource_title):
            return resource
    return None


def _title_matches(pattern: str, title: str) -> bool:
    """Return whether the title contains all pattern tokens in order."""
    # CKAN resource titles drift in punctuation and spacing, so match ordered
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
    """Normalize a CKAN resource title into lowercase alphanumeric tokens."""
    return re.findall(r"[a-z0-9]+", value.lower())


def _optional_int(value: Any) -> int | None:
    """Convert optional CKAN numeric metadata to an integer when present."""
    if value in ("", None):
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None
