# Documentation map

[AGENTS.md](../AGENTS.md) supplies the brief context loaded for repository work.
The [project README](../README.md) is the concise repository introduction; the
[HTML report](https://stevennitesh.github.io/small-business-lending-pipeline/)
is the main reader story. Use the relevant owner
below for deeper work; neither entry point requires loading the entire doc tree.

## Current owners

| Need | Maintained owner | Implementation evidence |
|---|---|---|
| Scope, accepted capabilities, tracker and completion rules | [Project specification](detailed/project_spec.md) | [GitHub issues](https://github.com/stevennitesh/small-business-lending-pipeline/issues) |
| Component ownership and local/cloud boundaries | [Architecture](detailed/architecture.md) | `pipelines/` and `dbt/models/` |
| Source population, access and coverage limits | [Source inventory](detailed/data_source_inventory.md) | `config/`, `pipelines/extract/`, storage/validation code |
| Metric populations, denominator choices, comparability and freshness meaning | [KPI methodology](detailed/kpi_definitions.md) | dbt SQL/schema; `config/reporting_policy.yml` and `config/freshness_rules.yml` |
| Model layers, grains and compatibility | [Data model](detailed/data_model.md) | `dbt/models/`, `dbt/dbt_project.yml`, macros and data tests |
| Field meaning and type boundaries | [Field dictionary](detailed/data_dictionary.md) | dbt schema YAML; `pipelines/powerbi/export_schema.py` |
| Commands, environment, output paths, cost and cleanup | [Runtime guide](detailed/orchestration_runtime.md) | `Makefile`, `scripts/`, flow CLI, `requirements.txt`, `.env.example` |
| Verification scope and evidence limits | [Testing guide](detailed/testing_plan.md) | `tests/`, `dbt/tests/`, CI workflow and Makefile |
| Required report pages and acceptance | [Dashboard specification](detailed/dashboard_spec.md) | Power BI handoff and actual report/screenshots |
| Imports, relationships, semantic measures and manual Desktop work | [Power BI handoff](../powerbi/README.md) | Export schema, model JSON, DAX, Power Query and contract validators |
| Main reader story | [Hosted HTML report](https://stevennitesh.github.io/small-business-lending-pipeline/), [offline copy](../reports/portfolio/index.html) | `scripts/render_portfolio_report.py` and `scripts/portfolio/`; [HTML provenance](../reports/portfolio/provenance.json); CI publishes after checks pass |
| Generated charts and aggregate evidence | [Aggregate results](detailed/analysis_results.md), [aggregate JSON](images/lending_analysis.json), [public verification](images/lending_verification.json) | `scripts/render_analysis_report.py`, checked reporting CSVs; [supporting-evidence guide](detailed/case_study.md) routes existing links to their owners |
| Reader vocabulary, current chart sequence and planned Desktop page narration | [Report reader guide](../powerbi/report_reader_guide.md) | `powerbi/report_language.json`, model display names/descriptions |
| Engineering choices and historical benchmarks | [Design decisions](detailed/design_decisions.md) | Recorded comparisons and rejected trials, with current implementation owners |
| Dated data and check results | [Verification appendix](implementation/lending_verification_history.md) | Public aggregate proof, retained local evidence and linked CI runs |

Keep definitions at these owners and link to them from summaries. Update the
owner and directly affected docs/contracts together; a prose change cannot prove
a pipeline refresh, report correction or cloud deployment. Keep changing counts,
schema fields and command definitions with executable sources, and date recorded
observations at the evidence owner.

## Retained evidence

The [design decisions](detailed/design_decisions.md) preserve the native-load and
materialization benchmarks, the rejected intermediate table and the failed
record-numbering trial. The [verification appendix](implementation/lending_verification_history.md)
records dated data populations, checks and limitations. Neither is a work queue.

Original implementation plans, repeated execution instructions and initial
unchecked checklists were consolidated into these records. Current requirements
remain in the project and dashboard specifications; GitHub issues own unfinished
work. Use maintained owners for commands and behavior, and keep useful negative
results visible when retiring old plans.
