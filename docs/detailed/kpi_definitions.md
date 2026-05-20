# Step 5: KPI Dictionary

## Purpose

This section defines the KPI contract for the Small Business Lending Intelligence Pipeline.

The goal is to make every published metric measurable, traceable, and defensible. Power BI visuals should be built from modeled mart or BI tables using the definitions in this document, not from ad hoc calculations against raw source files.

The KPI dictionary supports the MVP scope defined earlier:

- SBA lending data as the core lending fact source.
- Census Business Dynamics Statistics as annual business-health context.
- BLS LAUS as monthly labor-market context.
- State-level analysis as the MVP geography.
- No predictive machine learning in the MVP.

---

## KPI Design Principles

The project should follow these metric design rules.

1. **Every KPI must have a documented formula.**  
   A metric should not appear in Power BI unless its calculation logic is defined in this document or in a dbt model description.

2. **Every KPI must have an explicit grain.**  
   A metric calculated by state-month is not the same as a metric calculated by state-year. Grain must be documented.

3. **Every KPI must come from modeled tables.**  
   Dashboard metrics should come from dbt mart or BI models, not directly from raw source tables.

4. **Every KPI must be traceable to source data.**  
   Final KPI tables should preserve enough lineage to identify source system, ingestion date, and transformation path.

5. **Context metrics should not be presented as causal explanations.**  
   Census and BLS indicators provide context for lending activity. They do not prove that unemployment or business formation caused lending changes.

6. **No predictive decisioning.**  
   The MVP does not train models, predict loan approvals, score borrowers, forecast defaults, or recommend lending decisions.

7. **Prefer transparent metrics over complex indexes.**  
   A simple metric that users understand is better than an opaque score.

---

## Canonical KPI Categories

| Category | Description | Primary Source |
|---|---|---|
| Lending volume | Amount and count of approved SBA loans | SBA FOIA |
| Lending trend | Period-over-period changes in loan dollars and loan counts | SBA FOIA |
| Lender concentration | Share of lending controlled by top lenders | SBA FOIA |
| Industry mix | Lending distribution by NAICS sector or industry | SBA FOIA |
| Program mix | Lending distribution across SBA 7(a) and 504 programs | SBA FOIA |
| Business dynamics | Establishment, entry, exit, firm, and job dynamics | Census BDS |
| Labor-market context | Unemployment indicators by state and time period | BLS LAUS |
| Regional comparison | Lending normalized by business or labor context | SBA + Census + BLS |
| Pipeline health | Freshness, row counts, validations, and test status | Pipeline metadata |

---

## Canonical Dimensions

The following dimensions should be supported by the MVP mart and BI tables.

| Dimension | Description | MVP Requirement |
|---|---|---|
| `calendar_year` | Calendar year derived from approval date or source period | Required |
| `calendar_quarter` | Calendar quarter derived from approval date | Required for SBA |
| `month_start_date` | First day of calendar month | Required for SBA and BLS monthly marts |
| `state_fips` | Two-digit state FIPS code | Required |
| `state_abbr` | Two-character state abbreviation | Required |
| `state_name` | Full state name | Required |
| `loan_program` | SBA loan program, such as `7a` or `504` | Required |
| `lender_key` | Standardized lender identifier or surrogate key | Required for lender marts |
| `standardized_lender_name` | Cleaned lender name | Required for lender marts |
| `naics_code` | NAICS industry code where available | Required when source supports it |
| `naics_sector_code` | Two-digit NAICS sector | Required for industry marts |
| `naics_sector_name` | NAICS sector label | Required for dashboard display |
| `source_system` | Source system identifier | Required for lineage models |
| `ingestion_date` | Date the source extract was ingested | Required for pipeline health reporting |

---

## Canonical Staged Fields

KPI formulas should reference canonical staged fields rather than raw source column names.

### SBA Lending Fields

| Canonical Field | Description |
|---|---|
| `loan_record_key` | Stable surrogate key for the staged loan record |
| `source_row_hash` | Hash of raw row values for lineage and duplicate checks |
| `loan_program` | Normalized program value: `7a` or `504` |
| `approval_date` | Parsed loan approval date |
| `approval_month` | Month derived from `approval_date` |
| `approval_quarter` | Quarter derived from `approval_date` |
| `approval_year` | Calendar year derived from `approval_date` |
| `borrower_state_fips` | Borrower state FIPS code |
| `borrower_state_abbr` | Borrower state abbreviation |
| `standardized_lender_name` | Cleaned lender name |
| `lender_key` | Surrogate key for lender |
| `naics_code` | Cleaned NAICS code |
| `naics_sector_code` | Two-digit NAICS sector |
| `gross_approval_amount` | Approved loan amount used for volume KPIs |
| `sba_guaranteed_amount` | SBA guaranteed amount, where available and reliable |
| `jobs_supported` | Jobs supported / retained / created field, where available and documented |
| `source_file_key` | Link to source file lineage table |
| `ingested_at_utc` | Ingestion timestamp |

### Census BDS Fields

| Canonical Field | Description |
|---|---|
| `state_fips` | State FIPS code |
| `calendar_year` | BDS reference year |
| `establishment_count` | Number of establishments |
| `establishment_entry_count` | Number of establishment entries |
| `establishment_entry_rate` | Establishment entry rate |
| `establishment_exit_count` | Number of establishment exits |
| `establishment_exit_rate` | Establishment exit rate |
| `firm_count` | Number of firms |
| `job_creation_count` | Number of jobs created |
| `job_destruction_count` | Number of jobs destroyed |
| `source_file_key` | Link to source file lineage table |

### BLS LAUS Fields

| Canonical Field | Description |
|---|---|
| `state_fips` | State FIPS code derived from series mapping |
| `month_start_date` | Month represented by the LAUS observation |
| `calendar_year` | Observation year |
| `month_number` | Observation month number |
| `measure_name` | Labor-market measure name |
| `measure_value` | Numeric measure value |
| `unemployment_rate` | State unemployment rate, when using the unemployment-rate series |
| `series_id` | BLS series identifier |
| `source_file_key` | Link to source file lineage table |

---

# Lending Volume KPIs

## KPI: Total Approved Loan Amount

| Attribute | Definition |
|---|---|
| KPI name | `total_approved_loan_amount` |
| Business definition | Total dollar amount of approved SBA lending for the selected filters |
| Formula | `sum(gross_approval_amount)` |
| Primary source | SBA FOIA |
| Base grain | Loan record |
| Reporting grains | National, state, time period, lender, industry, program |
| Default aggregation | Sum |
| Format | Currency, USD |
| MVP required | Yes |

