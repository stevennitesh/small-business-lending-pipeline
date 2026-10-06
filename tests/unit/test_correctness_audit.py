"""Exercise confirmed ingestion and publication failures on small populations."""

import io
import json
from pathlib import Path

from botocore.exceptions import ClientError
import duckdb
import pytest
import pandas as pd
from jinja2 import Environment
from types import SimpleNamespace

from pipelines.extract.bls_laus_api import normalize_bls_response
from pipelines.load.snowflake_loader import _publish_raw_snapshot
from pipelines.load.duckdb_loader import load_raw_extracts, RawLoadError
from pipelines.flows.run_setup import initialize_run_context
from pipelines.load.snowflake_stage_sources import load_s3_manifest_group
from pipelines.powerbi.export_contract import _publish_csv_exports
from pipelines.powerbi.export_schema import BI_EXPORT_TABLES
from pipelines.storage.raw_artifacts import LocalRawArtifactStore, S3RawArtifactStore
from pipelines.validation.bls_laus_payload_checks import check_bls_laus_payload
from pipelines.validation.census_bds_payload_checks import check_census_bds_payload
from scripts.cleanup_local_data import find_candidates
from tests.unit.artifact_store_test_helpers import FakeS3ObjectClient
from tests.unit.extract_test_helpers import bls_laus_series_configs
from tests.unit.snowflake_test_helpers import FakeS3Client, FakeSnowflakeConnection
from tests.unit.raw_load_test_helpers import (
    build_raw_load_fixture_manifests,
    raw_load_validation_results,
)
from pipelines.validation.validation_result_io import write_validation_results


@pytest.mark.parametrize("value", ["bad", None, "NaN", "Infinity", True])
def test_malformed_bls_month_is_retained_and_blocks_validation(value):
    """One valid month must not hide a bad month in the same series."""
    series = bls_laus_series_configs()[0]
    response = {
        "status": "REQUEST_SUCCEEDED",
        "Results": {
            "series": [
                {
                    "seriesID": series.series_id,
                    "data": [
                        {"year": "2023", "period": "M01", "value": "2.5"},
                        {"year": "2023", "period": "M02", "value": value},
                    ],
                }
            ]
        },
    }
    rows = normalize_bls_response([response], series_by_id={series.series_id: series})
    assert len(rows) == 2
    results = check_bls_laus_payload(
        {"normalized_rows": rows},
        expected_series_ids=(series.series_id,),
        pipeline_run_id="audit",
    )
    assert any(result.status == "failed" for result in results)


@pytest.mark.parametrize(
    "mutation", ["duplicate", "period", "year", "unexpected_series"]
)
def test_bls_rejects_inconsistent_or_duplicate_months(mutation):
    """Normalized month identities must agree and remain unique."""
    row = {
        "series_id": "series",
        "observed_month": "2023-01-01",
        "period": "M01",
        "year": 2023,
        "value": 2.5,
    }
    rows = [row]
    if mutation == "duplicate":
        rows.append(dict(row))
    else:
        field, value = {
            "period": ("period", "M02"),
            "year": ("year", 2024),
            "unexpected_series": ("series_id", "other"),
        }[mutation]
        row[field] = value
    results = check_bls_laus_payload(
        {"normalized_rows": rows},
        expected_series_ids=("series",),
        pipeline_run_id="audit",
    )
    assert any(result.status == "failed" for result in results)


@pytest.mark.parametrize(
    "rows",
    [
        [["2023", "01"], ["2023", "01"]],
        [["2023"]],
        [["2023", "01"], ["2023", "02"], ["2024", "01"]],
    ],
)
def test_census_checks_retained_row_grain_and_each_year_coverage(rows):
    """Union coverage cannot conceal a missing state in a returned year."""
    results = check_census_bds_payload(
        [["YEAR", "state"], *rows],
        required_variables=("YEAR", "state"),
        expected_state_count=2,
        pipeline_run_id="audit",
    )
    assert any(result.status == "failed" for result in results)


