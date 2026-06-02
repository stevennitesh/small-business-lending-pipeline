from pathlib import Path

from tests.unit.dbt_schema_test_helpers import dbt_test_names, models_by_name


LENDING_MARTS = {
    "mart_lending_monthly_state": Path(
        "dbt/models/marts/lending/mart_lending_monthly_state.sql"
    ),
    "mart_lending_annual_state": Path(
        "dbt/models/marts/lending/mart_lending_annual_state.sql"
    ),
    "mart_lending_lender_state_period": Path(
        "dbt/models/marts/lending/mart_lending_lender_state_period.sql"
    ),
    "mart_lending_concentration_state_period": Path(
        "dbt/models/marts/lending/mart_lending_concentration_state_period.sql"
    ),
    "mart_lending_industry_state_period": Path(
        "dbt/models/marts/lending/mart_lending_industry_state_period.sql"
    ),
    "mart_lending_program_state_period": Path(
        "dbt/models/marts/lending/mart_lending_program_state_period.sql"
    ),
    "mart_lending_performance_state_period": Path(
        "dbt/models/marts/lending/mart_lending_performance_state_period.sql"
    ),
    "mart_lending_status_mix_state_period": Path(
        "dbt/models/marts/lending/mart_lending_status_mix_state_period.sql"
    ),
    "mart_lending_terms_pricing_state_period": Path(
        "dbt/models/marts/lending/mart_lending_terms_pricing_state_period.sql"
    ),
    "mart_lending_jobs_impact_state_period": Path(
        "dbt/models/marts/lending/mart_lending_jobs_impact_state_period.sql"
    ),
}
LENDING_SCHEMA = Path("dbt/models/marts/lending/schema.yml")


def test_required_lending_marts_exist():
    """Validate that required lending marts exist."""
    missing_paths = [str(path) for path in LENDING_MARTS.values() if not path.is_file()]

    assert missing_paths == []


def test_lending_schema_declares_grains_and_kpi_tests():
    """Validate that lending schema declares grains and kpi tests."""
    models = models_by_name([LENDING_SCHEMA])

    assert set(LENDING_MARTS) <= set(models)

    for model_name, model in models.items():
        assert model["meta"]["grain"]
        assert any(
            "unique_combination_of_columns" in test for test in model["data_tests"]
        )

        columns = {column["name"]: column for column in model["columns"]}
        assert "average_loan_size" in columns
        assert columns["average_loan_size"]["description"]
        if "loan_count" in columns:
            assert "non_negative" in dbt_test_names(columns["loan_count"]["data_tests"])
        if "total_approved_loan_amount" in columns:
            assert "non_negative" in dbt_test_names(
                columns["total_approved_loan_amount"]["data_tests"]
            )

    for model_name in ("mart_lending_monthly_state", "mart_lending_annual_state"):
        columns = {column["name"]: column for column in models[model_name]["columns"]}
        for growth_column in (
            "approved_loan_amount_yoy_growth_pct",
            "loan_count_yoy_growth_pct",
        ):
            assert growth_column in columns
            assert "decimal ratio" in columns[growth_column]["description"]

    share_columns = {
        "mart_lending_lender_state_period": "lender_approved_amount_share",
        "mart_lending_industry_state_period": "industry_approved_amount_share",
        "mart_lending_program_state_period": "program_approved_amount_share",
    }
    for model_name, share_column in share_columns.items():
        columns = {column["name"]: column for column in models[model_name]["columns"]}
        assert "accepted_range" in dbt_test_names(columns[share_column]["data_tests"])

    concentration_columns = {
        column["name"]: column
        for column in models["mart_lending_concentration_state_period"]["columns"]
    }
    for share_column in ("top_1_lender_share", "top_5_lender_share"):
        assert "accepted_range" in dbt_test_names(
            concentration_columns[share_column]["data_tests"]
        )
        assert "approved dollars" in concentration_columns[share_column]["description"]
    for amount_column in ("top_1_approved_loan_amount", "top_5_approved_loan_amount"):
        assert "non_negative" in dbt_test_names(
            concentration_columns[amount_column]["data_tests"]
        )
    assert "non_negative" in dbt_test_names(
        concentration_columns["lender_count"]["data_tests"]
    )
    lender_columns = {
        column["name"]: column
        for column in models["mart_lending_lender_state_period"]["columns"]
    }
    assert (
        "known-lender approved dollars"
        in lender_columns["lender_approved_amount_share"]["description"]
    )

    singular_tests = {path.name for path in Path("dbt/tests").glob("*.sql")}
    assert {
        "assert_mart_lending_annual_state_reconciles.sql",
        "assert_mart_lending_lender_state_period_reconciles.sql",
        "assert_mart_lending_industry_state_period_reconciles.sql",
        "assert_mart_lending_program_state_period_reconciles.sql",
        "assert_mart_lending_performance_reconciles.sql",
        "assert_mart_lending_status_mix_reconciles.sql",
        "assert_mart_lending_terms_pricing_reconciles.sql",
        "assert_mart_lending_jobs_impact_reconciles.sql",
        "assert_bi_lender_mix_excludes_unknown.sql",
    } <= singular_tests


