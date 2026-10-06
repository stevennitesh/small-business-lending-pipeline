# Source inventory and coverage

The three inputs are U.S. Small Business Administration (SBA) approval records,
Census Business Dynamics Statistics (BDS) employer business locations, and Bureau
of Labor Statistics (BLS) Local Area Unemployment Statistics (LAUS) state rates.
They retain separate extractors and grains. Configuration and
source-specific parser/validation code are the executable contracts; saved raw
payloads remain the evidence for any result.

| Source | Access and owner | Grain / use |
|---|---|---|
| SBA 7(a)/504 FOIA | SBA dataset-page distribution links; `config/sba_resources.yml`, `pipelines/extract/sba_extract.py` | Approval record; geographic/program/industry/name distribution |
| Census Business Dynamics Statistics | Census BDS API; `config/census_bds_variables.yml`, Census extractor | Employer-establishment state/year context, counts and published entry/exit rates |
| BLS Local Area Unemployment Statistics | BLS API and configured state-series IDs; `config/bls_laus_state_series.yml`, BLS extractor | Monthly seasonally adjusted state unemployment-rate context |

Exact extractor filenames and access contracts are in `pipelines/extract/`.
`config/sources.yml` owns enabled sources and identities;
`config/raw_validation_expectations.yml` owns raw acceptance checks.
[Reporting policy](../../config/reporting_policy.yml) owns dated completeness
assumptions; [freshness rules](../../config/freshness_rules.yml) own age tolerances.

## SBA population and geography