### SQL Pattern

```sql
sum(gross_approval_amount) as total_approved_loan_amount
```

### Caveats

- This metric measures approved SBA loan dollars, not all small-business lending.
- This metric does not represent outstanding loan balance, repayment status, default risk, or credit quality.
- Monetary values are nominal dollars unless a future inflation-adjusted metric is added.

---

## KPI: Loan Count

| Attribute | Definition |
|---|---|
| KPI name | `loan_count` |
| Business definition | Number of SBA loan records approved for the selected filters |
| Formula | `count(distinct loan_record_key)` |
| Primary source | SBA FOIA |
| Base grain | Loan record |
| Reporting grains | National, state, time period, lender, industry, program |
| Default aggregation | Count distinct |
| Format | Whole number |
| MVP required | Yes |

### SQL Pattern

```sql
count(distinct loan_record_key) as loan_count
```

### Caveats

- The MVP uses the staged loan record as the unit of count.
- If a program-specific natural loan identifier proves reliable after profiling, it can be used as part of the key strategy.
- Duplicate handling must be documented in the staging model.

---

## KPI: Average Loan Size

| Attribute | Definition |
|---|---|
| KPI name | `average_loan_size` |
| Business definition | Average approved SBA loan amount for the selected filters |
| Formula | `total_approved_loan_amount / loan_count` |
| Primary source | SBA FOIA |
| Base grain | Aggregated lending metric |
| Reporting grains | National, state, time period, lender, industry, program |
| Default aggregation | Calculated ratio |
| Format | Currency, USD |
| MVP required | Yes |

### SQL Pattern

```sql
sum(gross_approval_amount) / nullif(count(distinct loan_record_key), 0) as average_loan_size
```

### Caveats

- This is sensitive to large loans.
- Use median loan size as a stretch metric if outliers distort interpretation.
- Do not average pre-aggregated averages across groups.

---

## KPI: Median Loan Size

| Attribute | Definition |
|---|---|
| KPI name | `median_loan_size` |
| Business definition | Median approved SBA loan amount for the selected filters |
| Formula | Median of `gross_approval_amount` |
| Primary source | SBA FOIA |
| Base grain | Loan record |
| Reporting grains | National, state, time period, lender, industry, program |
| Default aggregation | Median / percentile |
| Format | Currency, USD |
| MVP required | Optional |

### SQL Pattern

```sql
median(gross_approval_amount) as median_loan_size
```

or warehouse-specific equivalent:

```sql
percentile_cont(0.5) within group (order by gross_approval_amount) as median_loan_size
```

### Caveats

- Implementation may differ between DuckDB and Snowflake.
- Include only if the SQL implementation is stable across the local and final warehouse workflows.

---

## KPI: SBA Guaranteed Amount

| Attribute | Definition |
|---|---|
| KPI name | `sba_guaranteed_amount` |
| Business definition | Dollar amount guaranteed by SBA, where available in the source data |
| Formula | `sum(sba_guaranteed_amount)` |
| Primary source | SBA FOIA |
| Base grain | Loan record |
| Reporting grains | National, state, time period, lender, industry, program |
| Default aggregation | Sum |
| Format | Currency, USD |
| MVP required | Conditional |

### SQL Pattern

```sql
sum(sba_guaranteed_amount) as sba_guaranteed_amount
```

### Caveats

- Include only after confirming field availability and consistency across 7(a) and 504 files.
- If the field is not consistently available, exclude from the MVP dashboard and document as future enhancement.

---

## KPI: SBA Guarantee Share

| Attribute | Definition |
|---|---|
| KPI name | `sba_guarantee_share` |
| Business definition | Share of approved loan dollars represented by SBA guaranteed dollars |
| Formula | `sba_guaranteed_amount / total_approved_loan_amount` |
| Primary source | SBA FOIA |
| Base grain | Aggregated lending metric |
| Reporting grains | National, state, time period, lender, industry, program |
| Default aggregation | Calculated ratio |
| Format | Percentage |
| MVP required | Conditional |

### SQL Pattern

```sql
sum(sba_guaranteed_amount) / nullif(sum(gross_approval_amount), 0) as sba_guarantee_share
```

### Caveats

- Only publish if `sba_guaranteed_amount` is reliable after profiling.
- Do not interpret this as risk exposure without additional program-specific context.

---

# Existing SBA Extra KPI Set

These KPIs use fields already present in the SBA 7(a) and 504 FOIA extracts.
They do not require new public sources, and they should not be described as
approval-rate, denial-rate, application-volume, borrower-risk, or unmet-demand
metrics.

| KPI | Formula | Grain | BI table | Caveat |
|---|---|---|---|---|
| `gross_chargeoff_amount` | `sum(gross_chargeoff_amount)` | State-year | `bi_lending_performance` | Source-reported charge-off dollars for approved loans; not a full loss forecast. |
| `chargeoff_amount_rate` | `gross_chargeoff_amount / total_approved_loan_amount` | State-year | `bi_lending_performance` | Decimal ratio; denominator is approved dollars, not outstanding balance. |
| `charged_off_loan_count_rate` | `charged_off_loan_count / loan_count` | State-year | `bi_lending_performance` | Uses explicit charged-off status grouping; canceled/not-funded loans are not credit losses. |
| `status_group_approved_amount_share` | Status-group approved dollars / state-year approved dollars | State-year-status | `bi_lending_status_mix` | Status groups are descriptive and keep unmapped/unknown values visible. |
| `average_term_months` | `avg(term_months)` | State-year | `bi_lending_terms_pricing` | Computed only where source term is reported. |
| `average_initial_interest_rate` | `avg(initial_interest_rate / 100)` | State-year | `bi_lending_terms_pricing` | Decimal ratio; primarily available for 7(a), so pair with coverage. |
| `initial_interest_rate_coverage_rate` | Loans with initial rate / loan count | State-year | `bi_lending_terms_pricing` | Shows how complete the interest-rate field is before interpreting averages. |
| `fixed_interest_loan_share` | Fixed-rate loans / loans with reported rate type | State-year | `bi_lending_terms_pricing` | Share among loans with fixed/variable type reported. |
| `seven_a_sba_guarantee_rate` | SBA-guaranteed dollars / 7(a) approved dollars | State-year | `bi_lending_terms_pricing` | 7(a)-specific guarantee metric; keep distinct from 504 financing. |
| `third_party_dollars` | `sum(third_party_dollars)` | State-year | `bi_lending_terms_pricing` | 504 third-party financing, not SBA guarantee dollars. |
| `total_jobs_supported` | `sum(jobs_supported)` | State-year | `bi_lending_jobs_impact` | Source-reported and descriptive; not a causal jobs-created claim. |
| `jobs_supported_per_loan` | `total_jobs_supported / loan_count` | State-year | `bi_lending_jobs_impact` | Descriptive efficiency metric. |
| `jobs_supported_per_1m_approved` | `total_jobs_supported / (approved dollars / 1,000,000)` | State-year | `bi_lending_jobs_impact` | Descriptive and sensitive to nominal approved dollars. |
| `approved_loan_dollars_per_job_supported` | Approved dollars / jobs supported | State-year | `bi_lending_jobs_impact` | Null when jobs-supported denominator is zero. |