def test_state_lending_marts_exclude_unmapped_project_states():
    """Validate that state lending marts exclude unmapped project states."""
    for model_name in (
        "mart_lending_monthly_state",
        "mart_lending_annual_state",
        "mart_lending_lender_state_period",
        "mart_lending_industry_state_period",
        "mart_lending_program_state_period",
        "mart_lending_performance_state_period",
        "mart_lending_status_mix_state_period",
        "mart_lending_terms_pricing_state_period",
        "mart_lending_jobs_impact_state_period",
    ):
        model_sql = LENDING_MARTS[model_name].read_text(encoding="utf-8")

        assert "project_state_key is not null" in model_sql


def test_annual_lending_marts_reuse_fact_approval_year():
    """Validate that annual lending marts reuse fact approval year."""
    annual_mart_paths = [
        LENDING_MARTS["mart_lending_annual_state"],
        LENDING_MARTS["mart_lending_lender_state_period"],
        LENDING_MARTS["mart_lending_industry_state_period"],
        LENDING_MARTS["mart_lending_program_state_period"],
    ]

    for model_path in annual_mart_paths:
        model_sql = model_path.read_text(encoding="utf-8")

        assert "coalesce(extract(year from" not in model_sql
        assert "approval_year is not null" in model_sql

    reconciliation_sql = Path(
        "dbt/tests/assert_mart_lending_annual_state_reconciles.sql"
    ).read_text(encoding="utf-8")
    assert "coalesce(extract(year from" not in reconciliation_sql
    assert "approval_year is not null" in reconciliation_sql


def test_lender_mart_excludes_unknown_before_share_and_rank():
    """Validate that lender mart excludes unknown before share and rank."""
    lender_sql = LENDING_MARTS["mart_lending_lender_state_period"].read_text(
        encoding="utf-8"
    )
    reconciliation_sql = Path(
        "dbt/tests/assert_mart_lending_lender_state_period_reconciles.sql"
    ).read_text(encoding="utf-8")

    assert "fact.lender_key != 'UNKNOWN'" in lender_sql
    assert "known_lender_approved_loan_amount" in lender_sql
    assert "'state_period.known_lender_approved_loan_amount'" in lender_sql
    assert "annual.total_approved_loan_amount" not in lender_sql
    assert "lender_key != 'UNKNOWN'" in reconciliation_sql
    assert "fact_total_approved_loan_amount" in reconciliation_sql


def test_lender_concentration_exposes_top_1_and_top_5_metrics():
    """Validate that lender concentration exposes top 1 and top 5 metrics."""
    concentration_sql = LENDING_MARTS[
        "mart_lending_concentration_state_period"
    ].read_text(encoding="utf-8")
    concentration_test_sql = Path(
        "dbt/tests/assert_mart_lending_top_lender_share_ordering.sql"
    ).read_text(encoding="utf-8")

    assert "top_1_approved_loan_amount" in concentration_sql
    assert "top_1_lender_share" in concentration_sql
    assert "top_5_approved_loan_amount" in concentration_sql
    assert "top_5_lender_share" in concentration_sql
    assert "lender_rank = 1" in concentration_sql
    assert "lender_rank <= 5" in concentration_sql
    assert "select *" not in concentration_sql
    assert "from {{ ref('mart_lending_lender_state_period') }}" in concentration_sql
    for expected_column in (
        "state_key",
        "approval_year",
        "total_approved_loan_amount",
        "loan_count",
        "lender_rank",
    ):
        assert expected_column in concentration_sql
    assert "top_1_approved_loan_amount > concentration.top_5_approved_loan_amount" in (
        concentration_test_sql
    )


def test_lending_performance_mart_uses_status_group_without_canceled_losses():
    """Validate that lending performance mart uses status group without canceled losses."""
    performance_sql = LENDING_MARTS["mart_lending_performance_state_period"].read_text(
        encoding="utf-8"
    )
    models = models_by_name([LENDING_SCHEMA])
    performance_columns = {
        column["name"]: column
        for column in models["mart_lending_performance_state_period"]["columns"]
    }

    assert "fact.is_credit_loss_status" in performance_sql
    assert "loan_status" not in performance_sql
    assert "canceled" not in performance_sql.lower()
    assert "safe_divide" in performance_sql
    assert "gross_chargeoff_amount" in performance_columns
    assert "charged_off_loan_count" in performance_columns
    assert "accepted_range" in dbt_test_names(
        performance_columns["chargeoff_amount_rate"]["data_tests"]
    )
    assert (
        "decimal ratio" in performance_columns["chargeoff_amount_rate"]["description"]
    )
    assert (
        "explicitly charged-off"
        in performance_columns["charged_off_loan_count"]["description"]
    )


