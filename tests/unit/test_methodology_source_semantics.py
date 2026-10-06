"""Exercise source semantics on missing, zero and cross-program observations."""

import duckdb
import pandas as pd
import pytest

from tests.unit.test_reporting_methodology import render_model


def test_sba_monthly_yoy_keeps_calendar_identity_across_missing_months():
    with duckdb.connect() as con:
        con.execute("create table dim_state(state_key varchar, state_name varchar)")
        con.execute("""create table fact_sba_loans as select * from (values
            ('01',date '2024-10-01',100),('01',date '2024-11-01',200),
            ('01',date '2025-11-01',300),('01',date '2025-12-01',400))
            as t(project_state_key,approval_date,gross_approval_amount)""")
        rows = con.execute(
            render_model("dbt/models/marts/lending/mart_lending_monthly_state.sql")
        ).df()
        november = rows.loc[rows.approval_month.eq(pd.Timestamp("2025-11-01"))].iloc[0]
        december = rows.loc[rows.approval_month.eq(pd.Timestamp("2025-12-01"))].iloc[0]
        assert november.approved_loan_amount_yoy_growth_pct == pytest.approx(0.5)
        assert november.loan_count_yoy_growth_pct == 0
        assert pd.isna(december.approved_loan_amount_yoy_growth_pct)
        assert pd.isna(december.loan_count_yoy_growth_pct)


@pytest.mark.parametrize("model", ["annual", "monthly"])
def test_average_counts_zero_amounts_and_excludes_unknown_amounts(model):
    with duckdb.connect() as con:
        con.execute("create table dim_state(state_key varchar, state_name varchar)")
        con.execute("""create table fact_sba_loans as select * from (values
            ('01',2023,date '2023-06-01',100),('01',2023,date '2023-06-01',0),
            ('01',2023,date '2023-06-01',null),('02',2023,date '2023-06-01',null))
            as t(project_state_key,approval_year,approval_date,gross_approval_amount)""")
        rows = (
            con.execute(
                render_model(f"dbt/models/marts/lending/mart_lending_{model}_state.sql")
            )
            .df()
            .set_index("state_key")
        )
        assert rows.loc["01", "loan_count"] == 3
        assert rows.loc["01", "approval_amount_coverage_count"] == 2
        assert rows.loc["01", "total_approved_loan_amount"] == 100
        assert rows.loc["01", "average_loan_size"] == 50
        assert rows.loc["02", "approval_amount_coverage_count"] == 0
        assert pd.isna(rows.loc["02", "average_loan_size"])


def test_504_financing_ratio_uses_the_same_known_records_in_both_sums():
    with duckdb.connect() as con:
        con.execute("create table dim_state(state_key varchar, state_name varchar)")
        con.execute("""create table fact_sba_loans as select * from (values
            ('01',2023,'7a',1000,999), ('01',2023,'504',100,150),
            ('01',2023,'504',200,null),('01',2023,'504',null,80),
            ('01',2023,'504',0,0),('02',2023,'7a',100,null))
            as t(project_state_key,approval_year,loan_program_key,gross_approval_amount,third_party_dollars)""")
        for column in [
            "term_months",
            "initial_interest_rate",
            "sba_guaranteed_approval_amount",
        ]:
            con.execute(f"alter table fact_sba_loans add column {column} double")
        con.execute(
            "alter table fact_sba_loans add column fixed_or_variable_interest_indicator varchar"
        )
        con.execute(
            "update fact_sba_loans set fixed_or_variable_interest_indicator='unrecognized'"
        )
        rows = (
            con.execute(
                render_model(
                    "dbt/models/marts/lending/mart_lending_terms_pricing_state_period.sql"
                )
            )
            .df()
            .set_index("state_key")
        )
        assert rows.loc["01", "program_504_loan_count"] == 4
        assert rows.loc["01", "paired_504_coverage_count"] == 2
        assert rows.loc["01", "paired_504_approval_amount"] == 100
        assert rows.loc["01", "paired_504_third_party_dollars"] == 150
        assert rows.loc["01", "known_504_third_party_to_sba_amount_rate"] == 1.5
        assert rows.loc["01", "paired_504_coverage_rate"] == 0.5
        assert rows.loc["01", "interest_type_coverage_count"] == 0
        assert pd.isna(rows.loc["02", "known_504_third_party_to_sba_amount_rate"])
        assert pd.isna(rows.loc["02", "paired_504_coverage_rate"])


def test_census_freshness_uses_verified_release_and_preserves_march_reference():
    with duckdb.connect() as con:
        con.execute("""create table stg_ingestion_manifest as select 'census' as source_system,
            'bds' as dataset_name,'state' as resource_name,'2026-06-02T00:00:00Z' as extracted_at_utc,
            date '2026-06-02' as ingestion_date, 1 as row_count,
            true as is_latest_successful_snapshot,'run' as pipeline_run_id""")
        con.execute(
            "create table fact_sba_loans as select cast(null as date) as approval_date"
        )
        con.execute(
            "create table fact_bds_state_year as select 2023 as year, date '2023-03-12' as bds_reference_date"
        )
        con.execute(
            "create table fact_laus_state_month as select cast(null as date) as observed_month"
        )
        row = (
            con.execute(
                render_model(
                    "dbt/models/marts/pipeline/mart_pipeline_source_freshness.sql",
                    {"freshness_checked_at": "2026-10-04T00:00:00"},
                )
            )
            .df()
            .iloc[0]
        )
        assert row.latest_observation_date == pd.Timestamp("2023-03-12")
        assert row.observation_date_basis == "march_12_reference"
        assert row.observation_age_days == 1302
        assert row.extract_age_days == 124
        assert row.snapshot_validity_status == "valid_selected_snapshot"
        assert row.freshness_status == "latest_published"


def test_guarantee_ratio_is_paired_and_cannot_include_504_values():
    with duckdb.connect() as con:
        con.execute("create table dim_state(state_key varchar, state_name varchar)")
        con.execute("""create table fact_sba_loans as select * from (values
            ('01',2023,'7a',100,75),('01',2023,'7a',200,null),
            ('01',2023,'7a',null,30),('01',2023,'7a',0,0),
            ('01',2023,'504',100,999))
            as t(project_state_key,approval_year,loan_program_key,gross_approval_amount,sba_guaranteed_approval_amount)""")
        for column in ["term_months", "initial_interest_rate", "third_party_dollars"]:
            con.execute(f"alter table fact_sba_loans add column {column} double")
        con.execute(
            "alter table fact_sba_loans add column fixed_or_variable_interest_indicator varchar"
        )
        row = (
            con.execute(
                render_model(
                    "dbt/models/marts/lending/mart_lending_terms_pricing_state_period.sql"
                )
            )
            .df()
            .iloc[0]
        )
        assert row.program_7a_loan_count == 4
        assert row.paired_7a_coverage_count == 2
        assert row.paired_7a_guaranteed_amount == 75
        assert row.paired_7a_approval_amount == 100
        assert row.paired_7a_coverage_rate == 0.5
        assert row.seven_a_sba_guarantee_rate == 0.75
        assert row.sba_guaranteed_approval_amount == 105
