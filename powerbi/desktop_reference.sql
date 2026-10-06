-- Repeatable local references for Desktop review, not a DAX engine.
-- scripts/verify_powerbi_readiness.py creates readiness_eligible (direct fact),
-- readiness_raw (independently parsed selected raw), and typed_bi_* (real CSVs).
-- Run that command from the repository root; results contain aggregates only.

-- reference: saved_population
select count(*) as fact_records,
       count(*) filter(where project_state_key is null) as unmapped_geography_records,
       count(*) filter(where approval_date is null) as unknown_calendar_date_records,
       min(approval_date) as first_approval_date, max(approval_date) as last_approval_date
from fact_sba_loans;

-- reference: raw_amount_status_coverage
select program, count(*) as eligible_records, count(amount) as known_amount_records,
       count(*) filter(where amount is null) as unknown_amount_records,
       count(*) filter(where source_amount < 0) as negative_amount_records_cleaned_to_null,
       count(*) filter(where amount = 0) as known_zero_records,
       count(*) filter(where upper(trim(loanstatus)) in ('CANCLD', 'NOT FUNDED')) as canceled_or_not_funded_records
from readiness_raw where state_key is not null and year is not null group by program order by program;

-- reference: zero_amount_source_population
select count(*) filter(where amount=0) as raw_known_zero_records,
       count(*) filter(where amount=0 and state_key is not null and year is not null) as eligible_known_zero_records,
       count(*) filter(where amount=0 and state_key is null) as raw_zeros_excluded_by_geography
from readiness_raw;

-- reference: growth_2025
with years as (
    select approval_year, sum(gross_approval_amount) as dollars, count(*) as records,
           count(distinct project_state_key) as states
    from readiness_eligible where approval_year in (2024,2025) group by 1
)
select c.dollars as current_dollars, p.dollars as prior_dollars,
       c.records as current_records, c.states as current_states, p.states as prior_states,
       (c.dollars / p.dollars - 1) * 100 as growth_percent
from years c join years p on c.approval_year = 2025 and p.approval_year = 2024;

-- reference: geography_2023
with lending as (
    select project_state_key, sum(gross_approval_amount) as dollars, count(*) as records
    from readiness_eligible where approval_year = 2023 group by 1
), ranked as (
    select state.state_name, lending.dollars, lending.records, bds.establishments,
           lending.records * 1000.0 / nullif(bds.establishments,0) as approvals_per_1000_establishments,
           row_number() over(order by lending.dollars desc, lending.project_state_key) as volume_rank,
           row_number() over(order by lending.records * 1000.0 / nullif(bds.establishments,0) desc,
                             lending.project_state_key) as intensity_rank
    from lending join fact_bds_state_year bds on lending.project_state_key=bds.state_key and bds.year=2023
    join bi_state_filter state on lending.project_state_key=state.state_key
)
select * from ranked where volume_rank <= 3 or intensity_rank <= 3 order by volume_rank;

-- reference: program_mix_through2025
select loan_program_key, sum(gross_approval_amount) as dollars, count(*) as records,
       count(gross_approval_amount) as known_amount_records,
       sum(gross_approval_amount) / sum(sum(gross_approval_amount)) over() as dollar_share
from readiness_eligible where approval_year <= 2025 group by 1 order by 1;

-- reference: unknown_category_coverage
select sum(gross_approval_amount) as all_dollars, count(*) as all_records,
       sum(gross_approval_amount) filter(where naics_key in ('UNKNOWN','99')) as unknown_industry_dollars,
       count(*) filter(where naics_key in ('UNKNOWN','99')) as unknown_industry_records,
       sum(gross_approval_amount) filter(where lender_key='UNKNOWN') as unknown_lender_dollars,
       count(*) filter(where lender_key='UNKNOWN') as unknown_lender_records,
       sum(gross_approval_amount) filter(where naics_key not in ('UNKNOWN','99')) / sum(gross_approval_amount) as industry_dollar_coverage,
       sum(gross_approval_amount) filter(where lender_key!='UNKNOWN') / sum(gross_approval_amount) as lender_dollar_coverage