@pytest.mark.parametrize("cloud", [False, True])
@pytest.mark.parametrize("streamed", [False, True])
def test_raw_store_refuses_to_overwrite_a_snapshot(tmp_path, cloud, streamed):
    """Reusing a raw artifact location preserves its original bytes."""
    client = FakeS3ObjectClient()
    store = (
        S3RawArtifactStore(bucket="bucket", s3_client=client)
        if cloud
        else LocalRawArtifactStore(data_root=tmp_path)
    )
    location = store.location(
        source_system="sba",
        dataset_name="test",
        resource_name="test",
        ingestion_date="2026-10-04",
        pipeline_run_id="audit",
        filename="input.csv",
    )
    write = store.write_file if streamed else store.write_bytes
    write(location, io.BytesIO(b"first") if streamed else b"first")
    with pytest.raises(ClientError if cloud else FileExistsError):
        write(location, io.BytesIO(b"second") if streamed else b"second")
    assert store.read_bytes(location) == b"first"


def test_default_cleanup_preserves_every_raw_run(tmp_path):
    """Default generated-output cleanup has no implicit raw retention selector."""
    for run in ("old", "new"):
        path = tmp_path / "data/raw/sba" / f"pipeline_run_id={run}" / "raw.csv"
        path.parent.mkdir(parents=True)
        path.write_text("retain\n")
    assert find_candidates(tmp_path) == []


def test_export_publication_failure_restores_previous_set(tmp_path, monkeypatch):
    """A rename failure cannot leave half the modeled CSV set replaced."""
    exports, staging = tmp_path / "exports", tmp_path / "staging"
    exports.mkdir()
    staging.mkdir()
    for name in BI_EXPORT_TABLES:
        (exports / f"{name}.csv").write_text("old\n")
        (staging / f"{name}.csv").write_text("new\n")
    (exports / "notes.csv").write_text("user data\n")
    replace = Path.replace

    def fail_second_publish(path, destination):
        if path == staging / f"{BI_EXPORT_TABLES[1]}.csv":
            raise OSError("simulated publication failure")
        return replace(path, destination)

    monkeypatch.setattr(Path, "replace", fail_second_publish)
    with pytest.raises(OSError, match="publication"):
        _publish_csv_exports(staging, exports)
    assert all(
        (exports / f"{name}.csv").read_text() == "old\n" for name in BI_EXPORT_TABLES
    )
    assert (exports / "notes.csv").read_text() == "user data\n"


def test_snowflake_maps_each_file_header_and_selects_exact_keys():
    """Reordering and adding a source field preserves the target meaning."""
    connection = FakeSnowflakeConnection()
    manifests = [
        {
            "raw_uri": f"s3://bucket/{key}",
            "s3_raw_uri": f"s3://bucket/{key}",
            "pipeline_run_id": "audit",
            "source_system": "sba",
            "dataset_name": "7a_504_foia",
            "resource_name": "test",
            "ingestion_date": "2026-10-04",
            "sha256_checksum": "checksum",
            "storage_backend": "s3",
        }
        for key in ("first.csv", "second.csv")
    ]
    load_s3_manifest_group(
        connection,
        raw_schema="RAW",
        source_table="raw_sba_7a_foia",
        table_name="_LOAD_TEST",
        manifests=manifests,
        stage_name="STAGE",
        s3_client=FakeS3Client(
            {
                "first.csv": "LoanNumber,GrossApproval\n",
                "second.csv": "GrossApproval,LoanNumber,Extra\n",
            }
        ),
    )
    copies = [sql for sql in connection.sql_statements if sql.startswith("copy into")]
    assert "select source.$1, source.$2, null," in copies[0]
    assert "select source.$2, source.$1, source.$3," in copies[1]
    assert "files = ('first.csv')" in copies[0]
    assert "files = ('second.csv')" in copies[1]


def test_snowflake_publication_rolls_back_all_tables_on_late_failure():
    """Execute the publication DML in DuckDB to prove snapshot rollback."""

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def execute(self, sql):
            if sql.startswith("describe table"):
                return self
            if sql.startswith(("create table", "alter table")):
                return self  # Existing fixture schemas already match candidates.
            if sql.startswith('insert into "RAW"."RAW_SBA_504_FOIA"'):
                raise RuntimeError("late insert failure")
            con.execute(sql)
            return self

        def fetchall(self):
            return [("VALUE", "VARCHAR", "COLUMN")]

    class Connection:
        def cursor(self):
            return Cursor()

    with duckdb.connect() as con:
        con.execute("create schema raw")
        for name in ("RAW_SBA_7A_FOIA", "RAW_SBA_504_FOIA"):
            con.execute(f"create table raw.{name} as select 'old' as value")
            con.execute(f"create table raw._LOAD_{name} as select 'new' as value")
        with pytest.raises(RuntimeError, match="late insert"):
            _publish_raw_snapshot(
                Connection(),
                "RAW",
                {
                    "raw_sba_7a_foia": "_LOAD_RAW_SBA_7A_FOIA",
                    "raw_sba_504_foia": "_LOAD_RAW_SBA_504_FOIA",
                },
            )
        for name in ("RAW_SBA_7A_FOIA", "RAW_SBA_504_FOIA"):
            assert con.execute(f"select value from raw.{name}").fetchall() == [("old",)]


