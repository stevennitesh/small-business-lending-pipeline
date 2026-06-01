from __future__ import annotations

from pipelines.storage.raw_artifacts import ArtifactReader
from pipelines.storage.raw_artifacts import ArtifactLocation
from pipelines.validation.raw_validation_output import (
    ValidationOutputWriteRequest,
    check_validation_output_created,
    write_validation_output_for_route,
)
from pipelines.validation.raw_validation_models import RawValidationOutput
from pipelines.validation.raw_validation_resources import (
    VALIDATION_RESULTS_DATASET_NAME,
    VALIDATION_RESULTS_FILENAME,
    VALIDATION_RESULTS_RESOURCE_NAME,
    VALIDATION_RESULTS_SOURCE_SYSTEM,
)
from tests.unit.validation_test_helpers import (
    raw_file_exists_result,
    read_json,
    validation_check_ids,
)


def test_validation_output_created_check(tmp_path):
    output_path = tmp_path / VALIDATION_RESULTS_FILENAME

    missing_result = check_validation_output_created(
        output_path,
        pipeline_run_id="run-123",
    )
    output_path.write_text("[]\n", encoding="utf-8")
    existing_result = check_validation_output_created(
        output_path,
        pipeline_run_id="run-123",
    )

    assert missing_result.status == "failed"
    assert existing_result.status == "passed"
    assert existing_result.source_system == VALIDATION_RESULTS_SOURCE_SYSTEM
    assert existing_result.source_dataset == VALIDATION_RESULTS_DATASET_NAME
    assert existing_result.source_resource_name == VALIDATION_RESULTS_RESOURCE_NAME


def test_validation_output_self_check_returns_final_results_without_mutating_input(
    tmp_path,
):
    output_path = tmp_path / VALIDATION_RESULTS_FILENAME
    initial_results = [raw_file_exists_result()]

    output_write = write_validation_output_for_route(
        _validation_output_request(
            tmp_path,
            validation_results=initial_results,
            validation_path=output_path,
        )
    )
    written_results = read_json(output_path)

    assert len(initial_results) == 1
    assert len(output_write.validation_results) == 2
    assert output_write.validation_results[0] is initial_results[0]
    assert output_write.validation_results[1].validation_check_id == "RAW_009"
    assert validation_check_ids(written_results) == [
        "RAW_001",
        "RAW_009",
    ]


def test_validation_output_route_writer_returns_destination_and_final_results(tmp_path):
    output_path = tmp_path / VALIDATION_RESULTS_FILENAME

    output_write = write_validation_output_for_route(
        _validation_output_request(tmp_path, validation_path=output_path)
    )

    assert output_write.local_path == output_path
    assert output_write.artifact_location is None
    assert validation_check_ids(output_write.validation_results) == ["RAW_009"]
    assert validation_check_ids(read_json(output_path)) == ["RAW_009"]


def test_raw_validation_output_formats_summary_references(tmp_path):
    local_output = RawValidationOutput(
        local_path=tmp_path / VALIDATION_RESULTS_FILENAME,
    )
    cloud_output = RawValidationOutput(
        local_path=tmp_path / VALIDATION_RESULTS_FILENAME,
        artifact_location=ArtifactLocation(
            storage_backend="s3",
            artifact_uri="s3://unit-test-bucket/validation/results.json",
            artifact_key="validation/results.json",
            s3_uri="s3://unit-test-bucket/validation/results.json",
        ),
    )

    assert local_output.local_path_text.endswith(VALIDATION_RESULTS_FILENAME)
    assert local_output.durable_reference_uri.endswith(VALIDATION_RESULTS_FILENAME)
    assert (
        cloud_output.durable_reference_uri
        == "s3://unit-test-bucket/validation/results.json"
    )


def test_cloud_validation_output_route_writer_uses_provided_store(
    tmp_path,
):
    writes = []

    class FakeStore:
        def __init__(self, bucket: str):
            self.bucket = bucket

        def location(self, **kwargs):
            return ArtifactLocation(
                storage_backend="s3",
                artifact_uri=f"s3://{self.bucket}/{kwargs['filename']}",
                artifact_key=kwargs["filename"],
                s3_uri=f"s3://{self.bucket}/{kwargs['filename']}",
            )

        def write_bytes(self, location, payload):
            writes.append((location.artifact_uri, payload))

    result = raw_file_exists_result()

    output_write = write_validation_output_for_route(
        _validation_output_request(
            tmp_path,
            validation_results=[result],
            validation_path=tmp_path / VALIDATION_RESULTS_FILENAME,
            is_cloud_route=True,
            bucket="unit-test-bucket",
            artifact_store=FakeStore("unit-test-bucket"),
        )
    )

    assert output_write.artifact_location is not None
    assert output_write.artifact_location.artifact_uri == (
        f"s3://unit-test-bucket/{VALIDATION_RESULTS_FILENAME}"
    )
    assert [uri for uri, _ in writes] == [
        f"s3://unit-test-bucket/{VALIDATION_RESULTS_FILENAME}",
        f"s3://unit-test-bucket/{VALIDATION_RESULTS_FILENAME}",
    ]
    assert writes[-1][1] == (tmp_path / VALIDATION_RESULTS_FILENAME).read_bytes()
    assert validation_check_ids(output_write.validation_results) == [
        "RAW_001",
        "RAW_009",
    ]


def _validation_output_request(
    tmp_path,
    *,
    validation_results=None,
    validation_path=None,
    is_cloud_route=False,
    bucket=None,
    artifact_store=None,
) -> ValidationOutputWriteRequest:
    return ValidationOutputWriteRequest(
        validation_results=validation_results or [],
        manifests=[],
        validation_path=validation_path or tmp_path / VALIDATION_RESULTS_FILENAME,
        pipeline_run_id="run-123",
        is_cloud_route=is_cloud_route,
        data_root=tmp_path,
        run_started_at_utc="2026-05-31T00:00:00Z",
        bucket=bucket,
        artifact_reader=ArtifactReader(),
        artifact_store=artifact_store,
    )
