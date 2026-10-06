# Current data model

The executable owners are `dbt/models/`, schema YAML, macros and custom tests.
The project has 52 models and four reference seeds. DuckDB uses `main` for modeled
tables and `main_seeds` for seeds; Snowflake uses the configured logical schemas
and optional `DBT_SCHEMA_PREFIX`. This describes implemented routes, not a new
warehouse deployment certification.

| Layer | Models and responsibility |
|---|---|
| Raw | `raw_sba_7a_foia`, `raw_sba_504_foia`, `raw_census_bds_state_year`, `raw_bls_laus_state_month`, `raw_ingestion_manifest`, `raw_validation_result`, `raw_pipeline_run_summary` |
| Staging | Typed source fields joined to selected validated manifests; source-specific SBA models union into `stg_sba_loans`; audit staging exposes load/validation metadata |
| Dimensions | `dim_state`, `dim_date`, `dim_lender`, `dim_naics`, `dim_loan_program`, `dim_source_file`; reference seeds for states, NAICS, programs and status groups |
| Facts | `fact_sba_loans` one approval record; `fact_bds_state_year` state/year; `fact_laus_state_month` state/month |
| Lending marts | Monthly/annual state; state/year/lender, program, industry and concentration; optional performance, status, terms/pricing and jobs components |
| Context marts | LAUS monthly/annual, BDS annual and matched regional state/year; annual coverage flags travel with rates |
| Audit marts | Source-resource validity/age, validation rollups and raw-load summary; final same-pass completion is explicitly unknown |
| BI | 13 analytic tables and five filter tables; explicit projections without borrower identifiers |

The full BI export surface is owned by
[`BI_EXPORT_TABLES`](../../pipelines/powerbi/export_schema.py). `bi_lender_mix`
contains known names; `bi_industry_mix` retains unknown sectors for coverage.
`bi_lender_concentration` remains a state/year statistic; selected overall top-five
ranking uses lender-level dollar components in the semantic layer.

The `bi_*_filter` tables relate to analytical outputs one-to-many, single direction.
State/year filters reach all supported analytic tables. Program, industry and lender
filters reach only their category table. This deliberately avoids false global
filter behavior; see the [contract](../../powerbi/lending_dashboard_model.json).

## Grain and ownership

Calendar dates and fiscal years remain distinct. Lending requires mapped project
states and calendar dates; context joins align state/year labels while retaining
the BDS March 12 reference date and its distinct clock. Published BDS
rates are retained. LAUS exposes observed/expected/publisher-omitted months,
comparability and YTD. Ratios have safe null/zero denominators. Power BI aggregates
additive components using versioned measures; it does not reconstruct raw business
logic. [Metric definitions](kpi_definitions.md) own population and selection rules.

`source_lender_id` correctly names SBA LocationID; artifact/row keys still define
approval identity. Program labels expose amount basis and reporting-name role.
Every lending mean carries a valid-amount count independently of record volume.
Latest snapshot selection ranks passing manifests ahead of failed ones and uses
a deterministic URI tie-break, so a newer failed extract cannot suppress the last
valid snapshot. Invalid negative optional SBA components become null in staging.
Lender amount ranking explicitly puts unknown totals last on both adapters.
504 financing components use paired known records with an explicit coverage count.
Source recency compares saved SBA quarters, Census years and BLS months with
dated verified publications. BI rows expose publication/reference/verification
dates, publisher URL, cadence and any announced next release. Download review and
publication comparison have separate statuses and an assessment reason.
Observation age stays descriptive. A missed verified published period is stale;
expired verification or old downloads require review and remain unknown. The
health rollup counts latest_published as healthy; validity stays independent.

## Refresh and compatibility

Raw artifacts and manifests remain compatible and immutable. Changes add coverage
and component columns; the old BI unemployment decimal-change alias and mixed
third-party ratio remain explicitly deprecated. Semantic contract v3 replaces
the old third-party DAX measure and changes mean denominators. Upstream modeled
`source_loan_id` is renamed to `source_lender_id`; raw artifacts are unchanged.
Rebuild derived staging/facts/marts/BI and refresh CSVs or Snowflake BI
before applying the new Desktop measures. Existing warehouse/exports/PBIX are
saved historical outputs until refreshed; a source-contract change cannot update
a manual report binary automatically. The October 5 source refresh reloaded
validated current downloads and rebuilt active tables/CSVs; the PBIX remains
historical. Optional missing SBA `Subprogram` columns become null on both adapters;
both ISO and earlier SBA date strings are accepted. Literal `UNKNOWN` lender
names become missing, and documented BLS missing-month markers remain null rates. No cloud schema promotion was run: paid Snowflake execution is
deliberately deferred. Keep generated warehouses, CSVs and dbt targets out of Git.