All rates and shares are modeled as decimal values. Power BI owns percentage
formatting, display labels, slicers, relationships, and report layout.

---

# Lending Trend KPIs

## KPI: Approved Loan Amount Year-over-Year Growth

| Attribute | Definition |
|---|---|
| KPI name | `approved_loan_amount_yoy_growth_pct` |
| Business definition | Percent change in approved loan dollars compared with the same period in the prior year |
| Formula | `(current_period_amount - prior_year_period_amount) / prior_year_period_amount` |
| Primary source | SBA FOIA |
| Base grain | Aggregated time series |
| Reporting grains | State-month, state-quarter, state-year, national-period |
| Default aggregation | Calculated ratio |
| Format | Percentage |
| MVP required | Yes |

### SQL Pattern

```sql
(
  total_approved_loan_amount
  - lag(total_approved_loan_amount, 12) over (
      partition by state_fips
      order by month_start_date
    )
)
/
nullif(
  lag(total_approved_loan_amount, 12) over (
    partition by state_fips
    order by month_start_date
  ),
  0
) as approved_loan_amount_yoy_growth_pct
```

For annual marts:

```sql
(
  total_approved_loan_amount
  - lag(total_approved_loan_amount) over (
      partition by state_fips
      order by calendar_year
    )
)
/
nullif(
  lag(total_approved_loan_amount) over (
    partition by state_fips
    order by calendar_year
  ),
  0
) as approved_loan_amount_yoy_growth_pct
```

### Caveats

- Monthly year-over-year logic requires complete month coverage.
- If prior-year denominator is zero or null, return null.
- Interpret carefully during partial-year periods.

---

## KPI: Loan Count Year-over-Year Growth

| Attribute | Definition |
|---|---|
| KPI name | `loan_count_yoy_growth_pct` |
| Business definition | Percent change in loan count compared with the same period in the prior year |
| Formula | `(current_period_loan_count - prior_year_period_loan_count) / prior_year_period_loan_count` |
| Primary source | SBA FOIA |
| Base grain | Aggregated time series |
| Reporting grains | State-month, state-quarter, state-year, national-period |
| Default aggregation | Calculated ratio |
| Format | Percentage |
| MVP required | Yes |

### SQL Pattern

```sql
(
  loan_count
  - lag(loan_count, 12) over (
      partition by state_fips
      order by month_start_date
    )
)
/
nullif(
  lag(loan_count, 12) over (
    partition by state_fips
    order by month_start_date
  ),
  0
) as loan_count_yoy_growth_pct
```

### Caveats

- Do not average growth rates across states.
- Compute growth at the target reporting grain.

---

## KPI: Approved Loan Amount Quarter-over-Quarter Growth

| Attribute | Definition |
|---|---|
| KPI name | `approved_loan_amount_qoq_growth_pct` |
| Business definition | Percent change in approved loan dollars compared with the prior quarter |
| Formula | `(current_quarter_amount - prior_quarter_amount) / prior_quarter_amount` |
| Primary source | SBA FOIA |
| Base grain | Aggregated quarterly time series |
| Reporting grains | State-quarter, national-quarter |
| Default aggregation | Calculated ratio |
| Format | Percentage |
| MVP required | Optional |

### SQL Pattern

```sql
(
  total_approved_loan_amount
  - lag(total_approved_loan_amount) over (
      partition by state_fips
      order by calendar_year, calendar_quarter
    )
)
/
nullif(
  lag(total_approved_loan_amount) over (
    partition by state_fips
    order by calendar_year, calendar_quarter
  ),
  0
) as approved_loan_amount_qoq_growth_pct
```

### Caveats

- Quarter-over-quarter metrics can be volatile.
- Use alongside year-over-year metrics for cleaner interpretation.

---

# Lender KPIs

## KPI: Lender Approved Loan Amount

| Attribute | Definition |
|---|---|
| KPI name | `lender_approved_loan_amount` |
| Business definition | Total approved SBA loan dollars attributed to a lender |
| Formula | `sum(gross_approval_amount)` grouped by lender |
| Primary source | SBA FOIA |
| Base grain | Loan record |
| Reporting grains | Lender, lender-state, lender-year, lender-program |
| Default aggregation | Sum |
| Format | Currency, USD |
| MVP required | Yes |

### SQL Pattern

```sql
sum(gross_approval_amount) as lender_approved_loan_amount
```

### Caveats

- Lender names may vary across records.
- MVP standardization should include trimming, casing, punctuation cleanup, and null handling.
- Deep lender entity resolution is a stretch goal.

---

## KPI: Lender Loan Count

| Attribute | Definition |
|---|---|
| KPI name | `lender_loan_count` |
| Business definition | Number of SBA loan records attributed to a lender |
| Formula | `count(distinct loan_record_key)` grouped by lender |
| Primary source | SBA FOIA |
| Base grain | Loan record |
| Reporting grains | Lender, lender-state, lender-year, lender-program |
| Default aggregation | Count distinct |
| Format | Whole number |
| MVP required | Yes |

### SQL Pattern

```sql
count(distinct loan_record_key) as lender_loan_count
```

---

## KPI: Lender Share of Approved Loan Amount

| Attribute | Definition |
|---|---|
| KPI name | `lender_approved_amount_share` |
| Business definition | Lender's share of total approved loan dollars within a selected market |
| Formula | `lender_approved_loan_amount / total_market_approved_loan_amount` |
| Primary source | SBA FOIA |
| Base grain | Aggregated lender market |
| Reporting grains | Lender-state-year, lender-state-month, lender-national-year |
| Default aggregation | Calculated ratio |
| Format | Percentage |
| MVP required | Yes |