def test_local_loader_detects_same_count_file_change_before_replacement(tmp_path):
    """Retained validation cannot authorize different bytes at the same path."""
    manifests = build_raw_load_fixture_manifests(tmp_path)
    validation = write_validation_results(
        raw_load_validation_results(manifests), tmp_path / "validation.json"
    )
    kwargs = dict(
        duckdb_path=tmp_path / "warehouse.duckdb",
        sba_7a_manifest_paths=manifests["sba_7a"],
        sba_504_manifest_paths=manifests["sba_504"],
        census_bds_manifest_paths=manifests["census"],
        bls_laus_manifest_paths=manifests["bls"],
        validation_result_paths=[validation],
    )
    load_raw_extracts(**kwargs)
    manifest = json.loads(manifests["sba_7a"][0].read_text())
    raw = Path(manifest["local_raw_path"])
    raw.write_text(raw.read_text().replace("1000", "9000"))
    with pytest.raises(RawLoadError, match="changed since validation"):
        load_raw_extracts(**kwargs)
    with duckdb.connect(str(kwargs["duckdb_path"])) as con:
        assert (
            con.execute("select count(*) from raw.raw_sba_7a_foia").fetchone()[0] == 2
        )
        assert "9000" not in [
            row[0]
            for row in con.execute(
                "select GrossApproval from raw.raw_sba_7a_foia"
            ).fetchall()
        ]


def test_duplicate_raw_manifests_cannot_multiply_the_loaded_population(tmp_path):
    """Summing duplicated expected row counts is not a valid reconciliation."""
    manifests = build_raw_load_fixture_manifests(tmp_path)
    validation = write_validation_results(
        raw_load_validation_results(manifests), tmp_path / "validation.json"
    )
    with pytest.raises(RawLoadError, match="Duplicate raw manifest"):
        load_raw_extracts(
            duckdb_path=tmp_path / "warehouse.duckdb",
            sba_7a_manifest_paths=manifests["sba_7a"] * 2,
            sba_504_manifest_paths=manifests["sba_504"],
            census_bds_manifest_paths=manifests["census"],
            bls_laus_manifest_paths=manifests["bls"],
            validation_result_paths=[validation],
        )


@pytest.mark.parametrize("violation", ["route", "evidence", "live_warehouse"])
def test_run_setup_preserves_existing_custody(tmp_path, violation):
    """Invalid routing and fixture/rerun mistakes fail before generated writes."""
    kwargs = dict(
        run_mode="local",
        extract_mode="fixture",
        dbt_target="dev_duckdb",
        data_root=str(tmp_path / "data"),
        duckdb_path=str(tmp_path / "warehouse.duckdb"),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / "profiles"),
        pipeline_run_id="audit",
    )
    if violation == "route":
        kwargs["dbt_target"] = "prod_snowflake"
    elif violation == "evidence":
        path = tmp_path / "data/validation/pipeline_run_id=audit/run_summary.json"
        path.parent.mkdir(parents=True)
        path.write_text("prior success\n")
    else:
        with duckdb.connect(kwargs["duckdb_path"]) as con:
            con.execute("create schema raw")
            con.execute(
                "create table raw.raw_ingestion_manifest as select 'https://publisher.example/input' as source_url"
            )
    with pytest.raises((ValueError, FileExistsError)):
        initialize_run_context(**kwargs)
    if violation == "evidence":
        assert path.read_text() == "prior success\n"


