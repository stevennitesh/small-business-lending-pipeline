let
    // Local CSV mode reads the stable latest export folder written by
    // make run-local through pipelines.powerbi.export_contract.
    // In Power BI Desktop, edit ExportRoot to the Windows absolute path for this
    // repository's data/exports/powerbi folder if the relative path is not found.
    ExportRoot = "data/exports/powerbi",

    // Reuse one loader so every BI table has identical CSV parsing behavior:
    // UTF-8 input, comma delimiters, CSV quoting, and promoted scalar headers.
    LoadCsv = (tableName as text) as table =>
        Table.PromoteHeaders(
            Csv.Document(
                File.Contents(ExportRoot & "/" & tableName & ".csv"),
                [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
            ),
            [PromoteAllScalars = true]
        )
in
    // Query names must stay aligned with powerbi/lending_dashboard_model.json
    // and the dbt-produced BI/export contract. Power BI should not load raw files.
    [
        bi_executive_overview = LoadCsv("bi_executive_overview"),
        bi_state_lending_trends = LoadCsv("bi_state_lending_trends"),
        bi_lender_concentration = LoadCsv("bi_lender_concentration"),
        bi_industry_mix = LoadCsv("bi_industry_mix"),
        bi_program_mix = LoadCsv("bi_program_mix"),
        bi_regional_business_health = LoadCsv("bi_regional_business_health"),
        bi_pipeline_health = LoadCsv("bi_pipeline_health"),
        bi_lender_mix = LoadCsv("bi_lender_mix"),
        bi_lending_performance = LoadCsv("bi_lending_performance"),
        bi_lending_status_mix = LoadCsv("bi_lending_status_mix"),
        bi_lending_terms_pricing = LoadCsv("bi_lending_terms_pricing"),
        bi_lending_jobs_impact = LoadCsv("bi_lending_jobs_impact"),
        bi_state_filter = LoadCsv("bi_state_filter"),
        bi_year_filter = LoadCsv("bi_year_filter"),
        bi_loan_program_filter = LoadCsv("bi_loan_program_filter"),
        bi_naics_filter = LoadCsv("bi_naics_filter"),
        bi_lender_filter = LoadCsv("bi_lender_filter")
    ]