def test_lending_status_mix_mart_reconciles_status_group_shares():
    """Validate that lending status mix mart reconciles status group shares."""
    status_mix_sql = LENDING_MARTS["mart_lending_status_mix_state_period"].read_text(
        encoding="utf-8"
    )
    models = models_by_name([LENDING_SCHEMA])
    status_mix_columns = {
        column["name"]: column
        for column in models["mart_lending_status_mix_state_period"]["columns"]
    }
    reconciliation_sql = Path(
        "dbt/tests/assert_mart_lending_status_mix_reconciles.sql"
    ).read_text(encoding="utf-8")

    assert "loan_status_group" in status_mix_sql
    assert "loan_status_group_label" in status_mix_sql
    assert "loan_status_sort_order" in status_mix_sql
    assert "mart_lending_performance_state_period" in status_mix_sql
    assert "status_group_approved_amount_share" in status_mix_columns
    assert "status_group_loan_count_share" in status_mix_columns
    for share_column in (
        "status_group_approved_amount_share",
        "status_group_loan_count_share",
    ):
        assert "accepted_range" in dbt_test_names(
            status_mix_columns[share_column]["data_tests"]
        )
    assert "approved_amount_share_sum" in reconciliation_sql
    assert "loan_count_share_sum" in reconciliation_sql
    assert "abs(coalesce(status_totals.loan_count_share_sum, 0) - 1)" in (
        reconciliation_sql
    )


def test_lending_terms_pricing_mart_documents_availability_and_program_semantics():
    """Validate that lending terms pricing mart documents availability and program semantics."""
    terms_sql = LENDING_MARTS["mart_lending_terms_pricing_state_period"].read_text(
        encoding="utf-8"
    )
    models = models_by_name([LENDING_SCHEMA])
    terms_columns = {
        column["name"]: column
        for column in models["mart_lending_terms_pricing_state_period"]["columns"]
    }
    reconciliation_sql = Path(
        "dbt/tests/assert_mart_lending_terms_pricing_reconciles.sql"
    ).read_text(encoding="utf-8")

    assert "fact.initial_interest_rate / 100" in terms_sql
    assert "initial_interest_rate_coverage_count" in terms_sql
    assert "fixed_or_variable_interest_indicator" in terms_sql
    assert "fact.loan_program_key = '7a'" in terms_sql
    assert "third_party_dollars" in terms_sql
    assert "seven_a_approved_loan_amount" in terms_columns
    assert "seven_a_sba_guarantee_rate" in terms_columns
    assert (
        "SBA 7(a) approved dollars"
        in terms_columns["seven_a_sba_guarantee_rate"]["description"]
    )
    assert "SBA 504 loans" in terms_columns["third_party_dollars"]["description"]
    assert (
        "decimal ratio" in terms_columns["average_initial_interest_rate"]["description"]
    )
    for rate_column in (
        "term_coverage_rate",
        "initial_interest_rate_coverage_rate",
        "fixed_interest_loan_share",
        "variable_interest_loan_share",
        "seven_a_sba_guarantee_rate",
    ):
        assert "accepted_range" in dbt_test_names(
            terms_columns[rate_column]["data_tests"]
        )
    assert "seven_a_approved_loan_amount" in reconciliation_sql
    assert "third_party_dollars" in reconciliation_sql


def test_lending_jobs_impact_mart_is_descriptive_and_reconciles():
    """Validate that lending jobs impact mart is descriptive and reconciles."""
    jobs_sql = LENDING_MARTS["mart_lending_jobs_impact_state_period"].read_text(
        encoding="utf-8"
    )
    models = models_by_name([LENDING_SCHEMA])
    jobs_columns = {
        column["name"]: column
        for column in models["mart_lending_jobs_impact_state_period"]["columns"]
    }
    reconciliation_sql = Path(
        "dbt/tests/assert_mart_lending_jobs_impact_reconciles.sql"
    ).read_text(encoding="utf-8")

    assert "jobs_supported_coverage_count" in jobs_sql
    assert "jobs_supported_per_1m_approved" in jobs_sql
    assert "approved_loan_dollars_per_job_supported" in jobs_sql
    assert "not causal" in jobs_columns["total_jobs_supported"]["description"]
    assert "not causal" in jobs_columns["jobs_supported_per_loan"]["description"]
    assert "accepted_range" in dbt_test_names(
        jobs_columns["jobs_supported_coverage_rate"]["data_tests"]
    )
    for metric_column in (
        "total_jobs_supported",
        "jobs_supported_per_loan",
        "jobs_supported_per_1m_approved",
        "approved_loan_dollars_per_job_supported",
    ):
        assert "non_negative" in dbt_test_names(
            jobs_columns[metric_column]["data_tests"]
        )
    assert "jobs_supported_coverage_count" in reconciliation_sql
    assert "total_jobs_supported" in reconciliation_sql
