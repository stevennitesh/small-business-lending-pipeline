from __future__ import annotations

from dataclasses import replace

import pipelines.flows.lending_pipeline_flow as local_flow
from pipelines.validation.raw_validation_resources import (
    BLS_LAUS_SOURCE_KEY,
    CENSUS_BDS_SOURCE_KEY,
    SBA_FOIA_SOURCE_KEY,
)
from tests.unit.source_extracts_flow_test_helpers import (
    install_source_extractor_fakes,
    live_flow_context,
)


def test_live_extraction_routes_to_source_extractors(tmp_path, monkeypatch):
    """Validate that live extraction routes to source extractors."""
    project_config = local_flow.load_config.fn()
    context = live_flow_context(tmp_path)
    calls = []
    install_source_extractor_fakes(monkeypatch, tmp_path, calls=calls)

    extraction_paths = local_flow.extract_sources.fn(context, project_config)

    assert [name for name, _ in calls] == ["sba", "census", "bls"]
    assert calls[0][1]["config"] == project_config.sba
    assert calls[0][1]["source_identity"] == project_config.source_identity(
        SBA_FOIA_SOURCE_KEY
    )
    assert calls[1][1]["config"] == project_config.census_bds
    assert calls[1][1]["source_identity"] == project_config.source_identity(
        CENSUS_BDS_SOURCE_KEY
    )
    assert calls[1][1]["start_year"] == 2020
    assert calls[1][1]["end_year"] == 2024
    assert calls[2][1]["config"] == project_config.bls_laus
    assert calls[2][1]["source_identity"] == project_config.source_identity(
        BLS_LAUS_SOURCE_KEY
    )
    assert calls[2][1]["start_year"] == 2019
    assert calls[2][1]["end_year"] == 2024
    assert len(extraction_paths.sba_7a_manifest_paths) == 1
    assert len(extraction_paths.sba_504_manifest_paths) == 1
    assert len(extraction_paths.manifest_paths) == 4


def test_cloud_live_extraction_passes_s3_manifest_artifact_store(
    tmp_path,
    monkeypatch,
):
    """Validate that cloud live extraction passes S3 manifest artifact store."""
    project_config = local_flow.load_config.fn()
    context = live_flow_context(
        tmp_path,
        run_mode="cloud",
        s3_bucket="cloud-bucket",
        pipeline_run_id="cloud-live-test-run",
    )
    calls = []
    install_source_extractor_fakes(
        monkeypatch,
        tmp_path,
        calls=calls,
        manifest_locations=True,
    )

    extraction_paths = local_flow.extract_sources.fn(context, project_config)

    assert [
        kwargs["manifest_artifact_store"].storage_backend for _, kwargs in calls
    ] == ["s3", "s3", "s3"]
    assert len(extraction_paths.manifest_locations) == 4
    assert {
        location.storage_backend for location in extraction_paths.manifest_locations
    } == {"s3"}


def test_live_bls_extraction_defaults_to_configured_history_start(
    tmp_path, monkeypatch
):
    """Validate that live BLS extraction defaults to configured history start."""
    project_config = local_flow.load_config.fn()
    context = live_flow_context(
        tmp_path,
        pipeline_run_id="live-config-start-run",
        source_start_year=None,
        source_end_year=2024,
    )
    calls = []
    install_source_extractor_fakes(monkeypatch, tmp_path, calls=calls)

    local_flow.extract_sources.fn(context, project_config)

    bls_call = next(kwargs for name, kwargs in calls if name == "bls")
    assert project_config.bls_laus.start_year == 1990
    assert bls_call["start_year"] == 1989
    assert bls_call["end_year"] == 2024


def test_live_extraction_honors_disabled_sources(tmp_path, monkeypatch):
    """Validate that live extraction honors disabled sources."""
    project_config = local_flow.load_config.fn()
    sources = {
        **project_config.sources,
        CENSUS_BDS_SOURCE_KEY: replace(
            project_config.sources[CENSUS_BDS_SOURCE_KEY],
            enabled=False,
        ),
    }
    project_config = replace(project_config, sources=sources)
    context = live_flow_context(
        tmp_path,
        pipeline_run_id="live-disabled-source",
    )
    calls = []
    install_source_extractor_fakes(monkeypatch, tmp_path, calls=calls)

    extraction_paths = local_flow.extract_sources.fn(context, project_config)

    assert [name for name, _ in calls] == ["sba", "bls"]
    assert extraction_paths.census_bds_manifest_paths == ()
    assert len(extraction_paths.manifest_paths) == 3
