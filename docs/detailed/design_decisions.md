# Engineering decisions and recorded benchmarks

These records explain choices made during implementation. Measurements below
come from May 2026 retained inputs and were not rerun for the October portfolio
cleanup. They are observations from one local environment, not performance
guarantees for the current warehouse.

## Native DuckDB loading

The local SBA loader uses DuckDB's native CSV scan instead of materializing the
full input in Python. On May 24, the recorded raw-load comparison used the same
saved May 20 source artifacts:

| Measurement | Earlier path | Native CSV path |
|---|---:|---:|
| Wall time | 28.6 seconds | 18.069 seconds |
| Maximum resident memory | About 4.7 GB | 2,002,464,768 bytes (about 2.0 GB) |

The resulting warehouse was 182,202,368 bytes. Source counts matched:
1,947,098 7(a) records, 227,404 504 records, 22,746 BLS state-month records and
1,734 Census state-year records. The subsequent fast build passed four seeds,
51 models and 33 critical tests; the 17-table BI export and model contract passed.
These counts identify the historical benchmark population, not today's inputs.

The implementation streams checksum inspection and disables Hive partition
inference on SBA CSV scans so artifact-directory names cannot introduce columns
that collide with explicit lineage metadata. See the
[architecture](architecture.md#local-and-cloud-routes) for current load protections.

## Persist modeled results where repeated work is expensive

Staging remains views; facts, marts and BI outputs are materialized as tables.
The recorded experiment reduced a full local build from about 313.8 to 31.6
seconds, while adding about 220 MB to DuckDB. This spends working database space
to avoid repeatedly expanding SBA-heavy views during tests and exports.

A later May 24 check recorded a 32.079-second full build and a 29.902-second
BI refresh with no change in raw bytes. Results varied between runs, so these
measurements do not support a fixed speedup promise. Current materialization
settings belong to `dbt/dbt_project.yml`; command effects and fast/full test
scope belong to the [runtime guide](orchestration_runtime.md#command-scope).

## Rejected intermediate table

A broad intermediate loan table reduced the fact model's time by about four
seconds but added a 14–15 second table build and hundreds of MB to the warehouse.
Both full and BI refreshes became slower. The table was rejected: the unit of
evaluation was the whole workflow, not the fastest isolated model.

Direct deterministic lender/source-file keys and explicit union columns were
retained. The recorded check preserved 2,174,502 fact rows and their key coverage;
relationship tests checked referential integrity. These are historical checks,
not substitutes for the current source-contract gate.

## Rejected load-time record numbering

A trial moved record numbering from staging to the raw loader. Total rows stayed
equal, but 2,058,678 fact keys differed in each direction. The staging ordinal
over selected manifest rows was not equivalent to a file-load ordinal. The trial
was rolled back. This is why equal counts alone cannot establish record identity
or authorize a change to fact keys.

## Keep definitions and evidence at their owners

dbt owns eligibility, source alignment and additive components; Power BI divides
or ranks those components under supported selections. Snapshot validation,
publication recency, raw loading and final flow completion remain separate facts.
The [methodology](kpi_definitions.md) and [verification guide](testing_plan.md)
explain those contracts.

The implemented S3/Snowflake route loads validated S3 artifacts through an
external stage; there is no alternate local-file Snowflake route. Paid live cloud
execution is deferred. Old task plans and execution transcripts have been retired;
the [documentation map](../README.md) identifies maintained owners and the
[verification appendix](../implementation/lending_verification_history.md) records
the dated October evidence and remaining report work.
