from __future__ import annotations

from pipelines.extract.extraction_run import (
    RawManifestSpec,
    build_extraction_run,
    raw_location_for_resource,
    resolve_api_key,
    resolve_year_range,
    write_raw_extraction_artifact,
)
from pipelines.utils.source_resources import CENSUS_BDS_RESOURCE


def test_write_raw_extraction_artifact_uses_extraction_run_and_source_resource(
    tmp_path,
):
    extraction_run = build_extraction_run(
        data_root=tmp_path,
        s3_bucket="unit-test-bucket",
        pipeline_run_id="run-123",
        extracted_at_utc="2026-05-07T12:00:00Z",
    )
    raw_payload = b'[["YEAR"], ["2026"]]\n'
    raw_location = raw_location_for_resource(
        extraction_run=extraction_run,
        source_resource=CENSUS_BDS_RESOURCE,
        filename="bds_state_year_fixture.json",
    )

    artifact = write_raw_extraction_artifact(
        extraction_run=extraction_run,
        spec=RawManifestSpec.from_extraction_payload(
            extraction_run=extraction_run,
            source_resource=CENSUS_BDS_RESOURCE,
            source_url="fixture://bds_state_year",
            raw_location=raw_location,
            raw_payload=raw_payload,
            row_count=1,
            file_format="json",
            schema_fields=["YEAR"],
            request_parameters={"run_mode": "fixture"},
        ),
    )

    assert artifact.manifest_path == tmp_path / (
        "manifests/census/ingestion_date=2026-05-07/"
        "pipeline_run_id=run-123/bds_state_year.manifest.json"
    )
    assert artifact.result.manifest.resource_name == "bds_state_year"
    assert artifact.result.manifest.row_count == 1


def test_resolve_year_range_uses_explicit_values_or_default_start_year():
    assert resolve_year_range(
        default_start_year=1990,
        start_year=2020,
        end_year=2023,
    ) == (2020, 2023)
    assert resolve_year_range(
        default_start_year=1990,
        end_year=2023,
    ) == (1990, 2023)


def test_resolve_api_key_prefers_explicit_value_then_environment(monkeypatch):
    monkeypatch.setenv("UNIT_TEST_API_KEY", "from-env")

    assert (
        resolve_api_key("explicit-key", env_var="UNIT_TEST_API_KEY")
        == "explicit-key"
    )
    assert resolve_api_key(None, env_var="UNIT_TEST_API_KEY") == "from-env"

    monkeypatch.delenv("UNIT_TEST_API_KEY")
    assert resolve_api_key(None, env_var="UNIT_TEST_API_KEY") is None