from readiness_eligible where approval_year <= 2025;

-- reference: known_lender_concentration_full_saved
with names as (
    select lender_key, sum(gross_approval_amount) as dollars
    from readiness_eligible where lender_key != 'UNKNOWN' group by lender_key
), ranked as (
    select *, row_number() over(order by dollars desc nulls last,lender_key) as position from names
)
select sum(dollars) as known_name_dollars,
       sum(dollars) filter(where position<=5) as selected_top5_dollars,
       sum(dollars) filter(where position<=5)/sum(dollars) as selected_top5_share,
       (select sum(top_5_approved_loan_amount) from typed_bi_lender_concentration) as pooled_top5_dollars,
       (select sum(top_5_approved_loan_amount) from typed_bi_lender_concentration)/sum(dollars) as pooled_top5_share
from ranked;

-- reference: financing_full_saved
select sum(paired_504_third_party_dollars) as paired_504_third_party_dollars,
       sum(paired_504_approval_amount) as paired_504_sba_dollars,
       sum(paired_504_coverage_count) as paired_504_records, sum(program_504_loan_count) as all_504_records,
       sum(paired_504_third_party_dollars)/sum(paired_504_approval_amount) as known_504_ratio,
       sum(paired_504_coverage_count)::double/sum(program_504_loan_count) as paired_504_coverage,
       sum(paired_7a_guaranteed_amount)/sum(paired_7a_approval_amount) as known_7a_ratio,
       sum(paired_7a_coverage_count) as paired_7a_records, sum(program_7a_loan_count) as all_7a_records,
       sum(paired_7a_coverage_count)::double/sum(program_7a_loan_count) as paired_7a_coverage
from typed_bi_lending_terms_pricing;

-- reference: period_and_context_guards
select year, calendar_period_status, is_comparable_context, annual_coverage_status,
       observed_month_count, expected_month_count, observed_expected_month_count,
       publisher_omitted_month_count, missing_month_count, unexpected_month_count,
       is_comparable_annual, is_year_to_date, count(*) as states
from typed_bi_regional_business_health
join typed_bi_executive_overview using (state_key,year)
where year in (1990,2023,2025,2026)
group by all order by year;

-- reference: laus_calendar_guards
select year,annual_coverage_status,observed_month_count,expected_month_count,
       observed_expected_month_count,publisher_omitted_month_count,missing_month_count,
       unexpected_month_count,is_comparable_annual,is_year_to_date,
       count(*) as states,count(unemployment_rate_yoy_change_pp) as comparable_yoy_states
from mart_laus_annual_state where year in (2023,2025,2026)
group by all order by year;

-- reference: bds_reference_clock
select min(year) as first_year,max(year) as last_year,min(bds_reference_date) as first_reference,
       max(bds_reference_date) as last_reference,
       count(*) filter(where extract(month from bds_reference_date)!=3 or extract(day from bds_reference_date)!=12) as wrong_reference_records
from fact_bds_state_year;

-- reference: state_year_selections
with scopes(label,states,years) as (values
    ('Alabama 2025',['01'],[2025]),
    ('California + Texas 2025',['06','48'],[2025]),
    ('California + Texas 2024-2025',['06','48'],[2024,2025])
)
select label, sum(gross_approval_amount) as dollars, count(*) as records,
       count(gross_approval_amount) as known_amount_records,
       sum(gross_approval_amount)/count(gross_approval_amount) as average_approval,
       (select sum(total_approved_loan_amount) from typed_bi_executive_overview b
        where list_contains(scopes.states,b.state_key) and list_contains(scopes.years,b.year)) as csv_dollars
from scopes join readiness_eligible f on list_contains(states,project_state_key) and list_contains(years,approval_year)
group by label,scopes.states,scopes.years order by label;

