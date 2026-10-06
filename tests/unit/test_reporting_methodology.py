"""Execute the reporting SQL on adversarial small populations, without live calls."""

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import duckdb
from jinja2 import Environment, StrictUndefined
import pytest
import pandas as pd

from pipelines.utils.reporting_policy import dbt_policy_vars


def render_model(path, overrides=None):
    """Render actual model SQL and macros against isolated DuckDB relations."""
    variables = {
        **dbt_policy_vars(),
        "reporting_policy": dbt_policy_vars()["reporting_policy"]
        | {
            "evidence_as_of": "2026-06-02",
            "sba_calendar_end": "2026-03-31",
            "bls_observation_end": "2026-04-30",
            "source_publications": {
                source: evidence | {"verified_on": "2026-10-03"}
                for source, evidence in dbt_policy_vars()["reporting_policy"][
                    "source_publications"
                ].items()
            },
            "census_bds_release": {
                "latest_year": 2023,
                "released_on": "2025-09-25",
                "verified_on": "2026-10-03",
                "source_url": "https://www.census.gov/programs-surveys/bds/news-updates/updates.html",
            },
        },
        "freshness_checked_at": "2026-10-03T00:00:00",
        **(overrides or {}),
    }
    env = Environment(undefined=StrictUndefined, extensions=["jinja2.ext.do"])
    env.globals.update(
        ref=lambda name: name,
        var=lambda name, default=None: variables.get(name, default),
        target=SimpleNamespace(type="duckdb"),
        run_started_at=datetime(2026, 10, 3, tzinfo=timezone.utc),
        dbt=SimpleNamespace(
            datediff=lambda start, end, unit: f"date_diff('{unit}', {start}, {end})"
        ),
    )
    macros = "\n".join(
        Path(p).read_text()
        for p in (
            "dbt/macros/safe_divide.sql",
            "dbt/macros/date_compat.sql",
            "dbt/macros/generate_surrogate_key.sql",
        )
    )
    return env.from_string(macros + Path(path).read_text()).render()


def test_full_year_growth_excludes_partial_boundaries_and_nonconsecutive_years():
    """Sparse observations do not redefine the declared publisher period."""
    with duckdb.connect() as con:
        con.execute("create table dim_state(state_key varchar, state_name varchar)")
        con.execute("insert into dim_state values ('01', 'Alabama')")
        con.execute("""create table fact_sba_loans as select * from (values
            ('01',1990,100,date '1990-10-01'), ('01',1991,200,date '1991-06-01'),
            ('01',2023,1000,date '2023-06-01'), ('01',2025,1500,date '2025-06-01'),
            ('01',2026,100,date '2026-03-01')) as t(project_state_key, approval_year, gross_approval_amount, approval_date)""")
        sql = render_model("dbt/models/marts/lending/mart_lending_annual_state.sql")
        rows = con.execute(sql).df().set_index("approval_year")
        assert not rows.loc[1990, "is_full_calendar_year"]
        assert rows.loc[
            2023, "is_full_calendar_year"
        ]  # one observed month is not a completeness test
        assert not rows.loc[2025, "is_comparable_yoy"]  # 2024 absent
        assert not rows.loc[2026, "is_full_calendar_year"]
        assert rows["approved_loan_amount_yoy_growth_pct"].isna().all()
        con.execute(
            "insert into fact_sba_loans values ('01',2024,1200,date '2024-06-01')"
        )
        rows = con.execute(sql).df().set_index("approval_year")
        assert rows.loc[2025, "approved_loan_amount_yoy_growth_pct"] == pytest.approx(
            0.25
        )


