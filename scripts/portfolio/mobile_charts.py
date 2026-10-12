"""Render narrow-screen SVG views from the report's verified saved aggregates.

Only layout and display rounding are applied here. The canonical desktop charts,
source populations and exact downloadable values retain their existing owners.
"""

from decimal import Decimal
from html import escape
import math
import textwrap


WIDTH = 360
INK, MUTED, TEAL, BLUE = "#19323c", "#526571", "#14545c", "#21618c"


def label(value, x, y, *, size=20, fill=INK, anchor="start", bold=False):
    weight = ' font-weight="700"' if bold else ""
    return (
        f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" fill="{fill}" '
        f'text-anchor="{anchor}"{weight}>{escape(str(value))}</text>'
    )


def wrapped(value, y, *, width=29, size=20, bold=False, fill=INK):
    parts = []
    for line in textwrap.wrap(value, width=width):
        parts.append(label(line, 18, y, size=size, bold=bold, fill=fill))
        y += size * 1.3
    return "".join(parts), y


def document(parts, height, title):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="360" height="{height:.0f}" '
        f'viewBox="0 0 360 {height:.0f}" role="img" aria-labelledby="title">'
        f'<title id="title">{escape(title)}</title><rect width="100%" height="100%" fill="white"/>'
        '<g font-family="system-ui, sans-serif">' + "".join(parts) + "</g></svg>"
    )


def bar_panel(rows, field, title, unit, formatting, *, start=18, maximum=None):
    parts = []
    heading, y = wrapped(title, start + 22, size=22, bold=True, width=27)
    parts.append(heading)
    values = [float(Decimal(str(row[field]))) for row in rows]
    ceiling = maximum or max(values) * 1.1
    for index, (row, value) in enumerate(zip(rows, values)):
        name, y = wrapped(row["label"], y + 16, size=20)
        parts.append(name)
        parts.append(
            f'<rect x="18" y="{y:.2f}" width="{232 * value / ceiling:.2f}" '
            f'height="20" rx="2" fill="{TEAL if index == 0 else "#658b9c"}"/>'
        )
        parts.append(
            label(formatting(row[field]), 342, y + 17, size=19, anchor="end", bold=True)
        )
        y += 39
    y += 7
    parts.append(f'<path d="M18 {y:.2f}H250" stroke="#b9cecc"/>')
    for fraction in (0, 0.5, 1):
        parts.append(
            label(
                f"{ceiling * fraction:g}",
                18 + fraction * 232,
                y + 24,
                size=18,
                anchor="start"
                if fraction == 0
                else "end"
                if fraction == 1
                else "middle",
                fill=MUTED,
            )
        )
    unit_text, y = wrapped(unit, y + 55, size=19, fill=MUTED)
    parts.append(unit_text)
    return parts, y + 16