def test_latest_selection_survives_failed_newer_snapshot_and_ties():
    """Execute the actual staging SQL; select exactly one passing snapshot."""
    base = dict(
        pipeline_run_id="old",
        source_system="sba",
        dataset_name="foia",
        resource_name="file",
        source_url="url",
        extracted_at_utc="2025-01-01T00:00:00Z",
        ingestion_date="2025-01-01",
        storage_backend="local",
        raw_uri="old.csv",
        local_raw_path="old.csv",
        s3_raw_uri=None,
        file_format="csv",
        row_count=1,
        sha256_checksum="hash",
        schema_hash="schema",
        validation_status="passed",
        request_parameters="{}",
        column_count=1,
        file_size_bytes=10,
        validation_messages="[]",
    )
    rows = [
        base,
        {**base, "raw_uri": "tied.csv"},
        {
            **base,
            "pipeline_run_id": "new",
            "raw_uri": "failed.csv",
            "validation_status": "failed",
            "extracted_at_utc": "2026-01-01T00:00:00Z",
        },
    ]
    env = Environment()
    env.globals["source"] = lambda schema, table: table
    sql = env.from_string(
        Path("dbt/models/staging/audit/stg_ingestion_manifest.sql").read_text()
    ).render()
    with duckdb.connect() as con:
        con.register("raw_ingestion_manifest", pd.DataFrame(rows))
        selected = con.execute(sql).df().query("is_latest_successful_snapshot")
        assert selected.raw_uri.tolist() == ["tied.csv"]


@pytest.mark.parametrize("program", ["7a", "504"])
def test_negative_sba_components_become_unknown_before_coverage_counts(program):
    """Run source staging SQL so negative values cannot enter paired means/ratios."""
    from pipelines.extract.fixture_payloads import sba_7a_row, sba_504_row
    from pipelines.load.raw_load_metadata import manifest_raw_row_metadata

    row = sba_7a_row() if program == "7a" else sba_504_row()
    fields = {
        "TermInMonths": "term_months",
        "JobsSupported": "jobs_supported",
        "GrossChargeoffAmount": "gross_chargeoff_amount",
    }
    fields.update(
        {
            "SBAGuaranteedApproval": "sba_guaranteed_approval_amount",
            "InitialInterestRate": "initial_interest_rate",
        }
        if program == "7a"
        else {"ThirdPartyDollars": "third_party_dollars"}
    )
    for field in fields:
        row[field.lower()] = "-9"
    manifest = dict(
        pipeline_run_id="audit",
        source_system="sba",
        dataset_name="7a_504_foia",
        resource_name=f"sba_{program}_current",
        ingestion_date="2026-10-04",
        storage_backend="local",
        local_raw_path="raw.csv",
        raw_uri="raw.csv",
        s3_raw_uri="s3://bucket/raw.csv",
        sha256_checksum="hash",
    )
    row.update(manifest_raw_row_metadata(manifest))
    env = Environment(extensions=["jinja2.ext.do"])
    env.globals.update(
        source=lambda schema, table: table,
        ref=lambda name: name,
        target=SimpleNamespace(type="duckdb"),
    )
    macros = "\n".join(
        Path(f"dbt/macros/{name}.sql").read_text()
        for name in ("date_compat", "generate_surrogate_key", "clean_lender_name")
    )
    sql = env.from_string(
        macros + Path(f"dbt/models/staging/sba/stg_sba_{program}_loans.sql").read_text()
    ).render()
    with duckdb.connect() as con:
        con.register(f"raw_sba_{program}_foia", pd.DataFrame([row]))
        con.register("ref_state", pd.read_csv("dbt/seeds/ref_state.csv", dtype=str))
        con.register(
            "stg_ingestion_manifest",
            pd.DataFrame(
                [
                    {
                        **manifest,
                        "validation_status": "passed",
                        "is_latest_successful_snapshot": True,
                    }
                ]
            ),
        )
        result = con.execute(sql).df().iloc[0]
        assert all(pd.isna(result[column]) for column in fields.values())


def test_ambiguous_sba_discovery_cannot_pick_an_arbitrary_release():
    """Two matching download URLs require an explicit resource decision."""
    from pipelines.extract.sba_resources import resolve_sba_resources
    from pipelines.utils.source_config_models import load_sba_resources_config
    from tests.unit.extract_test_helpers import sample_sba_package_metadata

    metadata = sample_sba_package_metadata()
    metadata["resources"].append(
        {**metadata["resources"][0], "url": "https://publisher.example/another.xlsx"}
    )
    with pytest.raises(ValueError, match="Ambiguous"):
        resolve_sba_resources(load_sba_resources_config().resources, metadata)


