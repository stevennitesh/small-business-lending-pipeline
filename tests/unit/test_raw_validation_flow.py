from __future__ import annotations

from dataclasses import replace

import pipelines.flows.lending_pipeline_flow as local_flow
from pipelines.validation import (
    raw_validation_runner,
    raw_validation_sources,
)
from pipelines.validation.raw_validation_models import RawValidationInput
from pipelines.validation.raw_validation_expectations import raw_validation_expectations
from pipelines.validation.raw_validation_resources import (
    BLS_LAUS_SOURCE_KEY,
    CENSUS_BDS_SOURCE_KEY,
    SBA_FOIA_SOURCE_KEY,
)
from tests.unit.validation_test_helpers import (
    assert_validation_output_contains,
    read_json,
)
from tests.unit.validation_flow_test_helpers import (
    fixture_validation_inputs,
    validation_context,
)


def test_raw_validation_passes_source_config_identity_to_payload_checks(
    tmp_path,
    monkeypatch,
):
    """Validate that raw validation passes source config identity to payload checks."""
    project_config = local_flow.load_config.fn()
    sources = {
        **project_config.sources,
        SBA_FOIA_SOURCE_KEY: replace(
            project_config.sources[SBA_FOIA_SOURCE_KEY],
            source_system="custom_sba",
            dataset_name="custom_sba_dataset",
        ),
        CENSUS_BDS_SOURCE_KEY: replace(
            project_config.sources[CENSUS_BDS_SOURCE_KEY],
            source_system="custom_census",
            dataset_name="custom_bds",
        ),
        BLS_LAUS_SOURCE_KEY: replace(
            project_config.sources[BLS_LAUS_SOURCE_KEY],
            source_system="custom_bls",
            dataset_name="custom_laus",
        ),
    }
    project_config = replace(project_config, sources=sources)
    _, context, extraction_paths = fixture_validation_inputs(
        tmp_path,
        pipeline_run_id="validation-identity-run",
        project_config=project_config,
    )
    captured_identities = {}

    def fake_sba_check(
        manifests,
        *,
        required_resource_names,
        source_identity,
        artifact_reader,
        raw_file_exists_resource_names,
    ):
        """Provide fake SBA check for tests."""
        captured_identities[SBA_FOIA_SOURCE_KEY] = source_identity
        return []

    def fake_census_check(
        payload,
        *,
        required_variables,
        expected_state_count,
        pipeline_run_id,
        source_identity,
    ):
        """Provide fake census check for tests."""
        captured_identities[CENSUS_BDS_SOURCE_KEY] = source_identity
        return []

    def fake_bls_check(
        payload,
        *,
        expected_series_ids,
        pipeline_run_id,
        required_period_pattern,
        unemployment_rate_min,
        unemployment_rate_max,
        publisher_omissions,
        source_identity,
    ):
        """Provide fake BLS check for tests."""
        captured_identities[BLS_LAUS_SOURCE_KEY] = source_identity
        return []

    monkeypatch.setattr(
        raw_validation_sources,
        "check_sba_required_resources",
        fake_sba_check,
    )
    monkeypatch.setattr(
        raw_validation_sources,
        "check_census_bds_payload",
        fake_census_check,
    )
    monkeypatch.setattr(
        raw_validation_sources,
        "check_bls_laus_payload",
        fake_bls_check,
    )

    local_flow.validate_raw_outputs.fn(context, extraction_paths, project_config)

    assert captured_identities == {
        SBA_FOIA_SOURCE_KEY: project_config.source_identity(SBA_FOIA_SOURCE_KEY),
        CENSUS_BDS_SOURCE_KEY: project_config.source_identity(CENSUS_BDS_SOURCE_KEY),
        BLS_LAUS_SOURCE_KEY: project_config.source_identity(BLS_LAUS_SOURCE_KEY),
    }


