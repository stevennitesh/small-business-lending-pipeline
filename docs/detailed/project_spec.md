# Small Business Lending Intelligence Pipeline — Project Specification

## Document Purpose

This document consolidates the approved project brief, business problem, analytical questions, and MVP scope for the Small Business Lending Intelligence Pipeline.

## Contents

1. Project Brief
2. Business Problem
3. Analytical Questions and Scope

---

# Small Business Lending Intelligence Pipeline

## Executive Summary

The Small Business Lending Intelligence Pipeline is an end-to-end analytics engineering project that tracks small-business lending activity and local business health across the United States.

The pipeline ingests public lending, business formation, and labor-market data; stores raw source extracts in AWS S3; transforms the data through raw, staging, and mart layers using SQL and dbt; validates data quality with dbt tests and Python checks; orchestrates refreshes with Prefect; and publishes business-facing KPIs in Power BI.

The project is designed to demonstrate practical data engineering and analytics engineering skills: Python ingestion, cloud object storage, SQL modeling, dimensional design, data quality controls, orchestration, warehouse-ready transformations, and dashboard delivery.

## One-Sentence Pitch

Built a production-style SQL/Python analytics pipeline that ingests public SBA, Census, and BLS data into S3, models lending and business-health KPIs with dbt and Snowflake, validates data quality, and publishes a Power BI dashboard for regional small-business lending analysis.

## Project Objective

The objective of this project is to create a reliable, repeatable pipeline for analyzing small-business lending trends by geography, industry, lender, and time period.

The final output will allow users to answer questions such as:

- Where is small-business lending increasing or declining?
- Which states and industries receive the most approved loan volume?
- Which lenders dominate SBA lending activity in specific regions?
- How do lending trends compare with business formation and unemployment trends?
- Which regions show stronger or weaker small-business credit activity?

## Business Context

Small businesses depend on access to credit for hiring, expansion, equipment purchases, working capital, and recovery from economic shocks. Public lending and economic datasets can be combined to monitor where small-business credit activity is strongest, where it may be weakening, and how lending patterns align with broader local economic conditions.

This project treats small-business lending data as a business intelligence use case rather than a static reporting exercise. The goal is not only to visualize loan totals, but to build a governed pipeline that produces trusted, reusable KPI tables.

## Target Audience

This project is intended for both business and technical users.

### Business Users

- Business analytics managers
- Regional strategy analysts
- Finance analysts
- Lending operations stakeholders

### Technical Users

- Data analysts
- Analytics engineers
- Data engineers
- Data governance reviewers

## What This Project Demonstrates

This project demonstrates the ability to design and build a complete analytics workflow using tools commonly used in business analytics, analytics engineering, and data engineering roles.

### Technical Capabilities

- Python-based API and CSV ingestion
- Raw data storage in AWS S3
- Local development with DuckDB
- Warehouse-oriented modeling with Snowflake
- SQL transformations with dbt Core
- Data quality checks with dbt tests and pytest
- Pipeline orchestration with Prefect
- Containerized development with Docker
- KPI dashboarding with Power BI

### Analytics Capabilities

- Business problem framing
- KPI design
- Dimensional modeling
- Time-series analysis
- Geographic analysis
- Lender and industry segmentation
- Data quality documentation
- Stakeholder-facing dashboard design

## Project Deliverables

The finished project will include:

- A documented project specification
- Python ingestion scripts for public data sources
- Raw data landing structure in S3
- Local DuckDB development workflow
- Snowflake-ready warehouse tables
- dbt staging and mart models
- dbt tests and custom Python validation checks
- Prefect orchestration flow
- Power BI dashboard
- README with architecture, setup instructions, and screenshots
- Documentation for KPIs, data sources, assumptions, and limitations

## Success Criteria

The project will be considered successful when it can:

1. Ingest raw public data from multiple sources.
2. Store immutable raw extracts in a structured S3 layout.
3. Transform raw data into clean staging tables.
4. Build business-ready mart tables for lending and regional business-health KPIs.
5. Run automated data quality checks.
6. Refresh end-to-end through an orchestrated pipeline.
7. Support a Power BI dashboard using final modeled tables.
8. Be understood by a recruiter or hiring manager in under five minutes through the README, screenshots, and documentation.

## Recruiter-Facing Summary

