from __future__ import annotations

import csv
import io
import json
from datetime import date
from pathlib import Path
from typing import Any, Callable

from pipelines.extract.bls_laus_extract import parse_monthly_period
from pipelines.flows.run_models import ExtractionPaths, LocalRunContext
from pipelines.flows.run_setup import resolve_s3_bucket
from pipelines.storage.raw_artifacts import (
    ArtifactLocation,
    LocalArtifactStore,
    LocalRawArtifactStore,
    RawArtifactLocation,
    S3ArtifactStore,
    S3RawArtifactStore,
    artifact_store_for_route,
    raw_artifact_store_for_route,
)
from pipelines.utils.config import ProjectConfig, SourceIdentity
from pipelines.utils.hashing import hash_bytes, hash_schema
from pipelines.utils.manifest import (
    ExtractionManifest,
    manifest_to_json_bytes,
    write_manifest,
)
from pipelines.utils.source_resources import source_name_for_resource


RawStoreFactory = Callable[
    [LocalRunContext, str],
    LocalRawArtifactStore | S3RawArtifactStore,
]
ArtifactStoreFactory = Callable[
    [LocalRunContext, str],
    LocalArtifactStore | S3ArtifactStore,
]
BucketResolver = Callable[[LocalRunContext], str | None]


def extract_fixture_sources(
    context: LocalRunContext,
    project_config: ProjectConfig,
    *,
    raw_artifact_store_factory: RawStoreFactory | None = None,
    artifact_store_factory: ArtifactStoreFactory | None = None,
    s3_bucket_resolver: BucketResolver | None = None,
) -> ExtractionPaths:
    raw_paths = write_fixture_raw_files(
        context,
        raw_artifact_store_factory=raw_artifact_store_factory,
        s3_bucket_resolver=s3_bucket_resolver,
    )
    manifest_outputs = {
        resource_name: write_fixture_manifest(
            context=context,
            resource_name=resource_name,
            raw_location=raw_location,
            raw_payload=raw_payload,
            row_count=row_count,
            file_format=file_format,
            schema_fields=schema_fields,
            source_identity=project_config.source_identity(
                source_name_for_resource(resource_name, project_config)
            ),
            artifact_store_factory=artifact_store_factory,
            s3_bucket_resolver=s3_bucket_resolver,
        )
        for resource_name, (
            raw_location,
            raw_payload,
            row_count,
            file_format,
            schema_fields,
        ) in raw_paths.items()
    }
    manifest_paths = {
        resource_name: manifest_path
        for resource_name, (manifest_path, _) in manifest_outputs.items()
    }
    manifest_locations = {
        resource_name: manifest_location
        for resource_name, (_, manifest_location) in manifest_outputs.items()
        if manifest_location is not None
    }
    return ExtractionPaths(
        sba_7a_manifest_paths=(manifest_paths["sba_7a_fy2020_present"],),
        sba_504_manifest_paths=(manifest_paths["sba_504_fy2010_present"],),
        census_bds_manifest_paths=(manifest_paths["bds_state_year"],),
        bls_laus_manifest_paths=(manifest_paths["laus_state_month"],),
        manifest_paths=tuple(manifest_paths.values()),
        sba_7a_manifest_locations=tuple(
            [manifest_locations["sba_7a_fy2020_present"]]
        )
        if "sba_7a_fy2020_present" in manifest_locations
        else (),
        sba_504_manifest_locations=tuple(
            [manifest_locations["sba_504_fy2010_present"]]
        )
        if "sba_504_fy2010_present" in manifest_locations
        else (),
        census_bds_manifest_locations=tuple([manifest_locations["bds_state_year"]])
        if "bds_state_year" in manifest_locations
        else (),
        bls_laus_manifest_locations=tuple([manifest_locations["laus_state_month"]])
        if "laus_state_month" in manifest_locations
        else (),
        manifest_locations=tuple(manifest_locations.values()),
    )


