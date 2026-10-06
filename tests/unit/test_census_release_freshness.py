"""Distinguish Census publication lag from missing a verified release."""

import duckdb
import pytest
import pandas as pd

from pipelines.utils.config import load_project_config
from pipelines.utils.reporting_policy import dbt_policy_vars
from tests.unit.config_test_helpers import mutate_config_file
from tests.unit.test_reporting_methodology import render_model


def test_pipeline_health_counts_latest_published_as_healthy():
    """A normal Census publication lag must not remain a pipeline warning."""
    with duckdb.connect() as con:
        con.execute("""create table stg_pipeline_run_summary as select
            'run' as pipeline_run_ids, timestamp '2026-10-04' as loaded_at_utc,
            4 as raw_table_count, 'passed' as validation_status""")
        con.execute("""create table mart_pipeline_validation_summary as select
            0 as failed_check_count, 0 as warning_check_count, 1 as passed_check_count,
            timestamp '2026-10-04' as latest_checked_at_utc""")
        con.execute("""create table mart_pipeline_source_freshness as select
            freshness_status, timestamp '2026-10-04' as freshness_checked_at_utc
            from (values ('current'),('latest_published'),('stale'),('unknown')) as states(freshness_status)""")
        row = (
            con.execute(
                render_model("dbt/models/marts/pipeline/mart_pipeline_run_summary.sql")
            )
            .df()
            .iloc[0]
        )
        assert row.current_source_resource_count == 2
        assert row.stale_or_unknown_source_resource_count == 2


@pytest.mark.parametrize(
    ("year", "extracted", "release", "expected"),
    [
        (2023, "2026-06-02", {}, "latest_published"),
        (2022, "2026-06-02", {}, "stale"),
        (2023, "2025-06-02", {}, "unknown"),
        (2023, "2026-06-02", {"verified_on": "2026-06-01"}, "unknown"),
        (2023, "2026-06-02", {"verified_on": "2026-10-05"}, "unknown"),
        (2023, "2026-06-02", {"verified_on": "2026-07-06"}, "latest_published"),
        (2023, "2026-06-02", {"verified_on": "2026-07-05"}, "unknown"),
        (2023, "2026-06-02", {"latest_year": 2024}, "stale"),
        (2024, "2026-06-02", {}, "unknown"),
        (2023, "2026-06-02", {"verified_on": None}, "unknown"),
        (2023, "2026-06-02", {"verified_on": "malformed"}, "unknown"),
        (2023, "2026-06-02", {"latest_year": None}, "unknown"),
        (2023, "2026-06-02", {"released_on": None}, "unknown"),
        (2023, "2026-06-02", None, "unknown"),
    ],
)
def test_bds_release_freshness(year, extracted, release, expected):
    """Run actual model SQL on lagged, missed, stale and unverifiable inputs."""
    policy = (
        {
            "census_bds_release": {
                "latest_year": 2023,
                "released_on": "2025-09-25",
                "verified_on": "2026-10-03",
                "source_url": "https://www.census.gov/programs-surveys/bds/news-updates/updates.html",
            }
            | release
        }
        if release is not None
        else {}
    )
    with duckdb.connect() as con:
        con.execute(f"""create table stg_ingestion_manifest as select
            'census' as source_system, 'bds' as dataset_name, 'state' as resource_name,
            '{extracted}T00:00:00Z' as extracted_at_utc, date '{extracted}' as ingestion_date,
            1 as row_count, true as is_latest_successful_snapshot, 'run' as pipeline_run_id""")
        con.execute(
            "create table fact_sba_loans as select cast(null as date) as approval_date"
        )
        con.execute(
            f"create table fact_bds_state_year as select date '{year}-03-12' as bds_reference_date"
        )
        con.execute(
            "create table fact_laus_state_month as select cast(null as date) as observed_month"
        )
        result = (
            con.execute(
                render_model(
                    "dbt/models/marts/pipeline/mart_pipeline_source_freshness.sql",
                    {
                        "freshness_checked_at": "2026-10-04T00:00:00",
                        "reporting_policy": policy,
                    },
                )
            )
            .df()
            .iloc[0]
        )
        assert result.freshness_status == expected
        if year == 2023:
            assert result.observation_age_days == 1302


@pytest.mark.parametrize(
    "field,value",
    [("max_release_check_age_days", 0), ("max_observation_age_days", 1461)],
)
def test_bds_policy_rejects_disabled_or_age_based_release_checks(
    tmp_path, field, value
):
    """Do not silently replace publication verification with a wider age limit."""
    config_dir = mutate_config_file(
        tmp_path,
        "freshness_rules.yml",
        lambda config: config["freshness_rules"]["census_bds"].update({field: value}),
    )
    with pytest.raises(ValueError, match="Census BDS|positive integer"):
        load_project_config(config_dir)


