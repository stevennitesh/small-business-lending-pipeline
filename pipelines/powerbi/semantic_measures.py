"""Small, explicit DAX aggregation patterns for the modeled BI handoff."""

from __future__ import annotations

import re


ADDITIVE_COLUMNS = {
    "total_approved_loan_amount",
    "loan_count",
    "program_7a_loan_count",
    "paired_7a_coverage_count",
    "paired_7a_guaranteed_amount",
    "paired_7a_approval_amount",
    "approval_amount_coverage_count",
    "program_504_loan_count",
    "paired_504_coverage_count",
    "paired_504_third_party_dollars",
    "paired_504_approval_amount",
    "top_5_approved_loan_amount",
    "gross_chargeoff_amount",
    "charged_off_loan_count",
    "establishment_count",
    "term_coverage_count",
    "total_term_months",
    "initial_interest_rate_coverage_count",
    "total_initial_interest_rate",
    "interest_type_coverage_count",
    "fixed_interest_loan_count",
    "variable_interest_loan_count",
    "seven_a_approved_loan_amount",
    "sba_guaranteed_approval_amount",
    "third_party_dollars",
    "jobs_supported_coverage_count",
    "total_jobs_supported",
    "comparable_prior_year_amount",
}
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def aggregation_expression(measure: dict) -> str:
    """Define allowed aggregation, without moving record eligibility into DAX."""
    table = measure["table"]
    operation = measure["aggregation"]
    identifiers = [table]
    identifiers += [
        measure[k]
        for k in (
            "column",
            "numerator",
            "denominator",
            "denominator_table",
            "dimension",
            "key",
            "known_key",
            "known_flag",
            "population_flag",
            "prior",
            "flag",
        )
        if k in measure
    ]
    identifiers += measure.get("category_columns", [])
    if not all(IDENTIFIER.fullmatch(value) for value in identifiers):
        raise ValueError("Invalid semantic aggregation identifier")
    if operation == "single_state_year":
        if table != "bi_regional_business_health" or measure["column"] not in {
            "annual_average_unemployment_rate",
            "unemployment_rate_yoy_change_pp",
            "establishment_entry_rate",
            "establishment_exit_rate",
        }:
            raise ValueError("Unsupported single-state/year context metric")
        return f"IF(HASONEVALUE(bi_state_filter[state_key]) && HASONEVALUE(bi_year_filter[year]), SELECTEDVALUE({table}[{measure['column']}]))"
    if operation == "selected_distinct_count":
        if (
            table != "bi_lender_mix"
            or measure["key"] != "lender_key"
            or measure["dimension"] != "bi_lender_filter"
        ):
            raise ValueError("Unsupported selected reporting-unit count")
        return "CALCULATE(DISTINCTCOUNT(bi_lender_mix[lender_key]), REMOVEFILTERS(bi_lender_filter))"
    for key in ("column", "numerator", "denominator", "prior"):
        if key in measure and measure[key] not in ADDITIVE_COLUMNS:
            raise ValueError("Only additive BI components may be aggregated")
    scale = measure.get("scale", 1)
    if scale not in (1, 1000, 1000000):
        raise ValueError("Unsupported semantic scale")
    if operation == "sum":
        return f"SUM({table}[{measure['column']}])"
    if operation in ("ratio", "cross_ratio", "matched_ratio"):
        denominator_table = measure.get("denominator_table", table)
        numerator = f"SUM({table}[{measure['numerator']}])"
        if scale != 1:
            numerator += f" * {scale}"
        denominator = f"SUM({denominator_table}[{measure['denominator']}])"
        if operation == "matched_ratio":
            if (
                table != "bi_regional_business_health"
                or denominator_table != table
                or measure.get("population_flag")
                != "has_matched_establishment_population"
            ):
                raise ValueError("Unsupported matched establishment population")
            population = f"{table}[{measure['population_flag']}] = TRUE()"
            numerator = f"CALCULATE({numerator}, {population})"
            denominator = f"CALCULATE({denominator}, {population})"
        return f"DIVIDE({numerator}, {denominator})"
    if operation in ("category_share", "coverage"):
        amount = f"SUM({table}[{measure['column']}])"
        dimension = measure["dimension"]
        remove = f"REMOVEFILTERS({dimension})"
        if dimension == table:
            remove = ", ".join(
                f"REMOVEFILTERS({table}[{col}])" for col in measure["category_columns"]
            )
        known = (
            f", {table}[{measure['known_flag']}] = TRUE()"
            if "known_flag" in measure
            else ""
        )
        numerator = f"CALCULATE({amount}{known})" if known else amount
        denominator = f"CALCULATE({amount}, {remove}{known})"
        if operation == "coverage":
            numerator = denominator
            denominator = f"CALCULATE({amount}, {remove}, REMOVEFILTERS({table}[{measure['known_flag']}]))"
        return f"DIVIDE({numerator}, {denominator})"
    if operation == "selected_top5":
        return f"""VAR Lenders =
    CALCULATETABLE(
        ADDCOLUMNS(
            SUMMARIZE({table}, {table}[{measure["key"]}]),
            "__Amount", CALCULATE(SUM({table}[{measure["column"]}]))
        ),
        REMOVEFILTERS({measure["dimension"]})
    )
VAR TopFive = TOPN(5, Lenders, [__Amount], DESC, {table}[{measure["key"]}], ASC)
RETURN DIVIDE(SUMX(TopFive, [__Amount]), SUMX(Lenders, [__Amount]))"""
    if operation == "full_year_growth":
        if table != "bi_state_lending_trends" or measure.get("key") != "state_key":
            raise ValueError("Unsupported annual growth population")
        return f"""VAR SelectedYear = SELECTEDVALUE(bi_year_filter[year])
VAR CurrentStates = VALUES({table}[{measure["key"]}])
VAR PriorStates =
    CALCULATETABLE(
        VALUES({table}[{measure["key"]}]),
        REMOVEFILTERS(bi_year_filter),
        bi_year_filter[year] = SelectedYear - 1
    )
RETURN IF(
    HASONEVALUE(bi_year_filter[year]) &&
    COUNTROWS(EXCEPT(CurrentStates, PriorStates)) = 0 &&
    COUNTROWS(EXCEPT(PriorStates, CurrentStates)) = 0 &&
    COUNTROWS({table}) = CALCULATE(COUNTROWS({table}), {table}[{measure["flag"]}] = TRUE()),
    DIVIDE(SUM({table}[{measure["column"]}]) - SUM({table}[{measure["prior"]}]), SUM({table}[{measure["prior"]}]))
)"""
    raise ValueError(f"Unsupported semantic aggregation: {operation}")


def dax_handoff(model: dict) -> str:
    """Render the versioned contract's exact measures for Desktop copy/paste."""
    return (
        f"// Contract v{model['semantic_version']}. Create each measure in Desktop; one block per measure.\n\n"
        + "\n\n".join(
            f"// Format: {measure.get('format_string', 'General')}\n{measure['name']} =\n{measure['expression']}"
            for measure in model["measures"]
        )
        + "\n"
    )