### SQL Pattern

```sql
lender_approved_loan_amount
/
nullif(sum(lender_approved_loan_amount) over (
  partition by state_fips, calendar_year
), 0) as lender_approved_amount_share
```

### Caveats

- The denominator must match the selected market grain.
- A lender's national share and state-level share are different metrics.

---

## KPI: Top 5 Lender Share

| Attribute | Definition |
|---|---|
| KPI name | `top_5_lender_share` |
| Business definition | Share of approved loan dollars from the five largest lenders in a selected market |
| Formula | `sum(approved loan amount for top 5 lenders) / total approved loan amount` |
| Primary source | SBA FOIA |
| Base grain | Aggregated lender market |
| Reporting grains | State-year, state-quarter, national-year |
| Default aggregation | Calculated ratio |
| Format | Percentage |
| MVP required | Yes |

### SQL Pattern

```sql
sum(case when lender_rank_by_amount <= 5 then lender_approved_loan_amount else 0 end)
/
nullif(sum(lender_approved_loan_amount), 0) as top_5_lender_share
```

### Caveats

- Top lenders should be ranked within the selected market and period.
- This is a concentration indicator, not a quality indicator.

---

## KPI: Lender HHI

| Attribute | Definition |
|---|---|
| KPI name | `lender_hhi` |
| Business definition | Herfindahl-Hirschman Index based on lender approved loan dollar shares |
| Formula | `sum(power(lender_market_share * 100, 2))` |
| Primary source | SBA FOIA |
| Base grain | Aggregated lender market |
| Reporting grains | State-year, state-quarter, national-year |
| Default aggregation | Calculated index |
| Format | Number, 0 to 10,000 |
| MVP required | Optional |

### SQL Pattern

```sql
sum(power(lender_approved_amount_share * 100, 2)) as lender_hhi
```

### Caveats

- HHI is useful for comparing concentration across markets.
- Do not imply regulatory conclusions from this metric.
- Top 5 lender share is easier for non-technical dashboard users; HHI can be included as a secondary metric.

---

# Industry KPIs

## KPI: Industry Approved Loan Amount

| Attribute | Definition |
|---|---|
| KPI name | `industry_approved_loan_amount` |
| Business definition | Approved SBA loan dollars by NAICS sector or industry |
| Formula | `sum(gross_approval_amount)` grouped by NAICS |
| Primary source | SBA FOIA |
| Base grain | Loan record |
| Reporting grains | NAICS sector, NAICS-state, NAICS-year, NAICS-program |
| Default aggregation | Sum |
| Format | Currency, USD |
| MVP required | Yes |

### SQL Pattern

```sql
sum(gross_approval_amount) as industry_approved_loan_amount
```

### Caveats

- MVP dashboard should use NAICS sector-level grouping first.
- Detailed NAICS codes may be sparse or inconsistent.
- Missing or invalid NAICS codes should be assigned to an `Unknown / Unclassified` group.

---

## KPI: Industry Loan Count

| Attribute | Definition |
|---|---|
| KPI name | `industry_loan_count` |
| Business definition | Number of SBA loan records by NAICS sector or industry |
| Formula | `count(distinct loan_record_key)` grouped by NAICS |
| Primary source | SBA FOIA |
| Base grain | Loan record |
| Reporting grains | NAICS sector, NAICS-state, NAICS-year, NAICS-program |
| Default aggregation | Count distinct |
| Format | Whole number |
| MVP required | Yes |

### SQL Pattern

```sql
count(distinct loan_record_key) as industry_loan_count
```

---

## KPI: Industry Share of Approved Loan Amount

| Attribute | Definition |
|---|---|
| KPI name | `industry_approved_amount_share` |
| Business definition | Industry's share of total approved SBA loan dollars within a selected market |
| Formula | `industry_approved_loan_amount / total_market_approved_loan_amount` |
| Primary source | SBA FOIA |
| Base grain | Aggregated industry market |
| Reporting grains | NAICS sector-state-year, NAICS sector-national-year |
| Default aggregation | Calculated ratio |
| Format | Percentage |
| MVP required | Yes |

### SQL Pattern

```sql
industry_approved_loan_amount
/
nullif(sum(industry_approved_loan_amount) over (
  partition by state_fips, calendar_year
), 0) as industry_approved_amount_share
```

### Caveats

- The denominator must match the reporting grain.
- A sector's state-level share and national share are different metrics.

---

## KPI: Average Loan Size by Industry

| Attribute | Definition |
|---|---|
| KPI name | `industry_average_loan_size` |
| Business definition | Average approved SBA loan size by NAICS sector or industry |
| Formula | `industry_approved_loan_amount / industry_loan_count` |
| Primary source | SBA FOIA |
| Base grain | Aggregated industry metric |
| Reporting grains | NAICS sector, NAICS-state, NAICS-year, NAICS-program |
| Default aggregation | Calculated ratio |
| Format | Currency, USD |
| MVP required | Yes |

### SQL Pattern

```sql
sum(gross_approval_amount) / nullif(count(distinct loan_record_key), 0) as industry_average_loan_size
```

---

# Program Mix KPIs

## KPI: Program Approved Loan Amount

| Attribute | Definition |
|---|---|
| KPI name | `program_approved_loan_amount` |
| Business definition | Approved SBA loan dollars by loan program |
| Formula | `sum(gross_approval_amount)` grouped by `loan_program` |
| Primary source | SBA FOIA |
| Base grain | Loan record |
| Reporting grains | Program, program-state, program-year |
| Default aggregation | Sum |
| Format | Currency, USD |
| MVP required | Yes |

### SQL Pattern

```sql
sum(gross_approval_amount) as program_approved_loan_amount
```

---

## KPI: Program Share of Approved Loan Amount

| Attribute | Definition |
|---|---|
| KPI name | `program_approved_amount_share` |
| Business definition | Share of approved SBA loan dollars by program |
| Formula | `program_approved_loan_amount / total_approved_loan_amount` |
| Primary source | SBA FOIA |
| Base grain | Aggregated program market |
| Reporting grains | Program-state-year, program-national-year |
| Default aggregation | Calculated ratio |
| Format | Percentage |
| MVP required | Yes |

### SQL Pattern