def test_laus_publisher_omission_gaps_ytd_and_pp_units():
    """BLS's 11-month exception is visible but does not become a pipeline error."""
    with duckdb.connect() as con:
        con.execute("create table dim_state(state_key varchar, state_name varchar)")
        con.execute(
            "create table fact_laus_state_month(state_key varchar, year integer, observed_month date, unemployment_rate double)"
        )
        for year, rate, months in (
            (2022, 0.04, range(1, 13)),
            (2023, 0.05, range(1, 13)),
            (2024, 0.06, range(1, 12)),
            (2025, 0.07, [m for m in range(1, 13) if m != 10]),
            (2026, 0.08, range(1, 5)),
        ):
            con.executemany(
                "insert into fact_laus_state_month values ('01', ?, ?, ?)",
                [(year, f"{year}-{month:02}-01", rate) for month in months],
            )
        con.execute(
            "insert into fact_laus_state_month values ('01',2025,date '2025-10-01',null)"
        )
        rows = (
            con.execute(
                render_model("dbt/models/marts/context/mart_laus_annual_state.sql")
            )
            .df()
            .set_index("year")
        )
        assert rows.loc[2023, "unemployment_rate_yoy_change_pp"] == pytest.approx(1)
        assert rows.loc[2024, "missing_month_count"] == 1
        assert rows.loc[2025, "expected_month_count"] == 11
        assert rows.loc[2025, "publisher_omitted_month_count"] == 1
        assert rows.loc[2025, "missing_month_count"] == 0
        assert rows.loc[2025, "annual_coverage_status"] == "publisher_omission"
        assert not rows.loc[2025, "is_comparable_annual"]
        assert rows.loc[2026, "is_year_to_date"]
        assert rows.loc[2026, "annual_coverage_status"] == "year_to_date"
        assert rows.loc[2026, "missing_month_count"] == 0
        assert rows.loc[2026, "expected_month_count"] == 4
        assert rows.loc[2024:2026, "unemployment_rate_yoy_change_pp"].isna().all()


def test_monthly_laus_change_matches_calendar_month_after_a_gap():
    """A missing October cannot shift lag(12) onto a different calendar month."""
    with duckdb.connect() as con:
        con.execute("create table dim_state(state_key varchar, state_name varchar)")
        con.execute(
            "create table fact_laus_state_month(state_key varchar, year integer, observed_month date, unemployment_rate double)"
        )
        con.execute(
            "insert into fact_laus_state_month values ('01',2024,date '2024-11-01',.04), ('01',2025,date '2025-11-01',.05), ('01',2025,date '2025-12-01',.08)"
        )
        rows = con.execute(
            render_model("dbt/models/marts/context/mart_laus_monthly_state.sql")
        ).df()
        assert rows.loc[
            rows.observed_year.eq(2025) & rows.observed_month_number.eq(11),
            "unemployment_rate_yoy_change_pp",
        ].iloc[0] == pytest.approx(1)
        assert (
            rows.loc[
                rows.observed_month_number.eq(12), "unemployment_rate_yoy_change_pp"
            ]
            .isna()
            .all()
        )


def test_selected_snapshot_can_be_valid_but_stale():
    """A selected year-2000 manifest is not current merely because it passed."""
    with duckdb.connect() as con:
        con.execute("""create table stg_ingestion_manifest as select 'sba' as source_system,
            '7a_504_foia' as dataset_name, 'test' as resource_name,
            '2000-01-01T00:00:00Z' as extracted_at_utc, date '2000-01-01' as ingestion_date,
            10 as row_count, true as is_latest_successful_snapshot, 'run' as pipeline_run_id""")
        con.execute(
            "create table fact_sba_loans as select date '1999-12-31' as approval_date"
        )
        con.execute(
            "create table fact_bds_state_year as select 2023 as year, date '2023-03-12' as bds_reference_date"
        )
        con.execute(
            "create table fact_laus_state_month as select date '2026-03-01' as observed_month"
        )
        result = (
            con.execute(
                render_model(
                    "dbt/models/marts/pipeline/mart_pipeline_source_freshness.sql"
                )
            )
            .df()
            .iloc[0]
        )
        assert result.snapshot_validity_status == "valid_selected_snapshot"
        assert result.freshness_status == "stale"
        assert result.extract_age_days > result.max_extract_age_days


