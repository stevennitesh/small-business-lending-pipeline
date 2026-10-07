"""Build an offline portfolio report from versioned aggregate evidence and charts.

The standard library is sufficient. This presentation step verifies published
text hashes; it does not reopen raw data or rerun the saved warehouse checks.
"""

from __future__ import annotations

import argparse
import base64
from datetime import date
from decimal import Decimal
import hashlib
from html import escape
import json
from pathlib import Path
from string import Template


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = Path("scripts/portfolio")
CHARTS = ("findings", "geography", "programs", "industries", "lenders", "coverage")
REPO = "https://github.com/stevennitesh/small-business-lending-pipeline"
SITE = "https://stevennitesh.github.io/small-business-lending-pipeline/"
SOURCE_NAMES = {
    "sba": "SBA approval records",
    "census": "Census employer business locations",
    "bls": "BLS state unemployment",
}


def text(path: Path) -> str:
    """Read portable UTF-8 text, normalizing CRLF to LF."""
    return path.read_text(encoding="utf-8")


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def e(value: object) -> str:
    return escape(str(value), quote=True)


def money(value: str | Decimal, *, billions: bool = True) -> str:
    number = Decimal(value)
    return f"${number / Decimal(10**9):,.2f} billion" if billions else f"${number:,.0f}"


def pct(value: str | Decimal) -> str:
    return f"{Decimal(value) * 100:,.2f}%"


def display_date(value: str) -> str:
    return date.fromisoformat(value[:10]).strftime("%B %d, %Y").replace(" 0", " ")


def data_uri(value: str, mime: str) -> str:
    encoded = base64.b64encode(value.encode("utf-8")).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def doc(path: str, label: str) -> str:
    return f'<a href="{REPO}/blob/master/{e(path)}">{e(label)}</a>'


def table(headers: tuple[str, ...], rows: list[list[str]], caption: str) -> str:
    head = "".join(f'<th scope="col">{e(h)}</th>' for h in headers)
    body = "".join(
        "<tr>"
        + "".join(
            f'<th scope="row">{e(cell)}</th>' if i == 0 else f"<td>{e(cell)}</td>"
            for i, cell in enumerate(row)
        )
        + "</tr>"
        for row in rows
    )
    return (
        '<div class="table-scroll" tabindex="0" role="region" '
        f'aria-label="{e(caption)}"><table><caption>{e(caption)}</caption>'
        f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"
    )


def read_evidence(root: Path) -> tuple[dict, dict, dict[str, str]]:
    """Bind every displayed chart and number to the existing public proof."""
    proof_path = root / "docs/images/lending_verification.json"
    proof = json.loads(text(proof_path))
    if proof["schema_version"] != 1:
        raise ValueError("Unsupported public verification schema")
    names = {f"lending_{chart}.svg" for chart in CHARTS} | {
        "lending_analysis.json",
        "analysis_results.md",
    }
    if set(proof["public_outputs"]) != names:
        raise ValueError("Public proof must cover the aggregate report and six charts")
    inputs = {"docs/images/lending_verification.json": text(proof_path)}
    for name in sorted(names):
        folder = "docs/detailed" if name.endswith(".md") else "docs/images"
        relative = f"{folder}/{name}"
        content = text(root / relative)
        if sha(content) != proof["public_outputs"][name]["sha256"]:
            raise ValueError(f"Public evidence hash mismatch: {relative}")
        inputs[relative] = content
    analysis = json.loads(inputs["docs/images/lending_analysis.json"])
    csv_hashes = {
        name: check["sha256"]
        for name, check in proof["chart_generation_checks"]["inputs"].items()
    }
    if analysis["input_csv_sha256"] != csv_hashes:
        raise ValueError("Aggregate and chart proof refer to different CSV inputs")
    if (
        analysis["readiness_checked_at_utc"]
        != proof["recorded_readiness"]["checked_at_utc"]
    ):
        raise ValueError(
            "Aggregate and public proof refer to different readiness checks"
        )
    language = text(root / "powerbi/report_language.json")
    if not (
        sha(language)
        == proof["report_language_sha256"]
        == analysis["report_language_sha256"]
    ):
        raise ValueError("Report vocabulary differs from the public evidence")
    inputs["powerbi/report_language.json"] = language
    return analysis, proof, inputs


