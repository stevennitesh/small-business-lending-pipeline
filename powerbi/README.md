# Power BI Model

This folder stores the source-controlled Power BI model contract for `lending_dashboard`.

The target desktop artifact is `powerbi/lending_dashboard.pbix`, but PBIX creation requires Power BI Desktop on Windows. The WSL implementation keeps the reproducible pieces in Git:

- `powerbi/lending_dashboard_model.json` defines local CSV and Snowflake BI sources, dashboard tables, filter tables, one-to-many relationships, allowed measures, and filter coverage.
- `powerbi/power_query/local_csv_queries.pq` provides the local CSV source queries.
- `scripts/validate_powerbi_model.py` validates that the model contract stays aligned with the exported BI tables and does not use raw source data.

## Build In Power BI Desktop

1. Run `make run-local` to refresh local CSV tables under `data/exports/powerbi/*.csv`, or use `make run-cloud` to refresh Snowflake BI-schema tables. Both routes use the same BI table contract from `scripts/export_powerbi_tables.py`.
2. Open Power BI Desktop on Windows.
3. For local CSV mode, paste the queries from `powerbi/power_query/local_csv_queries.pq`. If Power BI Desktop cannot resolve the repo-relative `data/exports/powerbi` path, edit the `ExportRoot` value in the query to the Windows absolute path for this repo's export folder, for example `C:\Users\<you>\code\small-business-lending-pipeline\data\exports\powerbi`.
4. For cloud mode, connect to the matching Snowflake tables in `${SNOWFLAKE_DATABASE}.${SNOWFLAKE_BI_SCHEMA}`.
5. Create dimensions and relationships exactly as listed in `powerbi/lending_dashboard_model.json`.
6. Keep DAX measures limited to display labels, formatting, and dynamic titles. Core KPI values come from the BI tables.
7. Save the report as `powerbi/lending_dashboard.pbix`.

The model should use dbt-produced BI filter tables, including `bi_state_filter`, `bi_year_filter`, `bi_loan_program_filter`, `bi_naics_filter`, and `bi_lender_filter`. Do not connect to raw files or expose borrower-level fields.

Extra SBA KPI pages can use the dbt-produced BI tables `bi_lending_performance`, `bi_lending_status_mix`, `bi_lending_terms_pricing`, and `bi_lending_jobs_impact`. For local mode these are CSV files in `data/exports/powerbi`; for cloud mode they are the same logical table names in `${SNOWFLAKE_DATABASE}.${SNOWFLAKE_BI_SCHEMA}`.