-- reference: category_selection_ca_tx_2025
with population as (
    select * from readiness_eligible where project_state_key in ('06','48') and approval_year=2025
)
select sum(gross_approval_amount) as headline_dollars,
       sum(gross_approval_amount) filter(where loan_program_key='7a') as selected_7a_dollars,
       sum(gross_approval_amount) filter(where loan_program_key='7a')/sum(gross_approval_amount) as selected_7a_share,
       sum(gross_approval_amount) filter(where naics_key='72') as selected_sector72_dollars,
       sum(gross_approval_amount) filter(where naics_key='72')/
           sum(gross_approval_amount) filter(where naics_key not in ('UNKNOWN','99')) as selected_sector72_known_share,
       sum(gross_approval_amount) filter(where naics_key not in ('UNKNOWN','99'))/sum(gross_approval_amount) as industry_coverage_independent_of_sector_filter
from population;

-- reference: sector72_through2025_known_only_page
select sum(gross_approval_amount) filter(where naics_key='72') as selected_sector72_dollars,
       sum(gross_approval_amount) filter(where naics_key not in ('UNKNOWN','99')) as all_known_industry_dollars,
       sum(gross_approval_amount) filter(where naics_key='72')/
           sum(gross_approval_amount) filter(where naics_key not in ('UNKNOWN','99')) as selected_known_share,
       sum(gross_approval_amount) filter(where naics_key not in ('UNKNOWN','99'))/sum(gross_approval_amount) as coverage_after_hiding_unknown_rows
from readiness_eligible where approval_year<=2025;

-- reference: lender_selection_ca_tx_2025
with names as (
    select lender_key,sum(gross_approval_amount) as dollars from readiness_eligible
    where project_state_key in ('06','48') and approval_year=2025 and lender_key!='UNKNOWN' group by 1
), ranked as (
    select *,row_number() over(order by dollars desc nulls last,lender_key) as position from names
)
select max(dollars) as selected_one_lender_dollars,
       sum(dollars) as all_known_name_dollars,
       sum(dollars) filter(where position<=5)/sum(dollars) as top5_share_unchanged_by_lender_filter,
       sum(dollars)/(select sum(gross_approval_amount) from readiness_eligible
         where project_state_key in ('06','48') and approval_year=2025) as coverage_unchanged_by_lender_filter
from ranked;

-- reference: missing_prior_population_blank
with population(state,year,amount) as (values ('01',2024,100.0),('01',2025,110.0),('02',2024,900.0)),
scopes(label,states) as (values ('Alabama',['01']),('Alabama + Alaska',['01','02'])),
selected as (
    select label,year,sum(amount) as dollars,list_sort(list(state)) as observed_states
    from scopes join population on list_contains(states,state) group by label,year
)
select c.label,case when c.observed_states=p.observed_states then c.dollars/p.dollars-1 end as growth
from selected c join selected p on c.label=p.label and c.year=2025 and p.year=2024 order by c.label;

-- reference: missing_prior_row_blank
with population(state,year,amount) as (values ('01',2024,100.0),('01',2025,110.0),('02',2025,900.0)),
scopes(label,states) as (values ('Alabama',['01']),('Alabama + Alaska',['01','02'])),
selected as (
    select label,year,sum(amount) as dollars,list_sort(list(state)) as observed_states
    from scopes join population on list_contains(states,state) group by label,year
)
select c.label,case when c.observed_states=p.observed_states then c.dollars/p.dollars-1 end as growth
from selected c join selected p on c.label=p.label and c.year=2025 and p.year=2024 order by c.label;

-- reference: all_unknown_amount_blank
with population(amount) as (values (null::decimal(18,2)),(null::decimal(18,2)))
select count(*) as records,count(amount) as known_amount_records,
       sum(amount)/nullif(count(amount),0) as average_approval from population;