def test_invalid_raw_json_has_retained_validation_evidence(tmp_path):
    """A decode error must still write a blocking, source-specific result."""
    from pipelines.flows.raw_validation import validate_raw_outputs_for_flow
    from pipelines.validation.validation_failures import ValidationFailedError
    from tests.unit.validation_flow_test_helpers import fixture_validation_inputs

    config, context, extraction = fixture_validation_inputs(
        tmp_path, pipeline_run_id="bad-json"
    )
    manifest = json.loads(extraction.census_bds_manifest_paths[0].read_text())
    Path(manifest["local_raw_path"]).write_text("{broken JSON")
    with pytest.raises(ValidationFailedError):
        validate_raw_outputs_for_flow(context, extraction, config)
    results = json.loads(
        (context.run_validation_dir / "validation_results.json").read_text()
    )
    assert any(
        row["validation_check_id"] == "RAW_015" and row["status"] == "failed"
        for row in results
    )


def test_standalone_raw_upload_uses_the_manifest_key_and_cannot_overwrite(tmp_path):
    """Promotion must preserve program/grain path segments declared at extraction."""
    from pipelines.load.s3_upload_items import build_raw_upload_item
    from pipelines.load.s3_loader import upload_items_to_s3, S3UploadRequiredError

    raw = tmp_path / "raw.csv"
    raw.write_text("first\n")
    item = build_raw_upload_item(
        {
            "local_raw_path": str(raw),
            "source_system": "sba",
            "dataset_name": "7a_504_foia",
            "resource_name": "sba_7a_current",
            "pipeline_run_id": "audit",
            "ingestion_date": "2026-10-04",
            "s3_raw_uri": "s3://bucket/raw/sba/7a_foia/source_period=current/raw.csv",
        }
    )
    assert item.s3_key == "raw/sba/7a_foia/source_period=current/raw.csv"
    client = FakeS3ObjectClient()
    upload_items_to_s3([item], bucket="bucket", required=True, s3_client=client)
    raw.write_text("second\n")
    with pytest.raises(S3UploadRequiredError):
        upload_items_to_s3([item], bucket="bucket", required=True, s3_client=client)
    assert client.objects[("bucket", item.s3_key)] == b"first\n"


@pytest.mark.parametrize("violation", ["missing_column", "prohibited_column"])
def test_cloud_bi_validation_enforces_the_modeled_column_boundary(
    monkeypatch, violation
):
    """A nonempty table alone does not certify safe, usable BI columns."""
    from pipelines.flows import dbt_bi
    from pipelines.powerbi.export_schema import REQUIRED_EXPORT_COLUMNS

    connection = FakeSnowflakeConnection()
    columns = set(REQUIRED_EXPORT_COLUMNS["bi_executive_overview"])
    if violation == "missing_column":
        columns.remove("loan_count")
    else:
        columns.add("BORROWER_NAME")
    connection.table_columns["BI.BI_EXECUTIVE_OVERVIEW"] = [
        (name.upper(), "varchar") for name in columns
    ]
    monkeypatch.setattr(dbt_bi.SnowflakeConfig, "from_env", lambda: object())
    monkeypatch.setattr(dbt_bi, "connect_to_snowflake", lambda config: connection)
    monkeypatch.setattr(dbt_bi, "snowflake_bi_schema", lambda: "BI")
    with pytest.raises(ValueError, match="missing required|prohibited"):
        dbt_bi.validate_snowflake_bi_tables()
    assert connection.closed