```sql
program_approved_loan_amount
/
nullif(sum(program_approved_loan_amount) over (
  partition by state_fips, calendar_year
), 0) as program_approved_amount_share
```

### Caveats

- 7(a) and 504 programs serve different financing needs.
- Use program mix to describe composition, not to rank program quality.

---

# Business Dynamics KPIs

## KPI: Establishment Count

| Attribute | Definition |
|---|---|
| KPI name | `establishment_count` |
| Business definition | Number of business establishments in the selected state and year |
| Formula | Source-provided Census BDS establishment count |
| Primary source | Census BDS |
| Base grain | State-year |
| Reporting grains | State-year, national-year |
| Default aggregation | Sum across states |
| Format | Whole number |
| MVP required | Yes |

### SQL Pattern

```sql
sum(establishment_count) as establishment_count
```

### Caveats

- BDS is annual and may lag current lending periods.
- Use for annual context and normalization, not monthly reporting.

---

## KPI: Establishment Entry Count

| Attribute | Definition |
|---|---|
| KPI name | `establishment_entry_count` |
| Business definition | Count of establishment entries in the selected state and year |
| Formula | Source-provided Census BDS establishment entry count |
| Primary source | Census BDS |
| Base grain | State-year |
| Reporting grains | State-year, national-year |
| Default aggregation | Sum across states |
| Format | Whole number |
| MVP required | Yes |

### SQL Pattern

```sql
sum(establishment_entry_count) as establishment_entry_count
```

---

## KPI: Establishment Entry Rate

| Attribute | Definition |
|---|---|
| KPI name | `establishment_entry_rate` |
| Business definition | Rate of establishment entries in the selected state and year |
| Formula | Source-provided Census BDS rate, or documented recomputation if needed |
| Primary source | Census BDS |
| Base grain | State-year |
| Reporting grains | State-year |
| Default aggregation | Source rate at grain; weighted average for larger aggregations if denominator is available |
| Format | Percentage |
| MVP required | Yes |

### SQL Pattern

At state-year grain:

```sql
establishment_entry_rate
```

For national or multi-state rollups, prefer source-provided rates or weighted calculation if denominator is available:

```sql
sum(establishment_entry_count) / nullif(sum(establishment_count), 0) as establishment_entry_rate_calculated
```

### Caveats

- Do not average state rates without weighting.
- Confirm source rate definition before recomputing.
- Use BDS rates as business context, not as a direct measure of credit demand.

---

## KPI: Establishment Exit Count

| Attribute | Definition |
|---|---|
| KPI name | `establishment_exit_count` |
| Business definition | Count of establishment exits in the selected state and year |
| Formula | Source-provided Census BDS establishment exit count |
| Primary source | Census BDS |
| Base grain | State-year |
| Reporting grains | State-year, national-year |
| Default aggregation | Sum across states |
| Format | Whole number |
| MVP required | Yes |

### SQL Pattern

```sql
sum(establishment_exit_count) as establishment_exit_count
```

---

## KPI: Establishment Exit Rate

| Attribute | Definition |
|---|---|
| KPI name | `establishment_exit_rate` |
| Business definition | Rate of establishment exits in the selected state and year |
| Formula | Source-provided Census BDS rate, or documented recomputation if needed |
| Primary source | Census BDS |
| Base grain | State-year |
| Reporting grains | State-year |
| Default aggregation | Source rate at grain; weighted average for larger aggregations if denominator is available |
| Format | Percentage |
| MVP required | Yes |

### SQL Pattern

At state-year grain:

```sql
establishment_exit_rate
```

For weighted rollups:

```sql
sum(establishment_exit_count) / nullif(sum(establishment_count), 0) as establishment_exit_rate_calculated
```

### Caveats

- Do not average state rates without weighting.
- Keep entry and exit rates visually separate; netting them can hide churn.

---

## KPI: Net Establishment Entry

| Attribute | Definition |
|---|---|
| KPI name | `net_establishment_entry_count` |
| Business definition | Establishment entries minus establishment exits |
| Formula | `establishment_entry_count - establishment_exit_count` |
| Primary source | Census BDS |
| Base grain | State-year |
| Reporting grains | State-year, national-year |
| Default aggregation | Sum |
| Format | Whole number |
| MVP required | Optional |

### SQL Pattern

```sql
establishment_entry_count - establishment_exit_count as net_establishment_entry_count
```

### Caveats

- Net entry is a simplified measure.
- Present entry and exit separately when possible.

---

## KPI: Job Creation Count

| Attribute | Definition |
|---|---|
| KPI name | `job_creation_count` |
| Business definition | Jobs created from expanding or opening establishments |
| Formula | Source-provided Census BDS job creation count |
| Primary source | Census BDS |
| Base grain | State-year |
| Reporting grains | State-year, national-year |
| Default aggregation | Sum |
| Format | Whole number |
| MVP required | Optional |

### SQL Pattern

```sql
sum(job_creation_count) as job_creation_count
```

---

## KPI: Job Destruction Count

| Attribute | Definition |
|---|---|
| KPI name | `job_destruction_count` |
| Business definition | Jobs lost from contracting or closing establishments |
| Formula | Source-provided Census BDS job destruction count |
| Primary source | Census BDS |
| Base grain | State-year |
| Reporting grains | State-year, national-year |
| Default aggregation | Sum |
| Format | Whole number |
| MVP required | Optional |

### SQL Pattern

```sql
sum(job_destruction_count) as job_destruction_count
```

---

# Labor-Market KPIs

## KPI: Unemployment Rate

| Attribute | Definition |
|---|---|
| KPI name | `unemployment_rate` |
| Business definition | State unemployment rate for the selected month |
| Formula | Source-provided BLS LAUS unemployment rate |
| Primary source | BLS LAUS |
| Base grain | State-month |
| Reporting grains | State-month, state-year |
| Default aggregation | Source value at state-month; average for annual state summary |
| Format | Percentage |
| MVP required | Yes |

### SQL Pattern

At state-month grain:

```sql
unemployment_rate
```

At state-year grain:

```sql
avg(unemployment_rate) as annual_average_unemployment_rate
```

### Caveats

- Use percentage-point changes when comparing unemployment rates, not percent growth unless explicitly required.
- Preserve source footnotes where available.
- BLS revisions can affect historical values.

---

## KPI: Unemployment Rate Year-over-Year Change