def test_raw_validation_core_accepts_validation_owned_input(tmp_path):
    """Validate that raw validation core accepts validation owned input."""
    project_config, context, extraction_paths = fixture_validation_inputs(
        tmp_path,
        pipeline_run_id="validation-core-run",
    )

    validation_output = raw_validation_runner.validate_raw_outputs(
        RawValidationInput(
            pipeline_run_id=context.pipeline_run_id,
            extract_mode=context.extract_mode,
            is_cloud_route=context.is_cloud_route,
            data_root=context.data_root,
            run_started_at_utc=context.run_started_at_utc,
            validation_path=context.run_validation_dir / "validation_results.json",
            manifest_references=extraction_paths.manifest_paths,
        ),
        project_config,
    )
    validation_payload = read_json(validation_output.local_path)

    assert validation_output.local_path.is_file()
    assert validation_output.artifact_location is None
    assert {record["status"] for record in validation_payload} == {"passed"}
    assert_validation_output_contains(validation_output.local_path, "RAW_009")


def test_validation_expectations_follow_extract_mode(tmp_path):
    """Validate that validation expectations follow extract mode."""
    project_config = local_flow.load_config.fn()
    fixture_context = validation_context(
        tmp_path,
        extract_mode="fixture",
        pipeline_run_id="fixture-run",
        data_root_name="fixture-data",
        duckdb_name="fixture.duckdb",
        profiles_name="fixture-profiles",
    )
    live_context = validation_context(
        tmp_path,
        extract_mode="live",
        pipeline_run_id="live-run",
        data_root_name="live-data",
        duckdb_name="live.duckdb",
        profiles_name="live-profiles",
    )

    fixture_expectations = raw_validation_expectations(
        fixture_context.extract_mode,
        project_config,
    )
    live_expectations = raw_validation_expectations(
        live_context.extract_mode,
        project_config,
    )

    assert fixture_expectations.census_expected_state_count == 2
    assert fixture_expectations.census_required_variables == (
        "YEAR",
        "state",
        "ESTAB",
        "ESTABS_ENTRY",
        "ESTABS_EXIT",
    )
    assert fixture_expectations.bls_expected_series_ids == (
        "LASST010000000000003",
        "LASST170000000000003",
    )
    assert live_expectations.census_expected_state_count == 51
    assert live_expectations.census_required_variables == (
        "YEAR",
        "state",
        "ESTAB",
        "ESTABS_ENTRY",
        "ESTABS_EXIT",
    )
    assert len(live_expectations.bls_expected_series_ids) == 51
    assert "sba_7a_fy2020_present" in live_expectations.sba_required_resource_names
    assert "sba_504_fy2010_present" in live_expectations.sba_required_resource_names


def test_live_validation_expectations_skip_disabled_sources():
    """Validate that live validation expectations skip disabled sources."""
    project_config = local_flow.load_config.fn()
    disabled_sources = {
        source_key: replace(source_config, enabled=False)
        for source_key, source_config in project_config.sources.items()
    }
    project_config = replace(project_config, sources=disabled_sources)

    expectations = raw_validation_expectations("live", project_config)

    assert expectations.sba_required_resource_names == []
    assert expectations.census_required_variables == ()
    assert expectations.census_expected_state_count == 0
    assert expectations.bls_expected_series_ids == ()


def test_live_validation_expectations_skip_one_disabled_source():
    """Validate that live validation expectations skip one disabled source."""
    project_config = local_flow.load_config.fn()
    sources = {
        **project_config.sources,
        CENSUS_BDS_SOURCE_KEY: replace(
            project_config.sources[CENSUS_BDS_SOURCE_KEY],
            enabled=False,
        ),
    }
    project_config = replace(project_config, sources=sources)

    expectations = raw_validation_expectations("live", project_config)

    assert expectations.census_required_variables == ()
    assert expectations.census_expected_state_count == 0


def test_fixture_validation_expectations_allow_disabled_census_without_config():
    """Validate that fixture validation expectations allow disabled census without config."""
    project_config = local_flow.load_config.fn()
    project_config = replace(
        project_config,
        sources={
            **project_config.sources,
            CENSUS_BDS_SOURCE_KEY: replace(
                project_config.sources[CENSUS_BDS_SOURCE_KEY],
                enabled=False,
            ),
        },
        raw_validation_expectations={
            source_key: expectations
            for source_key, expectations in project_config.raw_validation_expectations.items()
            if source_key != CENSUS_BDS_SOURCE_KEY
        },
    )

    expectations = raw_validation_expectations("fixture", project_config)

    assert expectations.census_required_variables == ()
    assert expectations.census_expected_state_count == 0