def render(root: Path, output_dir: Path) -> dict:
    """Regenerate two small report files without modifying their evidence inputs."""
    a, proof, inputs = read_evidence(root)
    language = json.loads(inputs["powerbi/report_language.json"])
    for name in ("index.html", "report.css", "report.js"):
        relative = (TEMPLATES / name).as_posix()
        inputs[relative] = text(root / relative)
    inputs["scripts/render_portfolio_report.py"] = text(
        root / "scripts/render_portfolio_report.py"
    )
    year, context = a["lending_year"], a["context_year"]
    h = a["headline"]
    annual = {row["year"]: row for row in a["trend"]}
    if year not in annual or year - 1 not in annual:
        raise ValueError("Report needs the selected and prior lending years")
    prior = annual[year - 1]
    for key in ("amount", "records", "known_amount_records", "average"):
        if h[key] != annual[year][key]:
            raise ValueError(f"Headline differs from the selected trend year: {key}")
    if h["growth"] is None:
        raise ValueError("This report requires a supported comparable annual change")
    growth = Decimal(h["growth"])
    records_change = Decimal(h["records"]) / Decimal(prior["records"]) - 1
    dollars_direction = (
        "rose" if growth > 0 else "fell" if growth < 0 else "were unchanged"
    )
    records_direction = (
        "rose"
        if records_change > 0
        else "fell"
        if records_change < 0
        else "were unchanged"
    )
    movement = (
        "More reported dollars, fewer approval records"
        if growth > 0 and records_change < 0
        else "Read dollar totals alongside approval records"
    )
    geography = sorted(a["geography"], key=lambda r: (-Decimal(r["amount"]), r["key"]))
    intensity = sorted(
        a["geography"], key=lambda r: (-Decimal(r["intensity"]), r["key"])
    )
    top_state, top_intensity = geography[0], intensity[0]
    industry = a["industries"][0]
    checked = display_date(a["freshness_checked_at_utc"])
    scope = (
        "50 states and Washington, DC"
        if a["state_count"] == 51
        else f"{a['state_count']} reporting geographies"
    )

    def figure(
        name: str, number: int, title: str, description: str, source: str
    ) -> str:
        uri = data_uri(inputs[f"docs/images/lending_{name}.svg"], "image/svg+xml")
        return f"""<figure id="chart-{name}" aria-labelledby="{name}-title">
        <div class="figure-heading"><div><span class="eyebrow">Figure {number}</span>
        <h3 id="{name}-title">{e(title)}</h3></div>
        <div class="chart-actions"><button type="button" class="zoom" hidden
        aria-haspopup="dialog" aria-label="Enlarge {e(title)}">Enlarge chart ↗</button>
        <a href="{uri}" download="lending_{name}.svg">Download SVG</a></div></div>
        <div class="chart-scroll" tabindex="0" role="region" aria-label="{e(title)} chart">
        <img src="{uri}" alt="{e(description)}" loading="lazy"></div>
        <p class="mobile-hint">Scroll sideways to inspect the chart, or enlarge it.</p>
        <figcaption>{e(description)} <span class="chart-source">{e(source)}</span></figcaption>
        </figure>"""

    trend_description = (
        f"In {year}, reported amounts {dollars_direction} to {money(h['amount'])} "
        f"and approval records {records_direction} to {h['records']:,} "
        f"from {prior['records']:,} in {year - 1}."
    )
    geography_description = (
        f"{top_state['label']} leads {context} reported dollars at "
        f"{money(top_state['amount'])}. {top_intensity['label']} leads approval records "
        f"per 1,000 employer business locations at {Decimal(top_intensity['intensity']):.2f}."
    )
    programs_description = " ".join(
        f"{row['label']} accounts for {pct(row['share'])} of reported {year} amounts."
        for row in a["programs"]
    )
    industries_description = (
        f"{industry['label']} leads known-industry amounts at {pct(industry['share'])}. "
        f"Known sectors cover {pct(a['industry_coverage'])} of all reported {year} dollars."
    )
    lenders_description = (
        f"The five largest reporting lender names account for "
        f"{pct(a['top_five_lender_share'])} of known-name {year} dollars. "
        f"Known names cover {pct(a['lender_coverage'])} of all dollars."
    )
    source_rows = []
    for row in a["sources"]:
        system = row["system"]
        reference = row["publication_reference_date"]
        if system == "sba":
            period = date.fromisoformat(reference)
            reference = f"{period.year} Q{(period.month - 1) // 3 + 1}"
        elif system == "census":
            reference = reference[:4]
        else:
            reference = reference[:7]
        source_rows.append(
            [
                SOURCE_NAMES[system],
                reference,
                row["publication_date"] or "Not confirmed",
                row["publication_verified_date"],
                ", ".join(row["download_dates"]),
                "; ".join(
                    language["freshness_reason_labels"][reason]
                    for reason in row["reasons"]
                ),
            ]
        )
    readiness = proof["recorded_readiness"]
    evidence_table = table(
        ("Saved-data check", "Recorded result"),
        [
            [
                "Reporting tables / rows",
                f"{readiness['csv_tables']} / {readiness['csv_rows']:,}",
            ],
            [
                "CSV versus warehouse differences",
                str(readiness["csv_warehouse_differences"]),
            ],
            [
                "Duplicate / missing record keys",
                f"{readiness['duplicate_grains']} / {readiness['null_grain_keys']}",
            ],
            [
                "Relationships / unmatched keys",
                f"{readiness['relationships']} / {readiness['unmatched_relationship_keys']}",
            ],
            ["Readiness checked (UTC)", readiness["checked_at_utc"]],
        ],
        "Prior verification of saved reporting data",
    )
    values = {
        "styles": inputs[(TEMPLATES / "report.css").as_posix()],
        "script": inputs[(TEMPLATES / "report.js").as_posix()],
        "year": str(year),
        "context": str(context),
        "checked": e(checked),
        "scope": e(scope),
        "movement": e(movement),
        "amount": e(money(h["amount"])),
        "records": f"{h['records']:,}",
        "known_records": f"{h['known_amount_records']:,}",
        "growth": pct(growth),
        "records_change": pct(records_change),
        "average": money(h["average"], billions=False),
        "prior_year": str(year - 1),
        "trend_description": e(trend_description),
        "geography_description": e(geography_description),
        "programs_description": e(programs_description),
        "industries_description": e(industries_description),
        "lenders_description": e(lenders_description),
        "trend_chart": figure(
            "findings",
            1,
            "Annual approval activity",
            trend_description,
            "Source: SBA 7(a)/504 approval records; calendar years. Nominal amounts, including canceled/not-funded approvals.",
        ),
        "geography_chart": figure(
            "geography",
            2,
            f"Two ways to compare states · {context}",
            geography_description,
            "Sources: SBA approvals and Census BDS employer establishments. Both rankings use the same calendar year; source observation windows differ.",
        ),
        "program_chart": figure(
            "programs",
            3,
            f"Program contribution · {year}",
            programs_description,
            "Source: SBA. Whole 7(a) loans plus the SBA/Certified Development Company portion of 504 loans.",
        ),
        "industry_chart": figure(
            "industries",
            4,
            f"Industry distribution · {year}",
            industries_description,
            "Source: SBA; North American Industry Classification System (NAICS) sectors. Shares divide by known-sector dollars; unknown classifications remain in overall totals.",
        ),
        "lender_chart": figure(
            "lenders",
            5,
            f"Largest reporting lender names · {year}",
            lenders_description,
            "Source: SBA. Names are ranked after aggregation across the selected geography; they do not resolve banking groups or historical originators.",
        ),
        "coverage_chart": figure(
            "coverage",
            6,
            "Source reference periods and publication dates",
            f"Publisher and download checks were evaluated on {checked} UTC. Opening the report later does not update this evidence.",
            "Sources: SBA, Census BDS and BLS LAUS. Reference period, publication and download dates are separate clocks.",
        ),
        "trend_table": table(
            ("Calendar year", "Reported amounts", "Approval records"),
            [
                [str(r["year"]), money(r["amount"]), f"{r['records']:,}"]
                for r in a["trend"]
            ],
            "Annual approval totals",
        ),
        "geography_table": table(
            ("State", "Reported amounts", "Approval records"),
            [
                [r["label"], money(r["amount"]), f"{r['records']:,}"]
                for r in geography[:6]
            ],
            f"Largest state dollar totals · {context}",
        ),
        "intensity_table": table(
            ("State", "Records per 1,000 locations"),
            [[r["label"], f"{Decimal(r['intensity']):.2f}"] for r in intensity[:6]],
            f"Highest activity relative to employer locations · {context}",
        ),
        "program_table": table(
            ("Program", "Reported amounts", "Share of all amounts", "Approval records"),
            [
                [r["label"], money(r["amount"]), pct(r["share"]), f"{r['records']:,}"]
                for r in a["programs"]
            ],
            f"Program totals · {year}",
        ),
        "industry_table": table(
            ("Industry", "Reported amounts", "Share of known-sector amounts"),
            [
                [r["label"], money(r["amount"]), pct(r["share"])]
                for r in a["industries"]
            ],
            f"Known-industry totals · {year}",
        ),
        "lender_table": table(
            (
                "Reporting lender name",
                "Reported amounts",
                "Share of known-name amounts",
            ),
            [[r["label"], money(r["amount"]), pct(r["share"])] for r in a["lenders"]],
            f"Five largest reporting lender names · {year}",
        ),
        "source_table": table(
            (
                "Source",
                "Verified reference",
                "Published on",
                "Publisher checked",
                "Downloaded",
                "Assessment at check",
            ),
            source_rows,
            "Frozen publication and download evidence",
        ),
        "source_links": " · ".join(
            f'<a href="{e(r["publication_source_url"])}">{e(SOURCE_NAMES[r["system"]])}</a>'
            for r in a["sources"]
        ),
        "unknown_industry": e(money(a["unknown_industry"]["amount"]))
        + f" / {a['unknown_industry']['records']:,} records",
        "unknown_lender": e(money(a["unknown_lender_amount"]))
        + f" / {a['unknown_lender_records']:,} records",
        "evidence_table": evidence_table,
        "aggregate_uri": data_uri(
            inputs["docs/images/lending_analysis.json"], "application/json"
        ),
        "proof_uri": data_uri(
            inputs["docs/images/lending_verification.json"], "application/json"
        ),
        "method_link": doc("docs/detailed/kpi_definitions.md", "Metric definitions"),
        "architecture_link": doc(
            "docs/detailed/architecture.md", "Architecture and component ownership"
        ),
        "decision_link": doc(
            "docs/detailed/design_decisions.md",
            "Engineering decisions and benchmark limits",
        ),
        "test_link": doc("docs/detailed/testing_plan.md", "Verification contracts"),
        "history_link": doc(
            "docs/implementation/lending_verification_history.md",
            "Dated verification history",
        ),
        "runtime_link": doc(
            "docs/detailed/orchestration_runtime.md", "Runtime and reproduction guide"
        ),
        "powerbi_link": doc(
            "powerbi/README.md", "Power BI handoff and remaining Desktop work"
        ),
        "repo": REPO,
        "site": SITE,
    }
    html = Template(inputs[(TEMPLATES / "index.html").as_posix()]).substitute(values)
    provenance = {
        "schema_version": 1,
        "scope": "HTML presentation rebuilt from hash-verified public aggregates and existing charts; prior data checks are not rerun",
        "source_readiness_checked_at_utc": a["readiness_checked_at_utc"],
        "source_publication_checked_at_utc": a["freshness_checked_at_utc"],
        "text_hash_policy": "SHA256 of UTF-8 text with LF line endings",
        "inputs": {
            name: {"sha256": sha(value)} for name, value in sorted(inputs.items())
        },
        "outputs": {
            "index.html": {"sha256": sha(html), "bytes": len(html.encode("utf-8"))}
        },
        "not_executed": [
            "CSV and warehouse readiness verification",
            *proof["chart_generation_checks"]["not_executed"],
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "index.html").write_text(html, encoding="utf-8", newline="\n")
    (output_dir / "provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return provenance


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports/portfolio")
    args = parser.parse_args()
    result = render(ROOT, args.output_dir)
    print(
        f"Wrote {args.output_dir / 'index.html'} ({result['outputs']['index.html']['bytes']:,} bytes)"
    )


if __name__ == "__main__":
    main()