@pytest.mark.parametrize(
    "case",
    [
        "declared",
        "undeclared",
        "wrong_month",
        "unfootnoted",
        "wrong_code",
        "malformed",
        "wrong_date",
    ],
)
def test_bls_official_missing_value_requires_policy_and_publisher_footnote(case):
    """Only documented publisher placeholders may pass the numeric gate."""
    row = {
        "series_id": "series",
        "year": 2025,
        "period": "M10",
        "observed_month": "2025-10-01",
        "value": "-",
        "footnotes": [
            {
                "code": "X",
                "text": "Data unavailable due to the 2025 lapse in appropriations.",
            }
        ],
    }
    omissions = frozenset({(2025, 10)})
    if case == "undeclared":
        omissions = frozenset()
    elif case == "wrong_month":
        row.update(period="M09", observed_month="2025-09-01")
    elif case == "unfootnoted":
        row["footnotes"] = []
    elif case == "wrong_code":
        row["footnotes"][0]["code"] = "P"
    elif case == "malformed":
        row["value"] = "bad"
    elif case == "wrong_date":
        row["observed_month"] = "2025-11-01"
    results = check_bls_laus_payload(
        {"normalized_rows": [row]},
        expected_series_ids=("series",),
        pipeline_run_id="missing-value-test",
        publisher_omissions=omissions,
    )
    numeric = next(
        result for result in results if result.validation_check_id == "BLS_RAW_003"
    )
    if case == "declared":
        assert all(result.status == "passed" for result in results)
        assert numeric.observed_value["publisher_missing_rows"] == 1
        assert row["value"] == "-"
    else:
        assert numeric.status == "failed"


@pytest.mark.parametrize("program", ["7a", "504"])
@pytest.mark.parametrize("present", [True, False])
def test_sba_optional_subprogram_survives_or_becomes_unknown(
    tmp_path, program, present
):
    """A publisher dropping the optional field cannot break either SBA staging table."""
    from pipelines.load.duckdb_loader import _create_or_replace_native_csv_table
    from tests.unit.raw_load_test_helpers import write_raw_load_manifest
    from pipelines.utils.hashing import calculate_sha256

    raw = tmp_path / "source.csv"
    raw.write_text(
        "Program,GrossApproval"
        + (",Subprogram" if present else "")
        + "\n"
        + program
        + ",100"
        + (",SBA Express" if present else "")
        + "\n"
    )
    original = calculate_sha256(raw)
    manifest = write_raw_load_manifest(
        raw_file=raw,
        manifest_path=tmp_path / "manifest.json",
        source_system="sba",
        dataset_name="7a_504_foia",
        resource_name="sba_" + program,
        row_count=1,
        file_format="csv",
        schema_fields=["Program", "GrossApproval"]
        + (["Subprogram"] if present else []),
    )
    with duckdb.connect() as con:
        con.execute("create schema raw")
        _create_or_replace_native_csv_table(
            con, "raw.raw_sba_" + program + "_foia", [json.loads(manifest.read_text())]
        )
        assert con.execute(
            "select Subprogram from raw.raw_sba_" + program + "_foia"
        ).fetchone()[0] == ("SBA Express" if present else None)
    assert calculate_sha256(raw) == original


@pytest.mark.parametrize(
    "value,expected",
    [
        ("6/30/2026", "2026-06-30"),
        ("2026-06-30", "2026-06-30"),
        ("invalid", None),
        ("2026-02-30", None),
        ("", None),
        (None, None),
    ],
)
def test_sba_date_parser_accepts_both_releases_and_rejects_invalid_dates(
    value, expected
):
    """Actual staging macro handles old/new public formats without guessing bad dates."""
    env = Environment()
    macro = Path("dbt/macros/date_compat.sql").read_text()
    expression = env.from_string(macro + "{{ parse_sba_date('value') }}").render(
        target=SimpleNamespace(type="duckdb")
    )
    with duckdb.connect() as con:
        result = con.execute(
            "select " + expression + " from (values (?)) t(value)", [value]
        ).fetchone()[0]
    assert (result.isoformat() if result is not None else None) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("UNKNOWN", None),
        (" unknown ", None),
        ("", None),
        (None, None),
        (" Live   Oak\tBank ", "LIVE OAK BANK"),
    ],
)
def test_lender_name_cleaning_does_not_count_unknown_as_a_reporting_name(
    value, expected
):
    """Source placeholders remain missing; real names retain normalized whitespace."""
    env = Environment()
    macro = Path("dbt/macros/clean_lender_name.sql").read_text()
    expression = env.from_string(macro + "{{ clean_lender_name('value') }}").render(
        target=SimpleNamespace(type="duckdb")
    )
    with duckdb.connect() as con:
        result = con.execute(
            "select " + expression + " from (values (?)) t(value)", [value]
        ).fetchone()[0]
    assert result == expected