def test_selected_component_ratios_and_lender_ranking_meaning():
    """Uneven groups distinguish ratios of sums and global from pooled top-five."""
    with duckdb.connect() as con:
        con.execute(
            "create table groups(amount double, records integer, establishments integer)"
        )
        con.execute("insert into groups values (100,1,10),(900,99,100)")
        assert con.execute(
            "select sum(amount)/sum(records), sum(records)*1000.0/sum(establishments) from groups"
        ).fetchone() == pytest.approx((10, 100000 / 110))
        assert con.execute("select avg(amount/records) from groups").fetchone()[
            0
        ] != pytest.approx(10)
        con.execute(
            "create table lenders(state varchar, lender varchar, amount double)"
        )
        # X wins after aggregation across states, despite being sixth in each state.
        con.executemany(
            "insert into lenders values (?, ?, ?)",
            [(state, f"{state}{i}", 100) for state in ["A", "B"] for i in range(5)]
            + [("A", "X", 90), ("B", "X", 90)],
        )
        top = con.execute(
            "select lender, sum(amount) as amount from lenders group by lender order by amount desc, lender limit 5"
        ).fetchall()
        assert top[0] == ("X", 180)
        assert sum(amount for _, amount in top) / 1180 == pytest.approx(580 / 1180)
        assert 1000 / 1180 != pytest.approx(
            580 / 1180
        )  # pooled state-specific top5 is a different statistic


def test_missing_calendar_date_does_not_become_fiscal_year():
    """Execute the real fact projection on a missing-calendar approval record."""
    model_path = "dbt/models/marts/facts/fact_sba_loans.sql"
    source = Path(model_path).read_text()
    loan_projection = source.split("select", 1)[1].split("-- Group SBA", 1)[0]
    columns = [
        line.strip().rstrip(",")
        for line in loan_projection.splitlines()
        if line.strip()
    ]
    values = {
        "loan_record_key": "'missing-calendar'",
        "loan_program": "'7a'",
        "approval_fiscal_year": "2024",
        "approval_date": "cast(null as date)",
        "project_state_fips": "'01'",
    }
    with duckdb.connect() as con:
        projection = ", ".join(
            f"{values.get(col, 'cast(null as varchar)')} as {col}" for col in columns
        )
        con.execute("create table stg_sba_loans as select " + projection)
        con.execute("""create table ref_loan_status_group(loan_status_key varchar, loan_status_group varchar,
            loan_status_group_label varchar, is_credit_loss_status boolean, status_sort_order integer)""")
        row = con.execute(render_model(model_path)).df().iloc[0]
        assert row.approval_fiscal_year == 2024
        assert pd.isna(row.approval_year)


def test_passed_raw_load_cannot_certify_final_pipeline_completion():
    """Raw metadata plus valid/current sources still leave final completion unknown."""
    with duckdb.connect() as con:
        con.execute("""create table stg_pipeline_run_summary as select 'run' as pipeline_run_ids,
            '2026-10-03T00:00:00Z' as loaded_at_utc, 7 as raw_table_count, 'passed' as validation_status""")
        con.execute("""create table mart_pipeline_validation_summary as select 0 as failed_check_count,
            0 as warning_check_count, 10 as passed_check_count, '2026-10-03' as latest_checked_at_utc""")
        con.execute("""create table mart_pipeline_source_freshness as select 'current' as freshness_status,
            '2026-10-03' as freshness_checked_at_utc""")
        row = (
            con.execute(
                render_model("dbt/models/marts/pipeline/mart_pipeline_run_summary.sql")
            )
            .df()
            .iloc[0]
        )
        assert row.validation_status == "passed"
        assert row.raw_load_status == "loaded"
        assert row.latest_run_status == "unknown"
        assert (
            row.final_pipeline_status_evidence
            == "final_summary_not_loaded_in_this_dbt_pass"
        )