This project shows end-to-end ownership of an analytics pipeline: sourcing public data, designing a warehouse model, creating tested transformations, orchestrating refreshes, and delivering business-facing KPIs through a dashboard.

It is intentionally scoped to emphasize practical analytics engineering skills rather than unnecessary infrastructure complexity. AWS usage is focused on S3 as the raw data landing zone, while DuckDB, Snowflake, dbt, Prefect, pytest, Docker, and Power BI are used to build a complete and reproducible analytics workflow.


---

# Step 2: Business Problem

## Business Problem

Small-business lending activity varies significantly across geography, industry, lender, and time period. Business stakeholders need a reliable way to monitor where lending is expanding, where it is weakening, which lenders and industries are driving activity, and how lending patterns compare with broader local economic indicators such as business formation and unemployment.

The problem is not simply that lending data exists in multiple public sources. The problem is that the data is fragmented, published at different grains, and not immediately usable for business decision-making. A stakeholder needs modeled, validated, and dashboard-ready KPI tables that summarize lending activity and regional business conditions in a consistent way.

This project addresses that problem by building an analytics pipeline that converts raw public data into trusted reporting tables and Power BI dashboards for small-business lending intelligence.

## Business Use Case

A business analytics team wants to understand small-business credit activity across the United States. The team needs to identify regions, industries, and lenders with strong or weakening lending activity, then compare those patterns against local business-health indicators.

The output should support recurring analysis such as monthly, quarterly, or annual business reviews. Instead of manually downloading files, cleaning data, and rebuilding reports, users should be able to rely on a repeatable pipeline that refreshes source data, validates quality, rebuilds KPI tables, and updates dashboard-ready outputs.

## Target Users

| User Group | Primary Need | Example Questions |
|---|---|---|
| Business analytics manager | High-level lending and business-health KPIs | Where is SBA lending increasing or declining? |
| Regional strategy analyst | Geographic comparisons across states or regions | Which states show strong lending activity relative to local business formation? |
| Finance analyst | Loan volume, average loan size, and lender concentration metrics | Which lenders account for the largest share of approved lending? |
| Lending operations stakeholder | Trends by lender, industry, and geography | Which industries are receiving more or less lending activity over time? |
| Analytics engineer / data engineer | Reproducible, tested, well-modeled data assets | Are KPI tables refreshed, tested, and documented? |
| Data governance reviewer | Data lineage, validation, and freshness visibility | What source data was used, when was it ingested, and did quality checks pass? |

## Business Decisions Supported

The dashboard and KPI marts are intended to support the following types of business decisions:

1. **Regional prioritization**  
   Identify states or regions with increasing or declining small-business lending activity.

2. **Industry analysis**  
   Understand which industries receive the most approved loan volume and how industry lending patterns change over time.

3. **Lender concentration monitoring**  
   Measure whether lending activity is broadly distributed across lenders or concentrated among a small number of institutions.

4. **Market context analysis**  
   Compare lending trends against business formation and unemployment indicators to understand whether lending activity aligns with broader local economic conditions.

5. **Executive reporting**  
   Provide repeatable KPIs for business reviews, stakeholder presentations, and portfolio-style analysis.

6. **Data quality oversight**  
   Give technical and governance stakeholders visibility into source freshness, row counts, null checks, schema checks, and test results.

## Stakeholder Needs

### Business Stakeholders

Business stakeholders need concise, interpretable metrics that answer practical questions:

- How much SBA lending was approved?
- How many loans were approved?
- Which states, industries, and lenders account for the largest share?
- How are trends changing over time?
- Which regions appear stronger or weaker compared with business-health indicators?

They do not need raw source tables. They need clean, aggregated, business-ready KPIs.

### Technical Stakeholders

Technical stakeholders need confidence that the dashboard is built from reliable data assets. They need:

- documented source ingestion
- raw data retention
- repeatable transformations
- clear model lineage
- automated tests
- freshness checks
- transparent assumptions
- reproducible local and warehouse workflows

### Recruiter / Hiring Manager Audience

Recruiters and hiring managers need to see that the project is more than a dashboard. The project should demonstrate that the builder can:

- define a business problem
- design a data pipeline around that problem
- model data into analytical layers
- validate data before publishing metrics
- document tradeoffs and limitations
- deliver a stakeholder-facing dashboard