@pytest.mark.parametrize(
    "changes",
    [
        {"latest_year": True},
        {"latest_year": 2026},
        {"verified_on": "2025-01-01"},
        {"source_url": ""},
    ],
)
def test_bds_policy_rejects_unsupported_publisher_evidence(tmp_path, changes):
    """Publisher dates, year and reference must agree before running dbt."""
    config_dir = mutate_config_file(
        tmp_path,
        "reporting_policy.yml",
        lambda config: config["reporting_policy"]["census_bds_release"].update(changes),
    )
    with pytest.raises(ValueError, match="Census BDS"):
        dbt_policy_vars(config_dir)


@pytest.mark.parametrize(
    ("system", "observed", "checked", "extracted", "expected", "reason"),
    [
        (
            "sba",
            "2026-06-29",
            "2026-10-05",
            "2026-10-05",
            "latest_published",
            "latest_verified_release",
        ),
        (
            "sba",
            "2026-03-31",
            "2026-10-05",
            "2026-10-05",
            "stale",
            "newer_release_available",
        ),
        (
            "sba",
            "2026-09-30",
            "2026-10-05",
            "2026-10-05",
            "unknown",
            "publisher_evidence_unknown",
        ),
        (
            "sba",
            "2026-06-30",
            "2026-10-05",
            "2026-01-01",
            "unknown",
            "download_review_due",
        ),
        (
            "bls",
            "2026-08-01",
            "2026-10-05",
            "2026-10-05",
            "latest_published",
            "latest_verified_release",
        ),
        (
            "bls",
            "2026-07-01",
            "2026-10-05",
            "2026-10-05",
            "stale",
            "newer_release_available",
        ),
        (
            "bls",
            "2026-09-01",
            "2026-10-05",
            "2026-10-05",
            "unknown",
            "publisher_evidence_unknown",
        ),
        (
            "bls",
            "2026-08-01",
            "2026-10-20",
            "2026-10-05",
            "unknown",
            "publisher_verification_due",
        ),
        (
            "bls",
            "2026-08-01",
            "2026-11-06",
            "2026-10-05",
            "unknown",
            "publisher_verification_due",
        ),
        (
            "bls",
            "2026-08-01",
            "2026-10-05",
            "2026-06-01",
            "unknown",
            "download_review_due",
        ),
    ],
)
def test_publication_period_and_review_status(
    system, observed, checked, extracted, expected, reason
):
    """A source publication, not elapsed observation age or a schedule, decides staleness."""
    policy = dbt_policy_vars()["reporting_policy"]
    with duckdb.connect() as con:
        con.execute(f"""create table stg_ingestion_manifest as select
            '{system}' as source_system, 'dataset' as dataset_name, 'resource' as resource_name,
            '{extracted}T00:00:00Z' as extracted_at_utc, date '{extracted}' as ingestion_date,
            1 as row_count, true as is_latest_successful_snapshot, 'run' as pipeline_run_id""")
        for name, field, source in (
            ("fact_sba_loans", "approval_date", "sba"),
            ("fact_bds_state_year", "bds_reference_date", "census"),
            ("fact_laus_state_month", "observed_month", "bls"),
        ):
            value = f"date '{observed}'" if source == system else "cast(null as date)"
            con.execute(f"create table {name} as select {value} as {field}")
        result = (
            con.execute(
                render_model(
                    "dbt/models/marts/pipeline/mart_pipeline_source_freshness.sql",
                    {"freshness_checked_at": checked, "reporting_policy": policy},
                )
            )
            .df()
            .iloc[0]
        )
        assert result.freshness_status == expected
        assert result.freshness_reason == reason
        assert result.max_observation_age_days is None or pd.isna(
            result.max_observation_age_days
        )
        if system == "sba":
            assert pd.isna(result.publication_date)
        else:
            assert str(result.publication_date.date()) == "2026-09-18"


@pytest.mark.parametrize("source", ["sba_foia", "census_bds", "bls_laus"])
def test_no_source_can_reintroduce_observation_age_staleness(tmp_path, source):
    """Reject an age-only rule even for quarterly or monthly publishers."""
    config_dir = mutate_config_file(
        tmp_path,
        "freshness_rules.yml",
        lambda config: config["freshness_rules"][source].update(
            max_observation_age_days=90
        ),
    )
    with pytest.raises(ValueError, match="release-based freshness"):
        load_project_config(config_dir)
