from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from pipelines.load.raw_load_metadata import manifest_raw_row_metadata


LOCAL_FRAME_SOURCE_TABLE_KINDS = {
    "raw_census_bds_state_year": "census_bds_json",
    "raw_bls_laus_state_month": "bls_laus_json",
}


def load_local_source_frame(
    table_name: str,
    manifests: list[dict[str, Any]],
    *,
    error_cls: type[Exception],
) -> pd.DataFrame:
    """Read small local non-CSV raw files into a source-shaped frame."""

    table_key = _table_key(table_name)
    table_kind = LOCAL_FRAME_SOURCE_TABLE_KINDS.get(table_key)
    if table_kind is None:
        raise error_cls(f"Unsupported raw table: {table_name}")

    frames = [
        _with_metadata(_read_manifest_frame(table_kind, manifest), manifest)
        for manifest in manifests
    ]
    return pd.concat(frames, ignore_index=True)


def _table_key(table_name: str) -> str:
    return table_name.split(".", maxsplit=1)[-1]


def _read_manifest_frame(table_kind: str, manifest: dict[str, Any]) -> pd.DataFrame:
    raw_path = Path(manifest["local_raw_path"])
    if table_kind == "census_bds_json":
        return _read_census_bds_json(raw_path)
    if table_kind == "bls_laus_json":
        return _read_bls_laus_json(raw_path)
    raise ValueError(f"Unsupported source table kind: {table_kind}")


def _read_census_bds_json(path: Path) -> pd.DataFrame:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if len(payload) < 1:
        return pd.DataFrame()
    return pd.DataFrame(payload[1:], columns=payload[0])


def _read_bls_laus_json(path: Path) -> pd.DataFrame:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return pd.DataFrame(payload.get("normalized_rows", []))


def _with_metadata(frame: pd.DataFrame, manifest: dict[str, Any]) -> pd.DataFrame:
    enriched = frame.copy()
    for column_name, value in manifest_raw_row_metadata(manifest).items():
        enriched[column_name] = value
    return enriched