| Attribute | Definition |
|---|---|
| KPI name | `unemployment_rate_yoy_change_pp` |
| Business definition | Percentage-point change in unemployment rate compared with the same month in the prior year |
| Formula | `current_unemployment_rate - prior_year_unemployment_rate` |
| Primary source | BLS LAUS |
| Base grain | State-month |
| Reporting grains | State-month |
| Default aggregation | Calculated difference |
| Format | Percentage points |
| MVP required | Yes |

### SQL Pattern

```sql
unemployment_rate
-
lag(unemployment_rate, 12) over (
  partition by state_fips
  order by month_start_date
) as unemployment_rate_yoy_change_pp
```

### Caveats

- This is a percentage-point change, not a percent change.
- Null if prior-year comparison does not exist.

---

## KPI: Annual Average Unemployment Rate

| Attribute | Definition |
|---|---|
| KPI name | `annual_average_unemployment_rate` |
| Business definition | Average monthly unemployment rate across a calendar year |
| Formula | `avg(unemployment_rate)` over months in year |
| Primary source | BLS LAUS |
| Base grain | State-month |
| Reporting grains | State-year |
| Default aggregation | Average |
| Format | Percentage |
| MVP required | Yes |

### SQL Pattern

```sql
avg(unemployment_rate) as annual_average_unemployment_rate
```

### Caveats

- Require enough monthly observations before publishing annual values.
- A validation rule should flag incomplete years.

---

# Regional Comparison KPIs

## KPI: Loans per 1,000 Establishments

| Attribute | Definition |
|---|---|
| KPI name | `loans_per_1000_establishments` |
| Business definition | Number of SBA approved loans per 1,000 establishments |
| Formula | `(loan_count / establishment_count) * 1000` |
| Primary source | SBA FOIA + Census BDS |
| Base grain | State-year |
| Reporting grains | State-year, national-year |
| Default aggregation | Calculated ratio |
| Format | Number |
| MVP required | Yes |

### SQL Pattern

```sql
loan_count / nullif(establishment_count, 0) * 1000 as loans_per_1000_establishments
```

### Caveats

- This metric should be calculated at annual grain because BDS is annual.
- Do not join annual BDS values directly to monthly visuals unless clearly labeled.
- This normalizes lending activity by business base, not by credit demand.

---

## KPI: Approved Loan Dollars per Establishment

| Attribute | Definition |
|---|---|
| KPI name | `approved_loan_dollars_per_establishment` |
| Business definition | Approved SBA loan dollars divided by number of establishments |
| Formula | `total_approved_loan_amount / establishment_count` |
| Primary source | SBA FOIA + Census BDS |
| Base grain | State-year |
| Reporting grains | State-year, national-year |
| Default aggregation | Calculated ratio |
| Format | Currency, USD |
| MVP required | Yes |

### SQL Pattern

```sql
total_approved_loan_amount / nullif(establishment_count, 0) as approved_loan_dollars_per_establishment
```

### Caveats

- This is a normalized lending intensity metric.
- Large loans can materially affect the value.
- Use alongside loan count per establishment.

---

## KPI: Lending-to-Entry Ratio

| Attribute | Definition |
|---|---|
| KPI name | `lending_to_entry_ratio` |
| Business definition | SBA loan count relative to establishment entries |
| Formula | `loan_count / establishment_entry_count` |
| Primary source | SBA FOIA + Census BDS |
| Base grain | State-year |
| Reporting grains | State-year |
| Default aggregation | Calculated ratio |
| Format | Number |
| MVP required | Optional |

### SQL Pattern

```sql
loan_count / nullif(establishment_entry_count, 0) as lending_to_entry_ratio
```

### Caveats

- Establishment entries are not the same as SBA loan applicants.
- Use as directional context only.

---

## KPI: Lending and Unemployment Comparison

| Attribute | Definition |
|---|---|
| KPI name | `lending_unemployment_comparison` |
| Business definition | Combined view of lending activity and unemployment rate by state and time |
| Formula | Dashboard-level comparison of `total_approved_loan_amount`, `loan_count`, and `unemployment_rate` |
| Primary source | SBA FOIA + BLS LAUS |
| Base grain | State-month or state-year |
| Reporting grains | State-month, state-year |
| Default aggregation | Mixed metrics in same modeled table |
| Format | Mixed |
| MVP required | Yes |

### Implementation Pattern

Monthly table:

```sql
select
  lending.state_fips,
  lending.month_start_date,
  lending.total_approved_loan_amount,
  lending.loan_count,
  bls.unemployment_rate,
  bls.unemployment_rate_yoy_change_pp
from mart_lending_monthly_state lending
left join mart_laus_monthly_state bls
  on lending.state_fips = bls.state_fips
 and lending.month_start_date = bls.month_start_date
```

Annual table:

```sql
select
  lending.state_fips,
  lending.calendar_year,
  lending.total_approved_loan_amount,
  lending.loan_count,
  bls.annual_average_unemployment_rate
from mart_lending_annual_state lending
left join mart_laus_annual_state bls
  on lending.state_fips = bls.state_fips
 and lending.calendar_year = bls.calendar_year
```

### Caveats

- This comparison is descriptive, not causal.
- Avoid statements like “unemployment caused lending to decline.”
- Use neutral phrasing such as “lending declined while unemployment increased.”

---

# Optional Rules-Based Scorecard

## KPI: Regional Lending Activity Score

| Attribute | Definition |
|---|---|
| KPI name | `regional_lending_activity_score` |
| Business definition | Transparent rules-based score summarizing lending and business-health indicators |
| Formula | Weighted normalized components |
| Primary source | SBA FOIA + Census BDS + BLS LAUS |
| Base grain | State-year |
| Reporting grains | State-year |
| Default aggregation | Not additive |
| Format | Score, 0 to 100 |
| MVP required | Stretch only |

### Example Formula

```text
regional_lending_activity_score =
    0.30 * normalized_loan_amount_growth
  + 0.25 * normalized_loans_per_1000_establishments
  + 0.20 * normalized_establishment_entry_rate
  - 0.15 * normalized_unemployment_rate
  - 0.10 * normalized_top_5_lender_share
```

### Caveats

- This is not a machine learning model.
- This is not a credit-risk score.
- This is not a borrower, lender, or regional recommendation engine.
- Component weights must be documented.
- The score should be labeled as an exploratory business-health indicator if implemented.
- Keep this out of the MVP unless the core KPI tables and dashboard are complete.

---

# Pipeline Health KPIs