## Analytical Framing

This project treats small-business lending as a measurable business activity that can be analyzed across four main dimensions:

| Dimension | Purpose |
|---|---|
| Time | Track lending trends by month, quarter, or year |
| Geography | Compare lending activity across states or regions |
| Industry | Analyze lending by NAICS sector or industry group |
| Lender | Measure lender activity and concentration |

The project also adds economic context using business formation and unemployment indicators. These context datasets do not replace the core lending KPIs. They provide supporting signals to help interpret whether regional lending activity appears aligned with local business conditions.

## Non-ML Scope Decision

This project intentionally does not include predictive machine learning in the MVP.

The goal is to demonstrate analytics engineering: ingestion, storage, modeling, validation, orchestration, and dashboard delivery. The project will not train a model, predict loan approvals, estimate borrower creditworthiness, forecast defaults, or recommend lending decisions.

Any scoring included in the MVP should be transparent and rules-based, such as a simple regional business-health or lending-activity index built from documented KPI components. The score should be used for dashboard segmentation and interpretation only, not for predictive decisioning.

## Business Assumptions

The MVP is based on the following assumptions:

1. Public SBA lending data is sufficient to measure approved small-business lending activity.
2. Census business dynamics data can provide useful context for business formation and establishment trends.
3. BLS labor-market data can provide useful context for local employment conditions.
4. State-level analysis is the appropriate MVP geography because it is easier to model consistently across sources.
5. The project should prioritize trusted KPI tables over exploratory raw-data visualization.
6. The dashboard should be built from modeled mart or BI tables, not directly from raw source files.
7. Data limitations should be documented rather than hidden.

## Out of Scope for the Business Problem

The MVP does not attempt to solve the following problems:

- borrower-level credit risk scoring
- loan default prediction
- loan approval recommendation
- lender compliance review
- real-time lending surveillance
- fraud detection
- causal economic analysis
- paid-data enrichment
- production-grade cloud infrastructure
- machine learning model training

These exclusions keep the project focused on the analytics engineering workflow and avoid unnecessary scope creep.

## Business Success Criteria

The business problem is successfully addressed when users can answer the following questions from modeled tables and dashboard visuals:

1. Which states have the highest and lowest SBA approved lending volume?
2. How has lending activity changed over time?
3. Which industries receive the most SBA lending?
4. Which lenders dominate approved loan volume by geography?
5. How does lending activity compare with business formation indicators?
6. How does lending activity compare with unemployment conditions?
7. Which regions show stronger or weaker small-business lending activity?
8. Is the data fresh, validated, and traceable back to raw source extracts?

## Business Problem Summary

This project solves a reporting and analytics problem: public small-business lending and economic data is available, but it is not immediately structured for recurring business analysis. The pipeline converts fragmented public data into validated, documented, dashboard-ready KPI tables that allow stakeholders to monitor small-business lending trends and regional business-health indicators.


---

# Step 3: Analytical Questions and Scope

## Purpose

This section defines the analytical questions, MVP scope, out-of-scope items, and stretch goals for the Small Business Lending Intelligence Pipeline.

The goal is to keep the project focused on a complete analytics engineering workflow: ingesting public data, storing raw extracts, modeling business-ready KPI tables, validating data quality, orchestrating refreshes, and publishing a Power BI dashboard.

The MVP intentionally excludes predictive machine learning, borrower-level credit scoring, and production-grade cloud infrastructure.

## Core Analytical Questions

The project is designed to answer a focused set of business questions about small-business lending activity and regional business health.

### Lending Activity

1. **Where is SBA lending activity highest and lowest?**
   - Compare approved loan dollars and loan counts by state, region, industry, and time period.

2. **How has small-business lending changed over time?**
   - Track trends in approved loan volume, loan count, and average loan size by month, quarter, or year.

3. **Which industries receive the most SBA lending?**
   - Analyze approved loan activity by NAICS sector or industry group.

4. **Which lenders drive SBA lending activity?**
   - Rank lenders by approved loan amount, loan count, average loan size, and share of total lending.

5. **Is lending activity concentrated among a small number of lenders?**
   - Measure top-lender share and lender concentration by state, region, and time period.

### Regional Business Health