def test_known_industry_component_preserves_unclassified_rows_for_coverage():
    """Unknown and source 99 rows remain visible but cannot inflate known-sector share."""
    with duckdb.connect() as con:
        con.execute("""create table fact_sba_loans as select * from (values
            ('01',2023,'72',100),('01',2023,'UNKNOWN',50),('01',2023,'99',40),
            ('02',2023,'72',900)) as t(project_state_key,approval_year,naics_key,gross_approval_amount)""")
        con.execute("create table dim_state(state_key varchar,state_name varchar)")
        con.execute("""create table dim_naics as select * from (values
            ('72','Accommodation/Food',true),('99','Unclassified',false),
            ('UNKNOWN','Unknown',false)) as t(naics_key,naics_sector_name,is_valid_current_code)""")
        con.execute("""create table mart_lending_annual_state as select project_state_key as state_key,
            approval_year,sum(gross_approval_amount) as total_approved_loan_amount
            from fact_sba_loans group by 1,2""")
        con.execute(
            "create table mart_lending_industry_state_period as "
            + render_model(
                "dbt/models/marts/lending/mart_lending_industry_state_period.sql"
            )
        )
        con.execute(
            "create table bi_industry_mix as "
            + render_model("dbt/models/bi/bi_industry_mix.sql")
        )
        known, total, count = con.execute(
            "select sum(total_approved_loan_amount) filter(where is_known_industry), sum(total_approved_loan_amount),sum(loan_count) from bi_industry_mix"
        ).fetchone()
        assert (known, total, count) == (1000, 1090, 4)
        assert (
            con.execute(
                "select count(*) from bi_industry_mix where naics_key='99' and not is_known_industry"
            ).fetchone()[0]
            == 1
        )


def test_intensity_population_excludes_missing_or_zero_establishment_stock():
    """Matched intensity must exclude the numerator whenever its denominator is absent."""
    with duckdb.connect() as con:
        con.execute("create table dim_state(state_key varchar,state_name varchar)")
        con.execute("""create table mart_lending_annual_state as select * from (values
            ('01',2023,100,1,100,true),('02',2023,900,9,100,true),('03',2023,1000,10,100,true))
            as t(state_key,approval_year,total_approved_loan_amount,loan_count,average_loan_size,is_full_calendar_year)""")
        con.execute(
            "alter table mart_lending_annual_state add column approval_amount_coverage_count integer"
        )
        con.execute(
            "update mart_lending_annual_state set approval_amount_coverage_count=loan_count"
        )
        con.execute("""create table mart_laus_annual_state as select state_key,approval_year as year,
            .05 as annual_average_unemployment_rate, cast(null as double) as unemployment_rate_yoy_change_pp,
            12 as observed_month_count,12 as observed_expected_month_count,0 as unexpected_month_count,
            12 as expected_month_count,0 as publisher_omitted_month_count,
            0 as missing_month_count,false as is_year_to_date,true as is_comparable_annual,
            'full_year' as annual_coverage_status from mart_lending_annual_state""")
        con.execute("""create table mart_business_dynamics_annual_state as select state_key,approval_year as year,
            case when state_key='01' then 10 when state_key='03' then 0 end as establishment_count,
            .1 as establishment_entry_rate,.08 as establishment_exit_rate,
            date '2023-03-12' as bds_reference_date from mart_lending_annual_state""")
        con.execute(
            "create table mart_regional_business_health_annual_state as "
            + render_model(
                "dbt/models/marts/context/mart_regional_business_health_annual_state.sql"
            )
        )
        con.execute(
            "create table bi_regional_business_health as "
            + render_model("dbt/models/bi/bi_regional_business_health.sql")
        )
        result = con.execute(
            "select sum(total_approved_loan_amount)/sum(establishment_count),sum(loan_count)*1000.0/sum(establishment_count) from bi_regional_business_health where has_matched_establishment_population"
        ).fetchone()
        assert result == (10, 100)
        assert (
            con.execute(
                "select count(*) from bi_regional_business_health where is_comparable_context"
            ).fetchone()[0]
            == 1
        )