def write_fixture_raw_files(
    context: LocalRunContext,
    *,
    raw_artifact_store_factory: RawStoreFactory | None = None,
    s3_bucket_resolver: BucketResolver | None = None,
) -> dict[str, tuple[RawArtifactLocation, bytes, int, str, list[str]]]:
    output: dict[str, tuple[RawArtifactLocation, bytes, int, str, list[str]]] = {}
    ingestion_date = date.fromisoformat(context.run_started_at_utc[:10]).isoformat()
    bucket = (s3_bucket_resolver or resolve_s3_bucket)(context) or "local-fixtures"
    store = (
        raw_artifact_store_factory(context, bucket)
        if raw_artifact_store_factory is not None
        else raw_artifact_store_for_route(
            cloud_route=context.is_cloud_route,
            data_root=context.data_root,
            bucket=bucket,
        )
    )

    def write_fixture_artifact(
        *,
        output_name: str,
        source_system: str,
        dataset_name: str,
        resource_name: str,
        filename: str,
        payload: bytes,
        row_count: int,
        file_format: str,
        schema_fields: list[str],
    ) -> None:
        location = store.location(
            source_system=source_system,
            dataset_name=dataset_name,
            resource_name=resource_name,
            ingestion_date=ingestion_date,
            pipeline_run_id=context.pipeline_run_id,
            filename=filename,
        )
        store.write_bytes(location, payload)
        output[output_name] = (
            location,
            payload,
            row_count,
            file_format,
            schema_fields,
        )

    sba_7a_rows = [sba_7a_row()]
    write_fixture_artifact(
        output_name="sba_7a_fy2020_present",
        source_system="sba",
        dataset_name="7a_foia",
        resource_name="source_period=fy2020_present",
        filename="sba_7a_fixture.csv",
        payload=csv_bytes(sba_7a_rows),
        row_count=len(sba_7a_rows),
        file_format="csv",
        schema_fields=list(sba_7a_rows[0]),
    )

    sba_504_rows = [sba_504_row()]
    write_fixture_artifact(
        output_name="sba_504_fy2010_present",
        source_system="sba",
        dataset_name="504_foia",
        resource_name="source_period=fy2010_present",
        filename="sba_504_fixture.csv",
        payload=csv_bytes(sba_504_rows),
        row_count=len(sba_504_rows),
        file_format="csv",
        schema_fields=list(sba_504_rows[0]),
    )

    census_payload = [
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
            "2026",
            "10",
            "2",
            "20.0",
            "1",
            "10.0",
            "8",
            "30",
            "15",
            "2026",
            "01",
        ],
        [
            "Illinois",
            "2026",
            "20",
            "3",
            "15.0",
            "2",
            "10.0",
            "15",
            "40",
            "20",
            "2026",
            "17",
        ],
    ]
    write_fixture_artifact(
        output_name="bds_state_year",
        source_system="census",
        dataset_name="bds",
        resource_name="grain=state_year",
        filename="bds_state_year_fixture.json",
        payload=json_bytes(census_payload),
        row_count=len(census_payload) - 1,
        file_format="json",
        schema_fields=census_payload[0],
    )

    bls_payload = {
        "normalized_rows": [
            bls_row(
                "LASST010000000000003",
                "01",
                "AL",
                "Alabama",
                "2025",
                "M01",
                3.4,
            ),
            bls_row(
                "LASST010000000000003",
                "01",
                "AL",
                "Alabama",
                "2026",
                "M01",
                3.1,
            ),
            bls_row(
                "LASST170000000000003",
                "17",
                "IL",
                "Illinois",
                "2025",
                "M01",
                4.5,
            ),
            bls_row(
                "LASST170000000000003",
                "17",
                "IL",
                "Illinois",
                "2026",
                "M01",
                4.2,
            ),
        ]
    }
    write_fixture_artifact(
        output_name="laus_state_month",
        source_system="bls",
        dataset_name="laus",
        resource_name="grain=state_month",
        filename="bls_laus_state_month_fixture.json",
        payload=json_bytes(bls_payload),
        row_count=len(bls_payload["normalized_rows"]),
        file_format="json",
        schema_fields=list(bls_payload["normalized_rows"][0]),
    )
    return output


def write_fixture_manifest(
    *,
    context: LocalRunContext,
    resource_name: str,
    raw_location: RawArtifactLocation,
    raw_payload: bytes,
    row_count: int,
    file_format: str,
    schema_fields: list[str],
    source_identity: SourceIdentity,
    artifact_store_factory: ArtifactStoreFactory | None = None,
    s3_bucket_resolver: BucketResolver | None = None,
) -> tuple[Path, ArtifactLocation | None]:
    source_system = source_identity.source_system
    dataset_name = source_identity.dataset_name
    ingestion_date = date.fromisoformat(context.run_started_at_utc[:10]).isoformat()
    manifest_fields = raw_location.manifest_fields()
    manifest = ExtractionManifest(
        pipeline_run_id=context.pipeline_run_id,
        source_system=source_system,
        dataset_name=dataset_name,
        resource_name=resource_name,
        source_url=f"fixture://{resource_name}",
        extracted_at_utc=context.run_started_at_utc,
        ingestion_date=ingestion_date,
        local_raw_path=manifest_fields["local_raw_path"],
        s3_raw_uri=manifest_fields["s3_raw_uri"],
        file_format=file_format,
        row_count=row_count,
        sha256_checksum=hash_bytes(raw_payload),
        schema_hash=hash_schema(schema_fields),
        validation_status="passed",
        request_parameters={"run_mode": context.run_mode},
        column_count=len(schema_fields),
        file_size_bytes=len(raw_payload),
        validation_messages=[],
        storage_backend=manifest_fields["storage_backend"],
        raw_uri=manifest_fields["raw_uri"],
    )
    manifest_path = (
        context.data_root
        / "manifests"
        / source_system
        / f"pipeline_run_id={context.pipeline_run_id}"
        / f"{resource_name}.manifest.json"
    )
    write_manifest(manifest, manifest_path)
    manifest_location = None
    if context.is_cloud_route:
        bucket = (s3_bucket_resolver or resolve_s3_bucket)(context) or "local-fixtures"
        store = (
            artifact_store_factory(context, bucket)
            if artifact_store_factory is not None
            else artifact_store_for_route(
                cloud_route=context.is_cloud_route,
                data_root=context.data_root,
                bucket=bucket,
            )
        )
        manifest_location = store.location(
            prefix="manifests",
            source_system=manifest.source_system,
            dataset_name=manifest.dataset_name,
            resource_name=manifest.resource_name,
            ingestion_date=manifest.ingestion_date,
            pipeline_run_id=manifest.pipeline_run_id,
            filename=manifest_path.name,
        )
        store.write_bytes(
            manifest_location,
            manifest_to_json_bytes(manifest),
        )
    return manifest_path, manifest_location


def csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2) + "\n").encode("utf-8")


def sba_7a_row() -> dict[str, Any]:
    return {
        "asofdate": "3/31/2026",
        "program": "7A",
        "locationid": "1",
        "borrname": "Fixture 7A LLC",
        "borrstreet": "1 Main St",
        "borrcity": "Birmingham",
        "borrstate": "AL",
        "borrzip": "35203",
        "bankname": "Fixture Bank, Inc.",
        "bankfdicnumber": "123",
        "bankncuanumber": "",
        "bankstreet": "2 Bank St",
        "bankcity": "Birmingham",
        "bankstate": "AL",
        "bankzip": "35203",
        "grossapproval": "1000",
        "sbaguaranteedapproval": "750",
        "approvaldate": "1/15/2026",
        "approvalfy": "2026",
        "firstdisbursementdate": "2/1/2026",
        "processingmethod": "Preferred Lenders Program",
        "subprogram": "Guaranty",
        "initialinterestrate": "6",
        "fixedorvariableinterestind": "V",
        "terminmonths": "120",
        "naicscode": "541611",
        "naicsdescription": "Administrative Management",
        "franchisecode": "",
        "franchisename": "",
        "projectcounty": "JEFFERSON",
        "projectstate": "AL",
        "sbadistrictoffice": "ALABAMA DISTRICT OFFICE",
        "congressionaldistrict": "7",
        "businesstype": "CORPORATION",
        "businessage": "Existing",
        "loanstatus": "PIF",
        "paidinfulldate": "",
        "chargeoffdate": "",
        "grosschargeoffamount": "0",
        "revolverstatus": "FALSE",
        "jobssupported": "4",
        "collateralind": "TRUE",
        "soldsecmrktind": "Y",
    }

def sba_504_row() -> dict[str, Any]:
    return {
        "asofdate": "3/31/2026",
        "program": "504",
        "locationid": "2",
        "borrname": "Fixture 504 Inc.",
        "borrstreet": "10 Market St",
        "borrcity": "Chicago",
        "borrstate": "IL",
        "borrzip": "60601",
        "cdc_name": "Fixture CDC",
        "cdc_street": "20 CDC St",
        "cdc_city": "Chicago",
        "cdc_state": "IL",
        "cdc_zip": "60601",
        "thirdpartylender_name": "Third Party Bank",
        "thirdpartylender_city": "Chicago",
        "thirdpartylender_state": "IL",
        "thirdpartydollars": "2500",
        "grossapproval": "3000",
        "approvaldate": "2/20/2026",
        "approvalfy": "2026",
        "firstdisbursementdate": "3/1/2026",
        "processingmethod": "504 Basic",
        "subprogram": "Sec. 504",
        "terminmonths": "240",
        "naicscode": "721110",
        "naicsdescription": "Hotels",
        "franchisecode": "",
        "franchisename": "",
        "projectcounty": "COOK",
        "projectstate": "IL",
        "sbadistrictoffice": "ILLINOIS DISTRICT OFFICE",
        "congressionaldistrict": "1",
        "businesstype": "CORPORATION",
        "businessage": "Existing",
        "loanstatus": "PIF",
        "paidinfulldate": "",
        "chargeoffdate": "",
        "grosschargeoffamount": "0",
        "jobssupported": "8",
        "collateralind": "TRUE",
    }


def bls_row(
    series_id: str,
    state_fips: str,
    state_abbr: str,
    state_name: str,
    year: str,
    period: str,
    value: float,
) -> dict[str, Any]:
    observed_month = parse_monthly_period(year, period)
    if observed_month is None:
        raise ValueError(f"Invalid fixture BLS monthly period: {period}")
    return {
        "series_id": series_id,
        "state_fips": state_fips,
        "state_abbr": state_abbr,
        "state_name": state_name,
        "year": int(year),
        "period": period,
        "observed_month": observed_month.isoformat(),
        "value": value,
        "footnotes": [],
    }