6. **How does lending activity compare with business formation trends?**
   - Compare SBA lending activity with business openings, startups, establishments, or related Census business dynamics indicators.

7. **How does lending activity compare with labor-market conditions?**
   - Compare lending activity with unemployment rates and employment trends from BLS labor-market data.

8. **Which regions show stronger or weaker small-business credit activity?**
   - Combine lending, business dynamics, and labor-market indicators into dashboard-ready regional comparison views.

### Data Reliability

9. **Is the published data fresh, complete, and valid enough for reporting?**
   - Track source freshness, row counts, null checks, schema checks, and dbt test results.

10. **Can the reported KPIs be traced back to raw source extracts?**
    - Preserve raw files, ingestion manifests, and transformation lineage so results are reproducible.

## MVP Scope

The MVP will focus on building a reliable state-level analytics pipeline and dashboard using public data sources.

### Included in MVP

| Area | MVP Scope |
|---|---|
| Data sources | SBA lending data, Census business dynamics data, BLS labor-market data |
| Geography | U.S. national and state-level analysis |
| Time grain | Monthly, quarterly, or annual depending on source availability |
| Lending dimensions | Time, state, lender, industry, loan program |
| Economic context | Business formation / establishment indicators and unemployment indicators |
| Storage | Raw source extracts stored in AWS S3 using date-partitioned prefixes |
| Local development | DuckDB used for local ingestion, exploration, and development |
| Final warehouse | Snowflake used for final modeled tables |
| Transformations | dbt Core staging, mart, and BI-facing models |
| Data quality | dbt tests, row-count checks, null checks, schema checks, and freshness checks |
| Orchestration | Prefect flow for end-to-end refresh |
| Dashboard | Power BI dashboard built from modeled mart or BI tables |
| Documentation | Project spec, KPI dictionary, data dictionary, architecture notes, dashboard spec, README |

### MVP Business Deliverables

The MVP should produce the following business-facing outputs:

1. Executive lending overview dashboard.
2. State-level lending trend dashboard.
3. Industry lending dashboard.
4. Lender concentration dashboard.
5. Regional business-health context dashboard.
6. Data quality / pipeline health dashboard or report section.

### MVP Technical Deliverables

The MVP should produce the following technical outputs:

1. Python ingestion scripts for each source.
2. Raw data landing structure in S3.
3. Ingestion manifest files with metadata about source pulls.
4. Local DuckDB development database.
5. Snowflake-ready load and transformation workflow.
6. dbt staging models.
7. dbt mart models.
8. dbt tests and custom validation checks.
9. Prefect orchestration flow.
10. Docker-based local development setup.
11. Power BI dashboard connected to final modeled tables.
12. Clear README and supporting documentation.

## Primary Grain Decisions

The project will use different grains at different layers of the pipeline.

| Layer | Intended Grain | Notes |
|---|---|---|
| Raw SBA lending | Source file grain, usually one row per loan or loan record | Stored as received before standardization |
| Staged SBA lending | One cleaned row per loan record | Standardized dates, geography, lender, industry, and amount fields |
| Lending marts | Aggregated by state, time period, lender, industry, and program | Used for KPI reporting |
| Census business dynamics | Source-defined geography, industry, and time grain | May be annual depending on source availability |
| BLS labor-market data | State and month where available | Used as economic context, not as the core fact table |
| BI tables | Dashboard-specific aggregated grain | Optimized for Power BI usability |

## Analysis Boundaries

The MVP should prioritize consistency and interpretability over maximum data complexity.

### Geography Boundary

The MVP will focus on state-level analysis.

State-level analysis is the right first boundary because:

- it is easier to join consistently across SBA, Census, and BLS sources;
- it avoids premature complexity from county and metro-area normalization;
- it supports clear Power BI maps and trend comparisons;
- it is understandable to recruiters and business users.

County-level or metro-level analysis can be added later only if join quality and source coverage are strong.

### Time Boundary

The MVP will support trend analysis using the most reliable time grain available by source.

The project should not force all sources into the same time grain if the data does not support it cleanly. Instead, the model should document the grain of each source and aggregate only when defensible.

Expected approach:

- SBA lending: approval date aggregated to month, quarter, and year where available.
- BLS labor-market data: monthly state-level indicators where available.
- Census business dynamics data: annual or source-defined period indicators where available.