## KPI: Source Row Count

| Attribute | Definition |
|---|---|
| KPI name | `source_row_count` |
| Business definition | Number of records ingested from a source extract |
| Formula | Count of raw rows or records in the ingestion manifest |
| Primary source | Ingestion manifest |
| Base grain | Source file / API extract |
| Reporting grains | Source, dataset, ingestion date |
| Default aggregation | Sum |
| Format | Whole number |
| MVP required | Yes |

### SQL Pattern

```sql
sum(row_count) as source_row_count
```

---

## KPI: Staged Row Count

| Attribute | Definition |
|---|---|
| KPI name | `staged_row_count` |
| Business definition | Number of rows available in a staged model after cleaning and standardization |
| Formula | Count of rows in staged model |
| Primary source | dbt metadata or validation results |
| Base grain | dbt model |
| Reporting grains | Model, pipeline run |
| Default aggregation | Count |
| Format | Whole number |
| MVP required | Yes |

---

## KPI: Rejected Record Count

| Attribute | Definition |
|---|---|
| KPI name | `rejected_record_count` |
| Business definition | Number of records excluded or quarantined because they failed validation rules |
| Formula | Count of rejected records |
| Primary source | Validation output tables |
| Base grain | Validation rule + model + pipeline run |
| Reporting grains | Source, model, rule, pipeline run |
| Default aggregation | Sum |
| Format | Whole number |
| MVP required | Optional |

### Caveats

- If quarantine handling is not implemented in MVP, report validation failures instead.
- Do not silently drop records without documenting the rule.

---

## KPI: Validation Pass Rate

| Attribute | Definition |
|---|---|
| KPI name | `validation_pass_rate` |
| Business definition | Share of validation checks that passed for a pipeline run |
| Formula | `passed_validation_checks / total_validation_checks` |
| Primary source | Python validation results + dbt test results |
| Base grain | Pipeline run |
| Reporting grains | Pipeline run, source, model |
| Default aggregation | Calculated ratio |
| Format | Percentage |
| MVP required | Yes |

### SQL Pattern

```sql
passed_validation_checks / nullif(total_validation_checks, 0) as validation_pass_rate
```

---

## KPI: Source Freshness Status

| Attribute | Definition |
|---|---|
| KPI name | `source_freshness_status` |
| Business definition | Status indicating whether a source extract is within the expected freshness window |
| Formula | Rule-based status from freshness checks |
| Primary source | Ingestion manifest + source-specific freshness rules |
| Base grain | Source dataset |
| Reporting grains | Source, dataset, pipeline run |
| Default aggregation | Latest status |
| Format | Categorical: `pass`, `warning`, `fail` |
| MVP required | Yes |

### Example Rules

| Source | Freshness Rule |
|---|---|
| SBA FOIA | Latest known source update should be within expected quarterly publication window |
| Census BDS | Latest available source year should match the documented available release |
| BLS LAUS | Latest available month should be within expected BLS publication lag |

### Caveats

- Public datasets have publication delays.
- Freshness checks should distinguish between source delay and pipeline failure where possible.

---

## KPI: Latest Successful Pipeline Run

| Attribute | Definition |
|---|---|
| KPI name | `latest_successful_pipeline_run_at_utc` |
| Business definition | Most recent completed pipeline run that passed required validation and dbt tests |
| Formula | `max(run_completed_at_utc)` where status is successful |
| Primary source | Prefect run metadata / pipeline log table |
| Base grain | Pipeline run |
| Reporting grains | Global |
| Default aggregation | Max timestamp |
| Format | Timestamp |
| MVP required | Yes |

---

# Recommended MVP KPI Set

The MVP dashboard should not try to show every metric. Start with a compact, high-signal set.

## Executive Overview KPIs

| KPI | Required |
|---|---:|
| `total_approved_loan_amount` | Yes |
| `loan_count` | Yes |
| `average_loan_size` | Yes |
| `approved_loan_amount_yoy_growth_pct` | Yes |
| `loan_count_yoy_growth_pct` | Yes |
| `top_5_lender_share` | Yes |
| `loans_per_1000_establishments` | Yes |
| `unemployment_rate` | Yes |
| `source_freshness_status` | Yes |

## Lending Detail KPIs

| KPI | Required |
|---|---:|
| `lender_approved_loan_amount` | Yes |
| `lender_loan_count` | Yes |
| `lender_approved_amount_share` | Yes |
| `industry_approved_loan_amount` | Yes |
| `industry_loan_count` | Yes |
| `industry_approved_amount_share` | Yes |
| `program_approved_loan_amount` | Yes |
| `program_approved_amount_share` | Yes |
| `gross_chargeoff_amount` | Optional |
| `chargeoff_amount_rate` | Optional |
| `charged_off_loan_count_rate` | Optional |
| `average_term_months` | Optional |
| `average_initial_interest_rate` | Optional |
| `initial_interest_rate_coverage_rate` | Optional |
| `seven_a_sba_guarantee_rate` | Optional |
| `third_party_dollars` | Optional |
| `total_jobs_supported` | Optional |
| `jobs_supported_per_1m_approved` | Optional |

## Business Context KPIs

| KPI | Required |
|---|---:|
| `establishment_count` | Yes |
| `establishment_entry_count` | Yes |
| `establishment_entry_rate` | Yes |
| `establishment_exit_count` | Yes |
| `establishment_exit_rate` | Yes |
| `annual_average_unemployment_rate` | Yes |
| `unemployment_rate_yoy_change_pp` | Yes |

## Pipeline Health KPIs

| KPI | Required |
|---|---:|
| `source_row_count` | Yes |
| `staged_row_count` | Yes |
| `validation_pass_rate` | Yes |
| `source_freshness_status` | Yes |
| `latest_successful_pipeline_run_at_utc` | Yes |
| `rejected_record_count` | Optional |

---

# KPI-to-Mart Mapping