Live discovery reads the CSV/XLSX distribution links from the
[SBA dataset page](https://data.sba.gov/dataset/7a-504-foia), normalizes titles
(including `7a` versus `7(a)`) and matches the configured seven logical resources.
The former CKAN `package_show` endpoint returned HTTP 404 on October 4, 2026.
Configured JSON metadata and explicitly supplied fixture metadata remain supported;
no release filename is hardcoded. The cached normalized links and extract manifests
retain publisher URLs. Multiple matching download URLs fail discovery instead of
selecting an arbitrary release. Discovering a newer release does not refresh the saved
extract or change its coverage policy; review both when deliberately refreshing.

The October 5, 2026 UTC download includes calendar approval dates 1990-10-01 through
2026-06-30, matching the June 30 publisher release. Fiscal-year resource ranges are discovery metadata, not calendar-year
labels. Records with missing calendar dates do not acquire one from fiscal year.
Canceled/not-funded statuses remain in approvals; disbursement is not eligibility.
Mapped project geography is required for state marts, separate from borrower
location. Unmapped/unknown geography and unknown classifications need disclosure.
Reporting units normalize currently assigned 7(a) `BankName` and 504
`ThirdPartyLender_Name`. The 504 `CDC_Name` and `LocationID` identify a separate
SBA lender role; `LocationID` is not a loan identifier. Names attribute historical
records in the selected snapshot, without historical originator/merger resolution.
`GrossApproval` reports whole loans for 7(a) and SBA/CDC portions for 504; combined
amounts do not represent total borrower/project financing.
[SBA dictionary](https://data.sba.gov/sites/default/files/uploaded_resources/7a_504_foia_data_dictionary.xlsx).

Public SBA records cannot measure loan applications, denial rates, unique
borrowers, total small-business credit or causal impact. Amounts are nominal.
Snapshots may contain revisions and source errors despite pipeline validation.
The June 30 release uses ISO dates and omits the optional `Subprogram` field.
Both local and cloud loaders supply a null optional column when absent; staging
accepts ISO and earlier month/day/year dates without altering retained CSV bytes.

## Census denominator

BDS covers employer establishments across firm sizes, not an exact small-business
population or a count of borrowers. Intensity joins the same state/year lending
and establishment rows. Summing annual stocks across years means establishment-
years as a proxy from annual reference stocks. BDS uses March 12 reference
stocks and March-to-March flows; calendar-year lending is contextual comparison.
Nonemployers and excluded sectors make the numerator/denominator scopes imperfect.
Published rates use scope-consistent mean stocks: prior stock is current stock
plus exits minus entries. Do not use naive adjacent published stocks or average
state rates.
[Census population](https://www.census.gov/programs-surveys/bds/about.html) and
[rate definition](https://www.census.gov/programs-surveys/bds/about/faq.html).
BDS is updated annually, typically in September, about two years after its
reference year. This differs from Census programs with longer survey cycles.
[Official BDS release frequency and lag](https://www.census.gov/programs-surveys/bds/about/faq.html).
The October 5 API refresh still ends in 2023, the latest published BDS year.
The Census release was published September 25, 2025; observation lag remains
visible separately from the new download timestamp. Release verification uses the
maintained year/date/URL evidence and a 90-day local review window. Old observation
age remains descriptive; only a missed verified publication is stale. Old downloads
or expired checks require verification instead.
[Census release and updates](https://www.census.gov/programs-surveys/bds/news-updates/updates.html).

## BLS coverage and interpretation

The configured series are monthly seasonally adjusted unemployment rates. Annual
output is their arithmetic mean, not official annual labor-force-weighted estimates.
Observed/expected months, source omissions, missing available months, YTD and
comparability are exposed. **BLS did not publish October 2025**, yielding 11-month
annual averages that are not strictly comparable with ordinary years. This known
publisher exception is valid data, not ingestion failure, and is not imputed.
[BLS notice](https://www.bls.gov/lau/launews1.htm).

No national/regional rate is formed by averaging state rates. LAUS revisions and
release delays remain possible. Use 2023 as the saved comparable context default;
The validated October 5 LAUS extract has 23,052 rows through August 2026:
23,001 numeric state-month observations and 51 explicit missing October 2025 rows.
Each state has eight observed/expected months in 2026, while SBA ends June 30.
These are separate YTD periods and neither supports full-year growth. New source releases require verified
coverage-policy updates, not an inference from sparse row min/max.

## Custody and evidence

Every extract carries source URL, request metadata, extraction/ingestion timestamps,
resource identity, run identity, location, checksum, schema hash and row count.
Raw validation is retained independently of dbt results and final run completion.
Census row shape and unique state-year grain are checked again on retained payloads;
every returned year must meet configured state coverage. BLS malformed monthly
values stay in the normalized payload so numeric/range validation can reject them.
Series-month rows must be unique, with matching period/year/date identities and
configured series IDs. Documented publisher omissions can be absent rows or explicit `-` markers.
Raw validation accepts a marker only for the maintained omitted month, with
consistent identities and the publisher's nonempty code-X footnote. Staging keeps
its rate null; annual coverage counts only numeric observations. Other malformed
values still fail validation. Invalid JSON produces retained blocking
validation evidence rather than bypassing result persistence.
S3/Snowflake and local routes share those obligations. Fixed fixtures prove parser
and orchestration behavior; they do not establish live publisher completeness.
See [architecture](architecture.md), [methodology](kpi_definitions.md) and
[dated evidence](case_study.md).

## Publication dates and reference periods

The October 5 verified SBA catalog confirms quarter-end coverage through June 30;
it says quarterly files are typically available one month after quarter end.
The dataset-level modified timestamp does not establish this particular release's
publication date, which remains unconfirmed.
[SBA catalog](https://data.sba.gov/dataset/7a-504-foia).

The August 2026 state LAUS release was published September 18, 2026 and announced
October 20 for the September state release. This is the state program used here,
separate from the earlier national employment release.
[BLS dated state release](https://www.bls.gov/news.release/archives/laus_09182026.htm).
The next announced date remains a schedule, not a verified new observation.

Reporting exposes actual publication dates where established, saved reference
periods, download and publisher-check dates separately. A newer verified period
makes saved inputs stale; old reference years and expired review windows alone do
not. Unknown publication dates stay null rather than adopting coverage or catalog dates.