### Industry Boundary

The MVP will use NAICS-based industry groupings where available.

The first version should prioritize broad NAICS sector or industry group analysis instead of highly granular industry drilldowns. This keeps the dashboard readable and reduces noise from sparse categories.

### Lender Boundary

The MVP will analyze lenders as named institutions from the SBA source data.

The first version will not attempt complex lender entity resolution beyond basic standardization, trimming, casing, and documented cleanup rules.

## Out of Scope for MVP

The MVP will not include the following:

### Machine Learning and Predictive Modeling

- predictive machine learning model training
- loan approval prediction
- borrower creditworthiness scoring
- loan default prediction
- next-period lending forecasts
- automated lending recommendations

### Advanced Risk or Compliance Use Cases

- borrower-level risk scoring
- lender compliance review
- fraud detection
- fair lending analysis
- causal inference about lending outcomes
- regulatory reporting certification

### Overextended Data Engineering Scope

- real-time or streaming ingestion
- AWS Glue
- AWS Lambda
- AWS Step Functions
- AWS Athena
- AWS Redshift
- EMR or Spark-based processing
- Kubernetes deployment
- Terraform-managed cloud infrastructure
- production-grade monitoring stack

### Overextended Data Scope

- paid data sources
- private credit bureau data
- borrower financial statements
- proprietary lender data
- manual web scraping where an API or downloadable file is available
- full county-level normalization in the first version
- full metro-area normalization in the first version

### Dashboard Scope Exclusions

- embedded analytics application
- row-level security implementation
- writeback functionality
- live operational alerting
- executive pixel-perfect report production

## Stretch Goals

Stretch goals should only be considered after the MVP pipeline, dbt models, tests, orchestration, and Power BI dashboard are working end-to-end.

| Stretch Goal | Description | Priority |
|---|---|---:|
| County-level analysis | Add county-level lending and economic context where joins are reliable | Medium |
| Metro-area analysis | Add CBSA or metro-level views if source geography can be standardized | Medium |
| Lender entity cleanup | Improve lender name standardization and grouping | Medium |
| Regional scorecard | Add a transparent, rules-based regional lending or business-health score | Medium |
| Power BI drillthrough pages | Add drillthrough from state to industry or lender detail | Low |
| Snowflake external stage | Load raw S3 files into Snowflake using an external stage | Medium |
| Data quality dashboard | Publish dbt test results and validation summaries as a dashboard page | High |
| CI checks | Add GitHub Actions for pytest and dbt checks | Medium |
| Historical snapshot comparison | Compare current ingestion to prior ingestion for row-count and metric drift | High |

## Explicit Non-ML Decision

Predictive machine learning is intentionally excluded from the MVP.

This project is designed to demonstrate analytics engineering and business intelligence delivery, not data science modeling. The strongest portfolio signal comes from building a clean, tested, documented, reproducible pipeline that produces trusted KPI tables and a stakeholder-facing dashboard.

Any future scoring should be rules-based, transparent, and derived from documented KPIs. It should not be presented as a predictive model.

## Scope Control Principles

The project should follow these scope control principles:

1. **Local-first development before cloud polish.**
   - Build the pipeline locally with DuckDB before expanding to Snowflake and S3-backed workflows.

2. **Modeled tables before dashboard design.**
   - Power BI should connect to mart or BI tables, not raw source extracts.

3. **Tested data before published KPIs.**
   - dbt and Python validation checks should run before dashboard outputs are considered trusted.

4. **State-level first, lower geography later.**
   - State-level analysis keeps the MVP consistent across sources.

5. **Transparent assumptions over false precision.**
   - Grain mismatches, data limitations, and source caveats should be documented.

6. **Recruiter clarity over technical sprawl.**
   - The project should be understandable from the README, architecture diagram, and dashboard screenshots within five minutes.

## Step 3 Summary

The MVP will answer a focused set of analytical questions about SBA lending activity, lender concentration, industry trends, and regional business-health context. It will use public SBA, Census, and BLS data at a primarily state-level grain, modeled through a tested SQL/dbt pipeline and published through Power BI.

The project intentionally excludes predictive machine learning, borrower-level risk scoring, real-time processing, and unnecessary cloud infrastructure. The priority is a complete, reproducible, well-documented analytics engineering project with clear business value.
