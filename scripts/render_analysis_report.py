"""Publish compact charts and an aggregate reader report from checked local exports.

Matplotlib is optional presentation tooling; it is not a pipeline dependency.
No warehouse, source extract or Power BI binary is opened or changed.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import textwrap
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
TABLES = (
    "bi_state_lending_trends",
    "bi_regional_business_health",
    "bi_program_mix",
    "bi_industry_mix",
    "bi_lender_mix",
    "bi_source_freshness",
)
CHART_NAMES = (
    "findings",
    "geography",
    "programs",
    "industries",
    "lenders",
    "coverage",
)
AMOUNT = "total_approved_loan_amount"
BLUE = "#21618c"
TEAL = "#117864"
GRAY = "#718096"
INK = "#172b3a"
SVG_NS = "http://www.w3.org/2000/svg"
LANGUAGE_FILE = ROOT / "powerbi/report_language.json"
AMOUNT_NOTE = (
    "Nominal approvals, including canceled/not-funded records; not disbursements.\n"
    "7(a): whole-loan amount; 504: SBA/Certified Development Company portion."
)


def checksum(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def text_checksum(path: Path) -> str:
    """Hash versioned UTF-8 text consistently across LF and CRLF checkouts."""
    return hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()


def public_verification(evidence: dict, outputs: dict[str, Path]) -> dict:
    """Publish only aggregate proof, with recorded and newly executed checks separate."""
    checks = evidence["csv_checks"]
    return {
        "schema_version": 1,
        "recorded_readiness": {
            "scope": "Prior saved-data verification; not rerun by the chart generator",
            "checked_at_utc": evidence["checked_at_utc"],
            "csv_tables": len(checks),
            "csv_rows": sum(check["rows"] for check in checks.values()),
            "csv_warehouse_differences": sum(
                check["warehouse_differences"] for check in checks.values()
            ),
            "duplicate_grains": sum(
                check["duplicate_grains"] for check in checks.values()
            ),
            "null_grain_keys": sum(
                check["null_grain_keys"] for check in checks.values()
            ),
            "relationships": len(evidence["relationship_checks"]),
            "unmatched_relationship_keys": sum(
                check["unmatched_keys"] for check in evidence["relationship_checks"]
            ),
        },
        "chart_generation_checks": {
            "scope": "Executed before publication: six input byte hashes and row counts; selected category amount, record and known-amount reconciliation",
            "inputs": {
                table: {
                    "rows": checks[table]["rows"],
                    "sha256": checks[table]["sha256"],
                }
                for table in TABLES
            },
            "not_executed": [
                "source download",
                "warehouse rebuild",
                "full dbt data test suite",
                "Power BI Desktop DAX or Power Query",
                "live cloud execution",
            ],
        },
        "public_text_hash_policy": "SHA256 of UTF-8 text with line endings normalized to LF; CSV hashes use exact bytes",
        "generator_sha256": text_checksum(Path(__file__)),
        "report_language_sha256": text_checksum(LANGUAGE_FILE),
        "public_outputs": {
            name: {"sha256": text_checksum(path)} for name, path in outputs.items()
        },
    }


def read_checked_exports(export_dir: Path, readiness_path: Path) -> tuple[dict, dict]:
    """Bind presentation to the CSV bytes actually checked by the readiness tool."""
    evidence = json.loads(readiness_path.read_text(encoding="utf-8"))
    tables = {}
    for table in TABLES:
        path = export_dir / f"{table}.csv"
        check = evidence["csv_checks"][table]
        if checksum(path) != check["sha256"]:
            raise ValueError(f"{table}: export changed since readiness verification")
        if any(
            check[key]
            for key in ("warehouse_differences", "duplicate_grains", "null_grain_keys")
        ):
            raise ValueError(f"{table}: readiness did not pass")
        with path.open(encoding="utf-8", newline="") as stream:
            tables[table] = list(csv.DictReader(stream))
        if len(tables[table]) != check["rows"]:
            raise ValueError(f"{table}: readiness row count differs")
    return tables, evidence


def number(row: dict, field: str) -> Decimal:
    return Decimal(row[field]) if row[field] else Decimal(0)


def totals(rows: list[dict]) -> dict:
    """Mean denominator is known amounts, distinct from approval record volume."""
    amount = sum((number(row, AMOUNT) for row in rows), Decimal(0))
    records = sum(int(row["loan_count"]) for row in rows)
    known = sum(int(row["approval_amount_coverage_count"]) for row in rows)
    return {
        "amount": amount,
        "records": records,
        "known_amount_records": known,
        "average": amount / known if known else None,
    }


def group_totals(rows: list[dict], key: str, label: str) -> list[dict]:
    groups = {}
    for row in rows:
        groups.setdefault(row[key], []).append(row)
    result = [
        {"key": value, "label": grouped[0][label], **totals(grouped)}
        for value, grouped in groups.items()
    ]
    return sorted(result, key=lambda row: (-row["amount"], row["key"]))


def annual_comparison(current: list[dict], prior: list[dict]) -> Decimal:
    """Missing states are not zero; require the same complete-year population."""
    if not current or not prior:
        raise ValueError("Annual comparison needs both years")
    if {row["state_key"] for row in current} != {row["state_key"] for row in prior}:
        raise ValueError("Annual comparison has different state populations")
    if any(row["is_full_calendar_year"] != "true" for row in current + prior):
        raise ValueError("Annual comparison includes a partial year")
    previous = totals(prior)["amount"]
    if previous <= 0:
        raise ValueError("Annual comparison has no positive prior amount")
    return totals(current)["amount"] / previous - 1


def build_analysis(
    tables: dict, lending_year: int, context_year: int, start_year: int
) -> dict:
    annual = tables["bi_state_lending_trends"]
    by_year = {
        year: [row for row in annual if int(row["approval_year"]) == year]
        for year in range(start_year, lending_year + 1)
    }
    if start_year >= lending_year:
        raise ValueError("Trend needs at least two years")
    for rows in by_year.values():
        if not rows or any(row["is_full_calendar_year"] != "true" for row in rows):
            raise ValueError("Trend requires complete calendar years")
    for year in range(start_year + 1, lending_year + 1):
        annual_comparison(by_year[year], by_year[year - 1])
    selected = by_year[lending_year]
    headline = totals(selected)
    headline["growth"] = annual_comparison(selected, by_year[lending_year - 1])
    context = [
        row
        for row in tables["bi_regional_business_health"]
        if int(row["year"]) == context_year
    ]
    if not context or any(
        row["is_comparable_context"] != "true"
        or row["has_matched_establishment_population"] != "true"
        or number(row, "establishment_count") <= 0
        for row in context
    ):
        raise ValueError(
            "Geographic comparison needs complete same-year business context"
        )
    if {row["state_key"] for row in context} != {row["state_key"] for row in selected}:
        raise ValueError("Lending and context views need the same state population")
    geography = [
        {
            "key": row["state_key"],
            "label": row["state_name"],
            "amount": number(row, AMOUNT),
            "records": int(row["loan_count"]),
            "establishments": number(row, "establishment_count"),
            "intensity": number(row, "loan_count")
            * 1000
            / number(row, "establishment_count"),
        }
        for row in context
    ]
    programs = group_totals(
        [
            row
            for row in tables["bi_program_mix"]
            if int(row["approval_year"]) == lending_year
        ],
        "loan_program_key",
        "loan_program_name",
    )
    industries_all = [
        row
        for row in tables["bi_industry_mix"]
        if int(row["approval_year"]) == lending_year
    ]
    industries = group_totals(
        [row for row in industries_all if row["is_known_industry"] == "true"],
        "naics_key",
        "naics_sector_name",
    )
    unknown_industry = totals(
        [row for row in industries_all if row["is_known_industry"] != "true"]
    )
    lenders = group_totals(
        [
            row
            for row in tables["bi_lender_mix"]
            if int(row["approval_year"]) == lending_year
        ],
        "lender_key",
        "lender_name",
    )
    for name, grouped in (
        ("program", programs),
        ("industry", group_totals(industries_all, "naics_key", "naics_sector_name")),
    ):
        if sum((row["amount"] for row in grouped), Decimal(0)) != headline["amount"]:
            raise ValueError(f"{name}: dollars do not reconcile with the headline")
        if sum(row["records"] for row in grouped) != headline["records"]:
            raise ValueError(f"{name}: records do not reconcile with the headline")
        if (
            sum(row["known_amount_records"] for row in grouped)
            != headline["known_amount_records"]
        ):
            raise ValueError(
                f"{name}: known amounts do not reconcile with the headline"
            )
    known_industry_amount = sum((row["amount"] for row in industries), Decimal(0))
    if known_industry_amount <= 0:
        raise ValueError("Industry chart needs positive known-industry dollars")
    known_lender_amount = sum((row["amount"] for row in lenders), Decimal(0))
    if known_lender_amount <= 0 or known_lender_amount > headline["amount"]:
        raise ValueError("Known lender dollars outside headline population")
    for row in programs:
        row["share"] = row["amount"] / headline["amount"]
    for row in industries:
        row["share"] = row["amount"] / known_industry_amount
    for row in lenders:
        row["share"] = row["amount"] / known_lender_amount
    sources = []
    for system in ("sba", "census", "bls"):
        rows = [
            row
            for row in tables["bi_source_freshness"]
            if row["source_system"] == system
        ]
        if not rows or len({row["latest_observation_date"] for row in rows}) != 1:
            raise ValueError(f"{system}: missing or inconsistent source coverage")
        if any(row["is_latest_successful_snapshot"] != "true" for row in rows):
            raise ValueError(f"{system}: saved input validity is not established")
        publication_fields = (
            "publication_reference_date",
            "publication_date",
            "publication_verified_date",
            "publication_source_url",
            "publication_cadence",
            "next_scheduled_release_date",
            "publication_status",
        )
        for field in publication_fields:
            if (
                any(field not in row for row in rows)
                or len({row[field] for row in rows}) != 1
            ):
                raise ValueError(
                    f"{system}: missing or inconsistent publication evidence: {field}"
                )
        sources.append(
            {
                "system": system,
                "observation_date": rows[0]["latest_observation_date"],
                "observation_age_days": int(rows[0]["observation_age_days"]),
                "status": sorted({row["freshness_status"] for row in rows}),
                "reasons": sorted({row["freshness_reason"] for row in rows}),
                "download_dates": sorted(
                    {row["latest_extracted_at_utc"][:10] for row in rows}
                ),
                **{field: rows[0][field] for field in publication_fields},
                "resources": len(rows),
            }
        )
    extraction_dates = sorted(
        {row["latest_extracted_at_utc"][:10] for row in tables["bi_source_freshness"]}
    )
    checked_at = {
        row["freshness_checked_at_utc"] for row in tables["bi_source_freshness"]
    }
    if len(checked_at) != 1:
        raise ValueError("Source ages must have one frozen check time")
    return {
        "lending_year": lending_year,
        "context_year": context_year,
        "state_count": len(context),
        "headline": headline,
        "trend": [{"year": year, **totals(rows)} for year, rows in by_year.items()],
        "geography": geography,
        "programs": programs,
        "industries": industries,
        "lenders": lenders,
        "unknown_industry": unknown_industry,
        "industry_coverage": known_industry_amount / headline["amount"],
        "lender_coverage": known_lender_amount / headline["amount"],
        "known_lender_amount": known_lender_amount,
        "known_lender_name_count": len(lenders),
        "unknown_lender_amount": headline["amount"] - known_lender_amount,
        "unknown_lender_records": headline["records"]
        - sum(row["records"] for row in lenders),
        "top_five_lender_share": sum((row["amount"] for row in lenders[:5]), Decimal(0))
        / known_lender_amount,
        "sources": sources,
        "extraction_dates": extraction_dates,
        "freshness_checked_at_utc": checked_at.pop(),
    }


def money(value: Decimal) -> str:
    return f"${value / Decimal(1_000_000_000):,.2f} billion"


def pct(value: Decimal) -> str:
    return f"{value * 100:.2f}%"


def annual_change_phrase(change: Decimal) -> str:
    """Describe the computed signed change without implying positive growth."""
    if change > 0:
        return f"increased by {pct(change)}"
    if change < 0:
        return f"decreased by {pct(-change)}"
    return "were unchanged"


def geography_scope(rows: list[dict]) -> str:
    """Name the actual geography; count alone cannot establish national coverage."""
    with (ROOT / "dbt/seeds/ref_state.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        reference = {row["state_fips"]: row for row in csv.DictReader(stream)}
    keys = {row["key"] for row in rows}
    if not keys:
        return "No project geographies"
    if not keys <= reference.keys():
        return f"{len(keys)} selected project geographies"
    if len(keys) <= 3:
        return "; ".join(
            "Washington, DC" if key == "11" else reference[key]["state_name"]
            for key in sorted(keys)
        )
    state_count = sum(reference[key]["is_state"] == "true" for key in keys)
    scope = f"{state_count} states"
    if "11" in keys:
        scope += " and Washington, DC"
    if keys != reference.keys():
        scope += " (selected)"
    return scope


def selected_period_note(analysis: dict) -> str:
    """Historical complete-year selections must not be called the latest year."""
    return (
        f"Selected complete lending year: {analysis['lending_year']}; "
        f"complete same-year business/labor context: {analysis['context_year']}."
    )


def render_charts(analysis: dict, image_dir: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 11,
            "svg.fonttype": "none",
            "svg.hashsalt": "sba-analysis-report",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.spines.left": False,
            "axes.edgecolor": "#cbd5e0",
            "axes.labelcolor": INK,
            "text.color": INK,
            "xtick.color": INK,
            "ytick.color": INK,
            "figure.facecolor": "white",
        }
    )
    year = analysis["lending_year"]
    context_year = analysis["context_year"]
    snapshot = ", ".join(analysis["extraction_dates"])
    verified = datetime.fromisoformat(analysis["readiness_checked_at_utc"]).strftime(
        "%B %d, %Y"
    )
    frozen = datetime.fromisoformat(analysis["freshness_checked_at_utc"]).strftime(
        "%B %d, %Y"
    )
    footer = f"Saved public data extracted {snapshot}; derived tables verified {verified} UTC."
    scope = geography_scope(analysis["geography"])

    def canvas(title: str, subtitle: str, height: float = 5.5, columns: int = 1):
        fig, axes = plt.subplots(1, columns, figsize=(11, height), squeeze=False)
        wrapped_title = textwrap.fill(title.replace("\n", " "), 78)
        multiline = "\n" in wrapped_title
        fig.text(0.06, 0.94, wrapped_title, fontsize=17, weight="bold", va="top")
        fig.text(
            0.06,
            0.80 if multiline else 0.86,
            "\n".join(textwrap.fill(line, 100) for line in subtitle.splitlines())
            + f"\nGeography: {scope}.",
            fontsize=11,
            va="top",
        )
        fig.subplots_adjust(
            left=0.30 if columns == 1 else 0.19,
            right=0.93,
            top=0.65 if multiline else 0.72,
            bottom=0.29,
            wspace=0.95,
        )
        return fig, list(axes[0])

    def save(
        fig, filename: str, title: str, description: str, note: str, note_top=0.19
    ):
        fig.text(0.06, note_top, note, fontsize=11, va="top")
        fig.text(0.06, 0.025, footer, fontsize=10, color=GRAY)
        path = image_dir / filename
        fig.savefig(
            path,
            format="svg",
            metadata={"Date": None, "Creator": "scripts/render_analysis_report.py"},
        )
        plt.close(fig)
        ET.register_namespace("", SVG_NS)
        tree = ET.parse(path)
        root = tree.getroot()
        root.set("role", "img")
        root.set("aria-labelledby", "chart-title chart-description")
        ET.SubElement(root, f"{{{SVG_NS}}}title", {"id": "chart-title"}).text = title
        ET.SubElement(
            root, f"{{{SVG_NS}}}desc", {"id": "chart-description"}
        ).text = description
        tree.write(path, encoding="utf-8", xml_declaration=True)

    def bars(ax, rows, field, color, unit, formatting, label_width=30):
        labels = [textwrap.fill(row["label"], label_width) for row in rows]
        values = [float(row[field]) for row in rows]
        ax.barh(labels, values, color=color, height=0.62)
        ax.invert_yaxis()
        ax.set_xlim(0, max(values) * 1.25)
        ax.set_xlabel(unit)
        ax.xaxis.set_major_locator(MaxNLocator(4))
        ax.grid(axis="x", alpha=0.14)
        ax.set_axisbelow(True)
        ax.tick_params(axis="y", length=0)
        for idx, row in enumerate(rows):
            ax.text(
                float(row[field]) + max(values) * 0.025,
                idx,
                formatting(row[field]),
                va="center",
                fontsize=11,
            )

    title = f"Reported approval amounts {annual_change_phrase(analysis['headline']['growth'])} in {year}"
    fig, axes = canvas(
        title,
        "How has annual lending activity changed? • Full calendar years",
        height=6,
        columns=2,
    )
    fig.subplots_adjust(left=0.09, wspace=0.40)
    years = [row["year"] for row in analysis["trend"]]
    ticks = sorted(
        set([year for year in years[::2] if year < years[-1] - 1] + [years[-1]])
    )
    for ax, field, scale, color, label, formatting in (
        (
            axes[0],
            "amount",
            1_000_000_000,
            BLUE,
            "Reported amounts ($ billions)",
            money,
        ),
        (
            axes[1],
            "records",
            1000,
            TEAL,
            "Approval records (thousands)",
            lambda value: f"{value:,} records",
        ),
    ):
        ax.plot(
            years,
            [float(row[field] / scale) for row in analysis["trend"]],
            marker="o",
            color=color,
            linewidth=2.5,
        )
        ax.set_ylim(bottom=0)
        ax.set_title(label, loc="left", fontsize=12, pad=14)
        ax.set_xticks(ticks)
        ax.tick_params(axis="x", labelsize=10)
        ax.grid(axis="y", alpha=0.18)
        last = analysis["trend"][-1]
        ax.annotate(
            formatting(last[field]),
            (last["year"], float(last[field] / scale)),
            xytext=(-5, 24),
            textcoords="offset points",
            ha="right",
            weight="bold",
            arrowprops={"arrowstyle": "-", "color": color},
        )
    note = "Source: U.S. Small Business Administration (SBA).\n" + AMOUNT_NOTE
    save(
        fig,
        "lending_findings.svg",
        title,
        "; ".join(
            f"{row['year']}: {money(row['amount'])}, {row['records']:,} approval records"
            for row in analysis["trend"]
        ),
        note,
    )

    title = "Dollar totals and records per business location rank states differently"
    fig, axes = canvas(
        title,
        f"Where is activity concentrated? • Both rankings use {context_year} • Top six in each ranking",
        height=6,
        columns=2,
    )
    fig.subplots_adjust(bottom=0.32)
    amount_rows = sorted(
        analysis["geography"], key=lambda row: (-row["amount"], row["key"])
    )[:6]
    amount_rows = [
        {**row, "billions": row["amount"] / 1_000_000_000} for row in amount_rows
    ]
    intensity_rows = sorted(
        analysis["geography"], key=lambda row: (-row["intensity"], row["key"])
    )[:6]
    bars(
        axes[0],
        amount_rows,
        "billions",
        BLUE,
        "Reported amounts\n($ billions)",
        lambda value: f"${value:.2f}bn",
    )
    bars(
        axes[1],
        intensity_rows,
        "intensity",
        TEAL,
        "Records per 1,000\nemployer locations",
        lambda value: f"{value:.2f}",
    )
    axes[0].set_title("Largest dollar totals", loc="left", fontsize=12, pad=18)
    axes[1].set_title("Highest relative activity", loc="left", fontsize=12, pad=18)
    save(
        fig,
        "lending_geography.svg",
        title,
        f"{context_year}: {amount_rows[0]['label']} leads dollars; {intensity_rows[0]['label']} leads records per 1,000 employer establishments.",
        "Sources: SBA; Census Business Dynamics Statistics (BDS).\n"
        + AMOUNT_NOTE
        + "\nCensus: March 12 employer-location stocks across firm sizes; excludes nonemployers.\n"
        "Context only; not credit access or unmet demand.",
    )

    title = f"{analysis['programs'][0]['label']} accounts for {pct(analysis['programs'][0]['share'])} of reported approval amounts"
    fig, (ax,) = canvas(
        title,
        f"How do the two programs contribute? • {year}",
        height=4.8,
    )
    rows = [{**row, "percent": row["share"] * 100} for row in analysis["programs"]]
    bars(
        ax,
        rows,
        "percent",
        BLUE,
        "Share of all reported approval amounts (%)",
        lambda value: f"{value:.2f}%",
    )
    save(
        fig,
        "lending_programs.svg",
        title,
        "; ".join(
            f"{row['label']}: {money(row['amount'])}, {pct(row['share'])}"
            for row in rows
        ),
        "Source: U.S. Small Business Administration (SBA).\n"
        + AMOUNT_NOTE
        + "\nShares do not measure comparable total financing or SBA risk exposure.",
    )

    title = f"{analysis['industries'][0]['label']} leads known-industry dollars"
    title = textwrap.fill(title, 72)
    fig, (ax,) = canvas(
        title,
        f"Which industries account for the most reported approval amounts? • {year} • Top six known sectors",
        height=6.5,
    )
    fig.subplots_adjust(left=0.36)
    rows = [
        {**row, "percent": row["share"] * 100} for row in analysis["industries"][:6]
    ]
    bars(
        ax,
        rows,
        "percent",
        TEAL,
        "Share of known-industry reported amounts (%)",
        lambda value: f"{value:.2f}%",
        label_width=32,
    )
    save(
        fig,
        "lending_industries.svg",
        title.replace("\n", " "),
        "; ".join(f"{row['label']}: {pct(row['share'])}" for row in rows),
        "Source: SBA; North American Industry Classification System (NAICS) sectors.\n"
        + AMOUNT_NOTE
        + f"\nKnown-industry coverage: {pct(analysis['industry_coverage'])}; unknown/unclassified: {money(analysis['unknown_industry']['amount'])}.\n"
        "Shares use known-sector dollars only; unknown records remain in the overall total.",
    )

    title = f"Five reporting lender names account for {pct(analysis['top_five_lender_share'])} of known-name dollars"
    fig, (ax,) = canvas(
        title,
        f"How concentrated are reported lender assignments? • {year}\nNames ranked by combined amounts across the shown states",
        height=6.5,
    )
    fig.subplots_adjust(left=0.38)
    rows = [
        {**row, "billions": row["amount"] / 1_000_000_000}
        for row in analysis["lenders"][:5]
    ]
    bars(
        ax,
        rows,
        "billions",
        BLUE,
        "Reported approval amounts ($ billions)",
        lambda value: f"${value:.2f}bn",
        label_width=33,
    )
    save(
        fig,
        "lending_lenders.svg",
        title,
        "; ".join(f"{row['label']}: {money(row['amount'])}" for row in rows),
        f"Source: SBA. Known-name coverage: {pct(analysis['lender_coverage'])}; unknown names: {money(analysis['unknown_lender_amount'])}.\n"
        + AMOUNT_NOTE
        + "\n7(a): currently assigned banks; 504: reported third-party lenders.\n"
        "Normalized names do not resolve historical originators or consolidated banking groups.",
    )

    title = "Source recency follows published releases and their reference periods"
    fig, (ax,) = canvas(
        title,
        f"Publication evidence evaluated {frozen} UTC; reference age alone does not mean stale.",
        height=6.8,
    )
    fig.subplots_adjust(left=0.06, right=0.94, top=0.70, bottom=0.32)
    ax.axis("off")
    language = json.loads(LANGUAGE_FILE.read_text(encoding="utf-8"))
    source_labels = {
        "sba": "SBA approval records",
        "census": "Census employer locations",
        "bls": "BLS state unemployment",
    }
    table_rows = [
        [
            textwrap.fill(source_labels[row["system"]], 22),
            source_reference_period(row["system"], row["publication_reference_date"]),
            row["publication_date"] or "Not confirmed",
            "\n".join(row["download_dates"]),
            "\n".join(
                textwrap.fill(language["freshness_reason_labels"][reason], 24)
                for reason in row["reasons"]
            ),
        ]
        for row in analysis["sources"]
    ]
    table = ax.table(
        cellText=table_rows,
        colLabels=[
            "Source",
            "Reference\nperiod",
            "Published on",
            "Downloaded on",
            "Recency assessment",
        ],
        colWidths=[0.23, 0.13, 0.18, 0.18, 0.28],
        cellLoc="left",
        colLoc="left",
        bbox=[0, 0, 1, 1],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(11)
    for (row_index, _), cell in table.get_celld().items():
        cell.set_edgecolor("#e2e8f0")
        cell.set_facecolor("#edf2f7" if row_index == 0 else "white")
        if row_index == 0:
            cell.set_text_props(weight="bold")
    announced = (
        "; ".join(
            f"{source_labels[row['system']]}: {row['next_scheduled_release_date']}"
            for row in analysis["sources"]
            if row["next_scheduled_release_date"]
        )
        or "None verified"
    )
    save(
        fig,
        "lending_coverage.svg",
        title,
        "; ".join(" | ".join(cells).replace("\n", " ") for cells in table_rows),
        "Sources: SBA; Census BDS; BLS Local Area Unemployment Statistics (LAUS).\n"
        + "Next announced release: "
        + announced
        + ".\nPublication dates marked 'Not confirmed' are unknown; coverage cutoffs are not release dates."
        + "\n"
        + selected_period_note(analysis),
        note_top=0.24,
    )


def source_reference_period(system: str, value: str) -> str:
    """Display the publisher reference at its year, quarter or month grain."""
    if not value:
        return "Not established"
    reference = datetime.fromisoformat(value)
    if system == "census":
        return str(reference.year)
    if system == "sba":
        return f"{reference.year} Q{(reference.month - 1) // 3 + 1}"
    return reference.strftime("%Y-%m")


def write_reader_results(analysis: dict, output: Path) -> None:
    """Human-readable aggregates, with exact machine-readable companions."""
    h = analysis["headline"]
    year = analysis["lending_year"]
    lines = [
        "# SBA approval activity: results and source coverage",
        "",
        "These charts and tables describe public SBA approval activity using validated source data.",
        "Read the [case study](case_study.md) for interpretation and the [methodology](kpi_definitions.md) for definitions.",
        "The [public verification record](../images/lending_verification.json) separates prior data validation from chart-generation checks.",
        "",
        "SBA supports business lending through two programs: [7(a)](https://www.sba.gov/loans/7a-loans/)",
        "covers general business uses such as working capital, equipment and real estate;",
        "[504](https://www.sba.gov/loans/504-loans/) supports major fixed assets such as buildings and equipment.",
        "Reported amounts use whole 7(a) loans plus the SBA/Certified Development Company portion of 504 loans.",
        f"The lending population covers **{geography_scope(analysis['geography'])}**: eligible records have a recognized project state and calendar approval date.",
        "BLS labor data is validated for state-level Power BI context. These static charts focus on approvals, employer-location comparisons and source coverage.",
        "",
        f"## How much activity? — {year}",
        "",
        f"The U.S. Small Business Administration (SBA) records **{money(h['amount'])}** in reported nominal approval amounts,",
        f"**{h['records']:,} approval records**. Reported approval amounts **{annual_change_phrase(h['growth'])}** from {year - 1}.",
        f"The average is **${h['average']:,.2f}**, dividing dollars by **{h['known_amount_records']:,} records with known amounts**.",
        "These records include canceled/not-funded approvals; they are not unique borrowers or disbursements.",
        "",
        "![Annual reported approval amounts and approval records](../images/lending_findings.svg)",
        "",
        "| Calendar year | Reported amounts | Approval records |",
        "|---|---:|---:|",
    ]
    lines += [
        f"| {row['year']} | {money(row['amount'])} | {row['records']:,} |"
        for row in analysis["trend"]
    ]
    lines += [
        "",
        f"## Where is it concentrated? — {analysis['context_year']}",
        "",
        "Both rankings use the same calendar year. Employer establishments are business locations with employees,",
        "across firm sizes; they are a contextual denominator rather than the number of eligible small businesses.",
        "",
        "![Dollar and employer-location rankings](../images/lending_geography.svg)",
        "",
        "**Largest reported dollar totals**",
        "",
        "| State | Reported amounts | Approval records |",
        "|---|---:|---:|",
    ]
    for row in sorted(
        analysis["geography"], key=lambda row: (-row["amount"], row["key"])
    )[:6]:
        lines.append(
            f"| {row['label']} | {money(row['amount'])} | {row['records']:,} |"
        )
    lines += [
        "",
        "**Most approval records relative to employer locations**",
        "",
        "| State | Reported amounts | Records per 1,000 employer locations |",
        "|---|---:|---:|",
    ]
    for row in sorted(
        analysis["geography"], key=lambda row: (-row["intensity"], row["key"])
    )[:6]:
        lines.append(
            f"| {row['label']} | {money(row['amount'])} | {row['intensity']:.2f} |"
        )
    lines += [
        "",
        f"## What makes up the total? — {year}",
        "",
        "![Program contribution](../images/lending_programs.svg)",
        "",
        "7(a) reports whole loans; 504 reports the SBA/Certified Development Company portion.",
        "Combined dollars therefore do not measure total project financing or comparable government exposure.",
        "",
        "| Program | Reported amounts | Share of all amounts | Approval records |",
        "|---|---:|---:|---:|",
    ]
    lines += [
        f"| {row['label']} | {money(row['amount'])} | {pct(row['share'])} | {row['records']:,} |"
        for row in analysis["programs"]
    ]
    lines += [
        "",
        "![Known-industry distribution](../images/lending_industries.svg)",
        "",
        f"Known sectors cover **{pct(analysis['industry_coverage'])}** of all reported amounts. Unknown/unclassified sectors contain",
        f"**{money(analysis['unknown_industry']['amount'])}** and **{analysis['unknown_industry']['records']:,} records**.",
        "Sector shares below divide by known-sector dollars, retaining unknown records in the overall total.",
        "",
        "| Industry | Reported amounts | Share of known-industry amounts |",
        "|---|---:|---:|",
    ]
    lines += [
        f"| {row['label']} | {money(row['amount'])} | {pct(row['share'])} |"
        for row in analysis["industries"][:6]
    ]
    lines += [
        "",
        f"## How concentrated are lender assignments? — {year}",
        "",
        "![Top five reporting lender names](../images/lending_lenders.svg)",
        "",
        f"The five largest names account for **{pct(analysis['top_five_lender_share'])}** of known-name dollars after",
        "aggregation across the selected geography. This is different from combining each state's top five.",
        f"Known names cover **{pct(analysis['lender_coverage'])}** of all dollars; unknown names account for",
        f"**{money(analysis['unknown_lender_amount'])}** and **{analysis['unknown_lender_records']:,} records**.",
        "7(a) uses currently assigned bank names; 504 uses reported third-party lender names. These normalized",
        "names do not identify consolidated banking groups or resolve historical originators.",
        "",
        "| Reporting lender name | Reported amounts | Share of known-name amounts |",
        "|---|---:|---:|",
    ]
    lines += [
        f"| {row['label']} | {money(row['amount'])} | {pct(row['share'])} |"
        for row in analysis["lenders"][:5]
    ]
    lines += [
        "",
        "## How current is the evidence?",
        "",
        "![Source reference periods and publications](../images/lending_coverage.svg)",
        "",
        f"Download dates: **{', '.join(analysis['extraction_dates'])}**. Publication and download checks were evaluated on",
        f"**{analysis['freshness_checked_at_utc'][:10]} UTC**. Opening this report later does not update the evidence.",
        "The six reporting files used by these charts match the files verified against modeled tables. Old reference periods alone do not mean stale data.",
        "",
        "| Source | Latest verified published reference | Published on | Publisher checked on | Downloaded on | Recency assessment |",
        "|---|---|---|---|---|---|",
    ]
    language = json.loads(LANGUAGE_FILE.read_text(encoding="utf-8"))
    source_names = language["sources"]
    lines += [
        f"| [{source_names[row['system']]}]({row['publication_source_url']}) | {source_reference_period(row['system'], row['publication_reference_date'])} | {row['publication_date'] or 'Not confirmed'} | {row['publication_verified_date'] or 'Not confirmed'} | {', '.join(row['download_dates'])} | {', '.join(language['freshness_reason_labels'][reason] for reason in row['reasons'])} |"
        for row in analysis["sources"]
    ]
    lines += [
        "",
        "| Source | Publication timing | Next announced release |",
        "|---|---|---|",
    ]
    lines += [
        f"| {source_names[row['system']]} | {language['source_publication_timing'][row['system']]} | {row['next_scheduled_release_date'] or 'Not confirmed'} |"
        for row in analysis["sources"]
    ]
    lines += [
        "",
        "A passed schedule date triggers publisher verification, not an assumed new release.",
        "Unknown publication dates stay unconfirmed; coverage cutoffs and catalog modification dates are not substitutes.",
        "Only a verified newer published period makes saved data stale. Expired checks require verification instead.",
        "",
        "The source endpoints above use separate clocks: SBA calendar approval dates, Census March 12 reference stocks,",
        "and BLS month-end labor observations. October 2025 unemployment data was not published. The 2025 mean of 11 published months",
        "is descriptive but does not support a comparable ordinary annual change.",
        "Census BDS is released annually with a multi-year lag; the latest verified published year can have an old reference date.",
        f"The report uses {year} for lending and {analysis['context_year']} for complete economic context.",
        "",
        "## Reproduction and scope",
        "",
        "Generated by `scripts/render_analysis_report.py` from checked local reporting CSVs.",
        "The companion [aggregate JSON](../images/lending_analysis.json) records exact values and input CSV SHA256 hashes.",
        "The [runtime guide](orchestration_runtime.md#reader-report-and-chart-generation) gives the repeatable generation command.",
        "These are generated data charts, not Power BI screenshots. The manual Power BI report still needs Desktop correction;",
        "paid Snowflake execution remains deferred. Chart generation itself performs no source refresh, warehouse rebuild or borrower-level publication.",
        "",
        "<details>",
        "<summary>Technical reference: frozen observation ages</summary>",
        "",
        f"Exact evaluation time: **{analysis['freshness_checked_at_utc']} UTC**. Ages are descriptive, not stale-data rules.",
        "",
        "| Source | Latest saved observation/reference | Descriptive age at check (days) |",
        "|---|---|---:|",
    ]
    lines += [
        f"| {source_names[row['system']]} | {row['observation_date']} | {row['observation_age_days']} |"
        for row in analysis["sources"]
    ]
    lines += ["", "</details>", ""]
    output.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create an SBA lending story with real charts from verified saved local data."
    )
    parser.add_argument(
        "--export-dir",
        type=Path,
        default=ROOT / "data/exports/powerbi",
        help="Folder of modeled, identifier-free reporting CSVs",
    )
    parser.add_argument(
        "--readiness",
        type=Path,
        default=ROOT / ".tmp/pre-pbix/readiness.json",
        help="Readiness evidence whose CSV hashes must match the inputs",
    )
    parser.add_argument("--image-dir", type=Path, default=ROOT / "docs/images")
    parser.add_argument(
        "--report-path", type=Path, default=ROOT / "docs/detailed/analysis_results.md"
    )
    parser.add_argument(
        "--lending-year",
        type=int,
        default=2025,
        help="Complete calendar year for lending results",
    )
    parser.add_argument(
        "--context-year",
        type=int,
        default=2023,
        help="Complete year shared by lending, business and labor data",
    )
    parser.add_argument(
        "--start-year",
        type=int,
        default=2016,
        help="First complete calendar year shown in the trend",
    )
    args = parser.parse_args()
    tables, evidence = read_checked_exports(args.export_dir, args.readiness)
    analysis = build_analysis(
        tables, args.lending_year, args.context_year, args.start_year
    )
    analysis["input_csv_sha256"] = {
        table: evidence["csv_checks"][table]["sha256"] for table in TABLES
    }
    analysis["readiness_checked_at_utc"] = evidence["checked_at_utc"]
    analysis["report_language_sha256"] = text_checksum(LANGUAGE_FILE)
    analysis["report_language_hash_encoding"] = "UTF-8 with LF line endings"
    args.image_dir.mkdir(parents=True, exist_ok=True)
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    render_charts(analysis, args.image_dir)
    published = {**analysis, "lenders": analysis["lenders"][:5]}
    (args.image_dir / "lending_analysis.json").write_text(
        json.dumps(published, indent=2, default=str) + "\n", encoding="utf-8"
    )
    write_reader_results(analysis, args.report_path)
    outputs = {
        f"lending_{name}.svg": args.image_dir / f"lending_{name}.svg"
        for name in CHART_NAMES
    }
    outputs["lending_analysis.json"] = args.image_dir / "lending_analysis.json"
    outputs["analysis_results.md"] = args.report_path
    (args.image_dir / "lending_verification.json").write_text(
        json.dumps(public_verification(evidence, outputs), indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Published six SBA lending charts and {args.report_path}. Inputs: verified saved CSVs; no source refresh."
    )


if __name__ == "__main__":
    main()
