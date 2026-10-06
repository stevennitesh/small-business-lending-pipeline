"""Shared Power BI export table and column contract."""

from __future__ import annotations


# Keep these SBA-specific KPI tables grouped so implementation-required Power BI
# model checks can distinguish the MVP dashboard core from the extra SBA pages.
EXTRA_SBA_KPI_BI_TABLES = (
    "bi_lending_performance",
    "bi_lending_status_mix",
    "bi_lending_terms_pricing",
    "bi_lending_jobs_impact",
)

# Export order is the stable local CSV order used by Power Query and tests.
BI_EXPORT_TABLES = (
    "bi_executive_overview",
    "bi_state_lending_trends",
    "bi_lender_concentration",
    "bi_industry_mix",
    "bi_program_mix",
    "bi_regional_business_health",
    "bi_pipeline_health",
    "bi_source_freshness",
    "bi_lender_mix",
    *EXTRA_SBA_KPI_BI_TABLES,
    "bi_state_filter",
    "bi_year_filter",
    "bi_loan_program_filter",
    "bi_naics_filter",
    "bi_lender_filter",
)

# Required columns are a minimum contract; dbt BI tables may expose additional
# safe display fields, but the Power BI handoff cannot drop these fields.
REQUIRED_EXPORT_COLUMNS = {
    "bi_executive_overview": {
        "state_key",
        "state_name",
        "year",
        "total_approved_loan_amount",
        "loan_count",
        "average_loan_size",
        "annual_average_unemployment_rate",
        "establishment_count",
        "loans_per_1000_establishments",
        "approved_loan_dollars_per_establishment",
        "context_join_status",
    },
    "bi_state_lending_trends": {
        "state_key",
        "state_name",
        "approval_year",
        "total_approved_loan_amount",
        "loan_count",
        "approved_loan_amount_yoy_growth_pct",
    },
    "bi_lender_concentration": {
        "state_key",
        "state_name",
        "approval_year",
        "top_5_lender_share",
        "lender_count",
    },
    "bi_industry_mix": {
        "state_key",
        "state_name",
        "approval_year",
        "naics_key",
        "industry_approved_amount_share",
    },
    "bi_program_mix": {
        "state_key",
        "state_name",
        "approval_year",
        "loan_program_key",
        "program_approved_amount_share",
    },
    "bi_regional_business_health": {
        "state_key",
        "state_name",
        "year",
        "annual_average_unemployment_rate",
        "unemployment_rate_yoy_change_pct",
        "establishment_count",
        "establishment_entry_rate",
        "establishment_exit_rate",
        "loans_per_1000_establishments",
        "approved_loan_dollars_per_establishment",
        "context_join_status",
    },
    "bi_pipeline_health": {
        "latest_run_status",
        "validation_status",
        "freshness_status",
    },
    "bi_lender_mix": {
        "state_key",
        "state_name",
        "approval_year",
        "lender_key",
        "lender_name",
        "total_approved_loan_amount",
        "loan_count",
        "lender_approved_amount_share",
        "lender_rank",
    },
    "bi_lending_performance": {
        "state_key",
        "state_name",
        "approval_year",
        "total_approved_loan_amount",
        "loan_count",
        "average_loan_size",
        "gross_chargeoff_amount",
        "charged_off_loan_count",
        "chargeoff_amount_rate",
        "charged_off_loan_count_rate",
    },
    "bi_lending_status_mix": {
        "state_key",
        "state_name",
        "approval_year",
        "loan_status_group",
        "loan_status_group_label",
        "loan_status_sort_order",
        "total_approved_loan_amount",
        "loan_count",
        "average_loan_size",
        "gross_chargeoff_amount",
        "charged_off_loan_count",
        "status_group_approved_amount_share",
        "status_group_loan_count_share",
    },
    "bi_lending_terms_pricing": {
        "state_key",
        "state_name",
        "approval_year",
        "total_approved_loan_amount",
        "loan_count",
        "average_loan_size",
        "term_coverage_count",
        "term_coverage_rate",
        "average_term_months",
        "initial_interest_rate_coverage_count",
        "initial_interest_rate_coverage_rate",
        "average_initial_interest_rate",
        "interest_type_coverage_count",
        "fixed_interest_loan_count",
        "variable_interest_loan_count",
        "fixed_interest_loan_share",
        "variable_interest_loan_share",
        "seven_a_approved_loan_amount",
        "sba_guaranteed_approval_amount",
        "seven_a_sba_guarantee_rate",
        "third_party_dollars",
        "third_party_to_approved_amount_rate",
    },
    "bi_lending_jobs_impact": {
        "state_key",
        "state_name",
        "approval_year",
        "total_approved_loan_amount",
        "loan_count",
        "average_loan_size",
        "jobs_supported_coverage_count",
        "jobs_supported_coverage_rate",
        "total_jobs_supported",
        "jobs_supported_per_loan",
        "jobs_supported_per_1m_approved",
        "approved_loan_dollars_per_job_supported",
    },
    "bi_state_filter": {
        "state_key",
        "state_fips",
        "state_abbr",
        "state_name",
        "census_region",
        "census_division",
    },
    "bi_year_filter": {
        "year",
        "year_label",
    },
    "bi_loan_program_filter": {
        "loan_program_key",
        "loan_program",
        "loan_program_name",
    },
    "bi_naics_filter": {
        "naics_key",
        "naics_sector_code",
        "naics_sector_name",
        "naics_description",
        "is_valid_current_code",
        "is_unknown",
    },
    "bi_lender_filter": {
        "lender_key",
        "lender_name",
        "is_unknown",
    },
}