@pytest.mark.parametrize(
    "months,matched,missing,unexpected,status",
    [
        ([1, 2, 3, 4], 4, 0, 0, "year_to_date"),
        ([1, 2, 3, 5], 3, 1, 1, "missing_or_unexpected_months"),
        ([1, 2, 3], 3, 1, 0, "missing_or_unexpected_months"),
        ([1, 2, 3, 4, 5], 4, 0, 1, "missing_or_unexpected_months"),
    ],
)
def test_laus_expected_month_identities_cannot_be_replaced_by_future_months(
    months, matched, missing, unexpected, status
):
    """A May observation cannot satisfy the April coverage obligation."""
    with duckdb.connect() as con:
        con.execute("create table dim_state(state_key varchar,state_name varchar)")
        con.execute(
            "create table fact_laus_state_month(state_key varchar,year integer,observed_month date,unemployment_rate double)"
        )
        con.executemany(
            "insert into fact_laus_state_month values ('01',2026,?,.05)",
            [(f"2026-{month:02}-01",) for month in months],
        )
        row = (
            con.execute(
                render_model("dbt/models/marts/context/mart_laus_annual_state.sql")
            )
            .df()
            .iloc[0]
        )
        assert row.observed_month_count == len(months)
        assert row.expected_month_count == 4
        assert row.observed_expected_month_count == matched
        assert row.missing_month_count == missing
        assert row.unexpected_month_count == unexpected
        assert row.annual_coverage_status == status
        assert not row.is_comparable_annual


def test_laus_publisher_omissions_outside_elapsed_range_do_not_reduce_expectation():
    """An October exception must not subtract a month from January–September YTD."""
    policy = dbt_policy_vars()["reporting_policy"] | {
        "bls_observation_end": "2025-09-30"
    }
    with duckdb.connect() as con:
        con.execute("create table dim_state(state_key varchar,state_name varchar)")
        con.execute(
            "create table fact_laus_state_month(state_key varchar,year integer,observed_month date,unemployment_rate double)"
        )
        con.executemany(
            "insert into fact_laus_state_month values ('01',2025,?,.05)",
            [(f"2025-{month:02}-01",) for month in range(1, 10)],
        )
        row = (
            con.execute(
                render_model(
                    "dbt/models/marts/context/mart_laus_annual_state.sql",
                    {"reporting_policy": policy},
                )
            )
            .df()
            .iloc[0]
        )
        assert row.expected_month_count == 9
        assert row.publisher_omitted_month_count == 0
        assert row.missing_month_count == row.unexpected_month_count == 0
        assert row.annual_coverage_status == "year_to_date"


def test_industry_coverage_population_includes_unknown_rows_hidden_on_page():
    """Known-only display rows still have an all-industry coverage denominator."""
    with duckdb.connect() as con:
        con.execute(
            "create table selected(state_key varchar,year integer,is_known_industry boolean,amount double)"
        )
        con.execute(
            "insert into selected values ('01',2023,true,100),('01',2023,false,50),('02',2023,true,1000),('01',2022,false,2000)"
        )
        # The known-only page displays 100. Clearing its classification predicate,
        # while preserving state/year, restores the all-industry denominator 150.
        known = con.execute(
            "select sum(amount) from selected where state_key='01' and year=2023 and is_known_industry"
        ).fetchone()[0]
        total = con.execute(
            "select sum(amount) from selected where state_key='01' and year=2023"
        ).fetchone()[0]
        assert known / total == pytest.approx(2 / 3)


def test_updated_laus_policy_requires_all_eight_available_2026_months():
    """The refreshed August endpoint changes coverage without making YTD comparable."""
    with duckdb.connect() as con:
        con.execute("create table dim_state(state_key varchar,state_name varchar)")
        con.execute(
            "create table fact_laus_state_month(state_key varchar,year integer,observed_month date,unemployment_rate double)"
        )
        con.executemany(
            "insert into fact_laus_state_month values ('01',2026,?,.05)",
            [(f"2026-{month:02}-01",) for month in range(1, 9)],
        )
        policy = dbt_policy_vars()["reporting_policy"] | {
            "bls_observation_end": "2026-08-31"
        }
        result = (
            con.execute(
                render_model(
                    "dbt/models/marts/context/mart_laus_annual_state.sql",
                    {"reporting_policy": policy},
                )
            )
            .df()
            .iloc[0]
        )
        assert result.expected_month_count == 8
        assert result.observed_expected_month_count == 8
        assert result.missing_month_count == 0
        assert result.annual_coverage_status == "year_to_date"
        assert not result.is_comparable_annual
