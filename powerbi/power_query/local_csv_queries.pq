let
    ExportRoot = "data/exports/powerbi",
    LoadCsv = (tableName as text) as table =>
        Table.PromoteHeaders(
            Csv.Document(
                File.Contents(ExportRoot & "/" & tableName & ".csv"),
                [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
            ),
            [PromoteAllScalars = true]
        )
in
    [
        bi_executive_overview = LoadCsv("bi_executive_overview"),
        bi_state_lending_trends = LoadCsv("bi_state_lending_trends"),
        bi_lender_concentration = LoadCsv("bi_lender_concentration"),
        bi_industry_mix = LoadCsv("bi_industry_mix"),
        bi_program_mix = LoadCsv("bi_program_mix"),
        bi_regional_business_health = LoadCsv("bi_regional_business_health"),
        bi_pipeline_health = LoadCsv("bi_pipeline_health"),
        bi_lender_mix = LoadCsv("bi_lender_mix"),
        bi_state_filter = LoadCsv("bi_state_filter"),
        bi_year_filter = LoadCsv("bi_year_filter"),
        bi_loan_program_filter = LoadCsv("bi_loan_program_filter"),
        bi_naics_filter = LoadCsv("bi_naics_filter"),
        bi_lender_filter = LoadCsv("bi_lender_filter")
    ]