| KPI | Recommended Mart / BI Model |
|---|---|
| `total_approved_loan_amount` | `mart_lending_monthly_state`, `mart_lending_annual_state` |
| `loan_count` | `mart_lending_monthly_state`, `mart_lending_annual_state` |
| `average_loan_size` | `mart_lending_monthly_state`, `mart_lending_annual_state` |
| `approved_loan_amount_yoy_growth_pct` | `mart_lending_monthly_state`, `mart_lending_annual_state` |
| `loan_count_yoy_growth_pct` | `mart_lending_monthly_state`, `mart_lending_annual_state` |
| `lender_approved_loan_amount` | `mart_lending_lender_state_period` |
| `lender_approved_amount_share` | `mart_lending_lender_state_period` |
| `top_5_lender_share` | `mart_lending_concentration_state_period` |
| `lender_hhi` | `mart_lending_concentration_state_period` |
| `industry_approved_loan_amount` | `mart_lending_industry_state_period` |
| `industry_approved_amount_share` | `mart_lending_industry_state_period` |
| `program_approved_loan_amount` | `mart_lending_program_state_period` |
| `gross_chargeoff_amount` | `mart_lending_performance_state_period`, `bi_lending_performance` |
| `chargeoff_amount_rate` | `mart_lending_performance_state_period`, `bi_lending_performance` |
| `charged_off_loan_count_rate` | `mart_lending_performance_state_period`, `bi_lending_performance` |
| `status_group_approved_amount_share` | `mart_lending_status_mix_state_period`, `bi_lending_status_mix` |
| `average_term_months` | `mart_lending_terms_pricing_state_period`, `bi_lending_terms_pricing` |
| `average_initial_interest_rate` | `mart_lending_terms_pricing_state_period`, `bi_lending_terms_pricing` |
| `initial_interest_rate_coverage_rate` | `mart_lending_terms_pricing_state_period`, `bi_lending_terms_pricing` |
| `seven_a_sba_guarantee_rate` | `mart_lending_terms_pricing_state_period`, `bi_lending_terms_pricing` |
| `third_party_dollars` | `mart_lending_terms_pricing_state_period`, `bi_lending_terms_pricing` |
| `total_jobs_supported` | `mart_lending_jobs_impact_state_period`, `bi_lending_jobs_impact` |
| `jobs_supported_per_1m_approved` | `mart_lending_jobs_impact_state_period`, `bi_lending_jobs_impact` |
| `establishment_count` | `mart_business_dynamics_annual_state` |
| `establishment_entry_rate` | `mart_business_dynamics_annual_state` |
| `establishment_exit_rate` | `mart_business_dynamics_annual_state` |
| `unemployment_rate` | `mart_laus_monthly_state` |
| `annual_average_unemployment_rate` | `mart_laus_annual_state` |
| `loans_per_1000_establishments` | `mart_regional_business_health_annual_state` |
| `approved_loan_dollars_per_establishment` | `mart_regional_business_health_annual_state` |
| `source_row_count` | `mart_pipeline_source_freshness` |
| `validation_pass_rate` | `mart_pipeline_validation_summary` |
| `latest_successful_pipeline_run_at_utc` | `mart_pipeline_run_summary` |

---

# Display and Formatting Standards

| Metric Type | Display Format |
|---|---|
| Dollar amounts | Currency, compact notation where needed, e.g. `$1.2B` |
| Loan counts | Whole number with thousands separator |
| Percent shares | Percentage with one decimal place |
| Growth rates | Percentage with one decimal place |
| Unemployment rates | Percentage with one decimal place |
| Percentage-point changes | `+/- X.X pp` |
| HHI | Whole number, 0 to 10,000 |
| Dates | Month-year for monthly views; year for annual views |
| Freshness status | `pass`, `warning`, `fail` |

---

# Null and Edge-Case Handling

| Scenario | Handling Rule |
|---|---|
| Denominator is zero | Return null, not zero |
| Prior-year value is missing | Return null growth |
| State mapping missing | Exclude from state-level marts and log validation issue |
| NAICS missing or invalid | Assign to `Unknown / Unclassified` |
| Lender name missing | Assign to `Unknown Lender` |
| Loan amount missing | Exclude from amount-based KPIs and log validation issue |
| Loan amount negative | Fail validation unless source documentation explains it |
| BDS annual value unavailable | Keep lending metric, set context metric null |
| BLS month unavailable | Keep lending metric, set labor metric null |
| Current period incomplete | Label as partial period or exclude from headline trend KPIs |

---

# Metric Caveats for Dashboard Notes

The Power BI dashboard should include concise notes or an information page with the following caveats.

1. **SBA lending coverage**  
   Metrics represent SBA 7(a) and 504 lending records available in public FOIA data. They do not represent all small-business lending.

2. **Approval activity, not performance**  
   Approved loan amount measures origination or approval activity. It does not measure repayment, delinquency, default, or loss performance.

   The extra SBA performance tables include source-reported status and
   charge-off fields, but they are still descriptive historical aggregates.
   They are not credit-risk scores, default forecasts, or loss-reserve models.

3. **Nominal dollars**  
   Dollar metrics are nominal unless an inflation-adjusted version is explicitly created.

4. **Mixed source grains**  
   SBA lending can be aggregated monthly or annually. BLS LAUS is monthly. Census BDS is annual. Cross-source KPIs should use compatible grains.

5. **Descriptive analytics only**  
   Comparisons with business formation or unemployment are descriptive. They should not be interpreted as causal analysis.

   Jobs-supported KPIs are also descriptive. They report SBA source fields and
   should not be labeled as causal jobs created by lending.

6. **No machine learning model**  
   The MVP does not train or deploy predictive models.

7. **No application funnel metrics**
   The current sources do not support application volume, approval rate, denial
   rate, or unmet-demand metrics.

7. **Public data limitations**  
   Source data may contain reporting delays, revisions, missing values, or field-level inconsistencies across historical files.

---

# KPI Acceptance Criteria

Step 5 is complete when the project has:

1. A documented KPI dictionary for all MVP metrics.
2. A clear formula for each required KPI.
3. A documented source for each KPI.
4. A documented grain for each KPI.
5. A documented dashboard formatting standard.
6. A documented null and edge-case handling policy.
7. A documented mapping from KPIs to dbt mart models.
8. Clear caveats preventing overinterpretation.
9. Explicit confirmation that predictive machine learning is out of scope.
10. A compact MVP KPI set suitable for Power BI.

---

# Step 5 Summary

The MVP KPI layer focuses on lending volume, lending trends, lender concentration, industry mix, program mix, regional business context, labor-market context, and pipeline health.

The most important business KPIs are total approved loan amount, loan count, average loan size, year-over-year lending growth, top lender share, loans per 1,000 establishments, establishment entry rate, and unemployment rate.

The most important technical KPIs are source row count, validation pass rate, source freshness status, and latest successful pipeline run.

All metrics should be calculated from modeled dbt mart or BI tables, not directly from raw source files.