def line_panel(rows, field, title, scale, formatting, *, start=18):
    parts = []
    heading, y = wrapped(title, start + 22, size=22, bold=True, width=27)
    parts.append(heading)
    y += 12
    years = [row["year"] for row in rows]
    values = [float(Decimal(str(row[field])) / scale) for row in rows]
    maximum = math.ceil(max(values) / 10) * 10
    left, top, width, height = 58, y, 278, 215
    for fraction in (0, 0.5, 1):
        py = top + height * (1 - fraction)
        parts.append(f'<path d="M{left} {py:.2f}H{left + width}" stroke="#e0e8eb"/>')
        parts.append(
            label(
                f"{maximum * fraction:g}",
                left - 9,
                py + 6,
                size=18,
                anchor="end",
                fill=MUTED,
            )
        )
    points = [
        (
            left + width * (year - years[0]) / (years[-1] - years[0]),
            top + height * (1 - value / maximum),
        )
        for year, value in zip(years, values)
    ]
    parts.append(
        '<polyline fill="none" stroke="'
        + TEAL
        + '" stroke-width="3" points="'
        + " ".join(f"{x:.2f},{py:.2f}" for x, py in points)
        + '"/>'
    )
    for x, py in points:
        parts.append(f'<circle cx="{x:.2f}" cy="{py:.2f}" r="4" fill="{TEAL}"/>')
    for index in (0, len(years) // 2, len(years) - 1):
        parts.append(
            label(
                years[index],
                points[index][0],
                top + height + 28,
                size=19,
                anchor="start"
                if index == 0
                else "end"
                if index == len(years) - 1
                else "middle",
                fill=MUTED,
            )
        )
    parts.append(
        label(
            formatting(rows[-1][field]),
            334,
            points[-1][1] - 12,
            size=20,
            anchor="end",
            bold=True,
        )
    )
    return parts, top + height + 65


def mobile_charts(analysis, language):
    """Return six complete, deterministic narrow-screen charts."""
    charts = {}
    year, context = analysis["lending_year"], analysis["context_year"]

    def percent(value):
        return f"{Decimal(str(value)) * 100:.2f}%"

    def billions(value):
        return f"${Decimal(str(value)) / Decimal(10**9):.2f}bn"

    parts, y = line_panel(
        analysis["trend"],
        "amount",
        "Reported amounts ($ billions)",
        Decimal(10**9),
        billions,
    )
    second, y = line_panel(
        analysis["trend"],
        "records",
        "Approval records (thousands)",
        Decimal(1000),
        lambda n: f"{Decimal(n) / 1000:.2f}k",
        start=y,
    )
    charts["findings"] = document(
        parts + second,
        y,
        f"Annual approval activity, {analysis['trend'][0]['year']}–{year}",
    )
    # Display bars in billions; the exact stored amounts are unchanged.
    rows = [
        {**row, "billions": str(Decimal(row["amount"]) / Decimal(10**9))}
        for row in sorted(
            analysis["geography"], key=lambda r: (-Decimal(r["amount"]), r["key"])
        )[:6]
    ]
    parts, y = bar_panel(
        rows,
        "billions",
        f"Largest dollar totals · {context}",
        "Reported amounts ($ billions)",
        lambda v: f"${Decimal(v):.2f}bn",
        maximum=math.ceil(max(Decimal(r["billions"]) for r in rows)),
    )
    second, y = bar_panel(
        sorted(
            analysis["geography"], key=lambda r: (-Decimal(r["intensity"]), r["key"])
        )[:6],
        "intensity",
        f"Most records per location · {context}",
        "Records per 1,000 employer locations",
        lambda v: f"{Decimal(v):.2f}",
        start=y,
        maximum=math.ceil(
            max(Decimal(r["intensity"]) for r in analysis["geography"]) / 5
        )
        * 5,
    )
    charts["geography"] = document(
        parts + second, y, f"Two state comparisons, {context}; top six in each ranking"
    )
    rows = [
        {**r, "percent": str(Decimal(r["share"]) * 100)} for r in analysis["programs"]
    ]
    parts, y = bar_panel(
        rows,
        "percent",
        f"Program shares · {year}",
        "Share of all reported amounts (%)",
        lambda v: f"{Decimal(v):.2f}%",
        maximum=100,
    )
    charts["programs"] = document(parts, y, f"Program contribution, {year}")
    rows = [
        {**r, "percent": str(Decimal(r["share"]) * 100)}
        for r in analysis["industries"][:6]
    ]
    parts, y = bar_panel(
        rows,
        "percent",
        f"Leading known industries · {year}",
        "Share of known-sector amounts (%)",
        lambda v: f"{Decimal(v):.2f}%",
        maximum=math.ceil(max(Decimal(r["percent"]) for r in rows) / 5) * 5,
    )
    charts["industries"] = document(
        parts,
        y,
        f"Top six known sectors, {year}; known-sector coverage {percent(analysis['industry_coverage'])}",
    )
    rows = [
        {**r, "billions": str(Decimal(r["amount"]) / Decimal(10**9))}
        for r in analysis["lenders"][:5]
    ]
    parts, y = bar_panel(
        rows,
        "billions",
        f"Largest reporting lender names · {year}",
        "Reported amounts ($ billions)",
        lambda v: f"${Decimal(v):.2f}bn",
        maximum=math.ceil(max(Decimal(r["billions"]) for r in rows)),
    )
    charts["lenders"] = document(
        parts,
        y,
        f"Five largest reporting names, {year}; known-name coverage {percent(analysis['lender_coverage'])}",
    )
    parts, y = [], 18
    names = {
        "sba": "SBA approval records",
        "census": "Census employer locations",
        "bls": "BLS state unemployment",
    }
    for row in analysis["sources"]:
        heading, y = wrapped(names[row["system"]], y + 22, size=22, bold=True, width=27)
        parts.append(heading)
        period = row["publication_reference_date"]
        if row["system"] == "sba":
            period = f"{period[:4]} Q{(int(period[5:7]) - 1) // 3 + 1}"
        elif row["system"] == "census":
            period = period[:4]
        else:
            period = period[:7]
        for line in (
            f"Reference: {period}",
            f"Published: {row['publication_date'] or 'Not confirmed'}",
            f"Checked: {row['publication_verified_date']}",
            "Assessment: "
            + "; ".join(language["freshness_reason_labels"][r] for r in row["reasons"]),
        ):
            value, y = wrapped(line, y + 8, size=20, fill=MUTED)
            parts.append(value)
        y += 24
        parts.append(f'<path d="M18 {y - 10:.2f}H342" stroke="#dce5e6"/>')
    charts["coverage"] = document(
        parts,
        y,
        "Source reference periods and publication dates; frozen publication evidence",
    )
    return charts