# Additive components and coverage required by the semantic measure handoff.
REQUIRED_EXPORT_COLUMNS["bi_executive_overview"].update(
    {"is_full_calendar_year", "calendar_period_status"}
)
REQUIRED_EXPORT_COLUMNS["bi_state_lending_trends"].update(
    {
        "is_comparable_yoy",
        "first_observed_approval_date",
        "last_observed_approval_date",
        "coverage_evidence_as_of",
        "is_full_calendar_year",
        "source_calendar_start",
        "comparable_prior_year_amount",
        "average_loan_size",
        "source_calendar_end",
        "calendar_period_status",
    }
)
REQUIRED_EXPORT_COLUMNS["bi_lender_concentration"].update(
    {"top_5_approved_loan_amount", "total_approved_loan_amount", "loan_count"}
)
REQUIRED_EXPORT_COLUMNS["bi_industry_mix"].update(
    {"naics_sector_name", "total_approved_loan_amount", "loan_count"}
)
REQUIRED_EXPORT_COLUMNS["bi_program_mix"].update(
    {"loan_program_name", "total_approved_loan_amount", "loan_count"}
)
REQUIRED_EXPORT_COLUMNS["bi_regional_business_health"].update(
    {
        "observed_month_count",
        "observed_expected_month_count",
        "unexpected_month_count",
        "is_year_to_date",
        "annual_coverage_status",
        "expected_month_count",
        "is_comparable_annual",
        "is_comparable_context",
        "publisher_omitted_month_count",
        "loan_count",
        "is_full_calendar_year",
        "total_approved_loan_amount",
        "unemployment_rate_yoy_change_pp",
        "missing_month_count",
    }
)
REQUIRED_EXPORT_COLUMNS["bi_pipeline_health"].update(
    {
        "raw_load_status",
        "freshness_checked_at_utc",
        "pipeline_run_ids",
        "final_pipeline_status_evidence",
        "loaded_at_utc",
    }
)
REQUIRED_EXPORT_COLUMNS["bi_lending_terms_pricing"].update(
    {"total_term_months", "total_initial_interest_rate"}
)

REQUIRED_EXPORT_COLUMNS["bi_source_freshness"] = {
    "source_system",
    "source_dataset",
    "source_resource_name",
    "latest_extracted_at_utc",
    "latest_ingestion_date",
    "latest_observation_date",
    "freshness_checked_at_utc",
    "latest_row_count",
    "observed_snapshot_count",
    "is_latest_successful_snapshot",
    "snapshot_validity_status",
    "freshness_status",
    "max_extract_age_days",
    "max_observation_age_days",
    "extract_age_days",
    "observation_age_days",
}

REQUIRED_EXPORT_COLUMNS["bi_industry_mix"].add("is_known_industry")

REQUIRED_EXPORT_COLUMNS["bi_regional_business_health"].add(
    "has_matched_establishment_population"
)

# These fields should stay out of the dashboard surface even if they exist in
# upstream raw, staging, or mart tables.
PROHIBITED_EXPORT_FIELDS = {
    "borrower_name",
    "borrower_city",
    "borrower_zip",
    "raw_file_path",
    "source_loan_id",
    "source_lender_id",
}

# Methodology v3: known-value means, paired 504 financing and source clocks.
for _table in (
    "bi_executive_overview",
    "bi_industry_mix",
    "bi_lender_concentration",
    "bi_lender_mix",
    "bi_lending_jobs_impact",
    "bi_lending_performance",
    "bi_lending_status_mix",
    "bi_lending_terms_pricing",
    "bi_program_mix",
    "bi_regional_business_health",
    "bi_state_lending_trends",
):
    REQUIRED_EXPORT_COLUMNS[_table].add("approval_amount_coverage_count")
REQUIRED_EXPORT_COLUMNS["bi_lending_terms_pricing"].update(
    [
        "known_504_third_party_to_sba_amount_rate",
        "paired_504_approval_amount",
        "paired_504_coverage_count",
        "paired_504_coverage_rate",
        "paired_504_third_party_dollars",
        "program_504_loan_count",
    ]
)
REQUIRED_EXPORT_COLUMNS["bi_regional_business_health"].update(["bds_reference_date"])
REQUIRED_EXPORT_COLUMNS["bi_source_freshness"].update(["observation_date_basis"])
REQUIRED_EXPORT_COLUMNS["bi_loan_program_filter"].update(
    ["approval_amount_basis", "reporting_lender_role"]
)

REQUIRED_EXPORT_COLUMNS["bi_lending_terms_pricing"].update(
    [
        "program_7a_loan_count",
        "paired_7a_coverage_count",
        "paired_7a_guaranteed_amount",
        "paired_7a_approval_amount",
        "paired_7a_coverage_rate",
    ]
)

# Explicit publisher periods and review reasons travel with every source row.
REQUIRED_EXPORT_COLUMNS["bi_source_freshness"].update(
    {
        "freshness_reason",
        "publication_source_url",
        "release_check_age_days",
        "publication_reference_date",
        "next_scheduled_release_date",
        "publication_verified_date",
        "download_status",
        "publication_status",
        "publication_date",
        "max_release_check_age_days",
        "publication_cadence",
    }
)
