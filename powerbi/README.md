# Power BI Model

This folder stores the source-controlled Power BI model contract for `lending_dashboard`.

The target desktop artifact is `powerbi/lending_dashboard.pbix`, but PBIX creation requires Power BI Desktop on Windows. The WSL implementation keeps the reproducible pieces in Git:

- `powerbi/lending_dashboard_model.json` defines sources, tables, dimensions, one-to-many relationships, allowed measures, and filter coverage.
- `powerbi/power_query/local_csv_queries.pq` provides the local CSV source queries.
- `scripts/validate_powerbi_model.py` validates that the model contract stays aligned with the exported BI tables and does not use raw source data.

## Build In Power BI Desktop

1. Run `make run-local` to refresh `data/exports/powerbi/*.csv`, or use `make run-cloud` to refresh Snowflake BI tables.
2. Open Power BI Desktop on Windows.
3. Load the CSV tables listed in `powerbi/lending_dashboard_model.json`, or connect to the matching Snowflake BI tables.
4. Create dimensions and relationships exactly as listed in `powerbi/lending_dashboard_model.json`.
5. Keep DAX measures limited to display labels, formatting, and dynamic titles. Core KPI values come from the BI tables.
6. Save the report as `powerbi/lending_dashboard.pbix`.

The model should use `bi_lender_mix` for lender filters and `bi_state_filter` for state and region filters. Do not connect to raw files or expose borrower-level fields.
