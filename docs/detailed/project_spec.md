# Project specification

Current scope, October 7, 2026. The Small Business Lending Intelligence Pipeline
is a personal, local-first descriptive analytics engineering project. Its business
question is: **Where is SBA lending concentrated, how does the picture change
relative to the local business base, and how can comparisons be trustworthy?**

The audience is an analyst or technical portfolio reviewer. Success means they
can inspect actual findings quickly, trace the source population and denominator,
and reproduce validated modeled outputs. This is public historical SBA approval
activity, not all small-business credit or borrower creditworthiness.

## Accepted capabilities

- Ingest public SBA 7(a)/504, Census BDS and BLS LAUS separately.
- Preserve immutable raw extracts, manifests, checksums, row counts, validation and
  lineage; report from validated selected snapshots.
- Support DuckDB locally and the implemented S3/Snowflake promotion route. Keep
  identical logical BI contracts and adapter-compatible dbt transformations.
- Orchestrate with Prefect, retaining stage outcomes/timings and the actual final
  run summary. Keep validity, source age, raw loads and completion distinct.
- Provide trusted dbt facts, marts and BI components; a small versioned Power BI
  semantic layer handles supported filter-context aggregation.
- Deliver the six dashboard pages in [dashboard_spec.md](dashboard_spec.md), with
  meaningful coverage/period labels, reproducible handoff and genuine screenshots.
- Keep Python 3.12, Make, pytest, dbt and Ruff gates plus the Docker runtime.
- Present the findings and engineering story in one HTML reader report, available
  offline and through GitHub Pages after CI. The README introduces the project;
  generated aggregates and maintained technical documents supply supporting evidence.

No extra services, new feeds, hosted analytics application, monitoring schedules, predictive ML,
borrower scoring, approval/denial predictions, causal jobs/economic impact or
real-time credit decisions are in the MVP. Do not scaffold production operations.
This simplification does not remove the supported cloud route or its custody and
validation requirements.

## Acceptance and honest limits

The report/evidence issues cannot be closed by a model
contract alone: Desktop corrections, fresh screenshots and missing cloud evidence
remain separately owned. The [verification appendix](../implementation/lending_verification_history.md)
records dated observations and
check results; [KPI methodology](kpi_definitions.md) owns scientific definitions.

For the October 4 pre-PBIX handoff, paid Snowflake execution is deliberately
deferred. Preserve the implemented route and distinguish mocked/local checks
from current live cloud certification. This does not close the separate report
or cloud-evidence acceptance tasks.

## Tracker workflow

[GitHub issues](https://github.com/stevennitesh/small-business-lending-pipeline/issues)
are the implementation tracker. A direct user request sets the current scope;
it does not require choosing an unrelated open issue. When the user asks for the
next issue, default to the lowest-numbered open issue unless prerequisites or the
user's selection establish another order.

For issue-based work, read its current acceptance criteria and prerequisites.
Use the current scope and dashboard specification for acceptance. The
[engineering decisions](design_decisions.md) preserve useful rationale and
benchmarks from retired implementation plans; issues own the work queue.

When finishing an implementation issue, preserve the established delivery workflow:
commit and push the verified changes, then comment with the commit hash, checks,
uncertainty and deliberate deferrals using actual Markdown line breaks. Close the
issue only when its acceptance criteria are met or the user explicitly accepts a
narrower result. Guidance maintenance alone does not require tracker mutations.
