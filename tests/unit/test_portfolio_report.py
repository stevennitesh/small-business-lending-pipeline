"""Check the report's evidence boundary, portability and offline reading path."""

import base64
from html.parser import HTMLParser
import json
import shutil
import xml.etree.ElementTree as ET

import pytest

from scripts.render_portfolio_report import ROOT, render, sha, text
from scripts.portfolio.mobile_charts import mobile_charts


@pytest.fixture
def report_root(tmp_path):
    root = tmp_path / "checkout"
    for relative in (
        "docs/images",
        "scripts/portfolio",
    ):
        shutil.copytree(
            ROOT / relative,
            root / relative,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
    for relative in (
        "docs/detailed/analysis_results.md",
        "scripts/render_portfolio_report.py",
        "powerbi/report_language.json",
    ):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    return root


class ReportParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.links = []
        self.images = []
        self.scripts = []

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if tag == "a":
            self.links.append(attrs.get("href", ""))
        if tag == "img":
            self.images.append(attrs)
        if tag == "script":
            self.scripts.append(attrs)


def test_report_is_deterministic_from_a_small_public_checkout(report_root, tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    render(report_root, first)
    # Windows Git checkouts may use CRLF; the published text hashes normalize LF.
    for source in report_root.rglob("*"):
        if source.is_file() and source.suffix in {
            ".py",
            ".json",
            ".html",
            ".css",
            ".js",
            ".md",
            ".svg",
        }:
            source.write_bytes(text(source).replace("\n", "\r\n").encode("utf-8"))
    render(report_root, second)
    for filename in ("index.html", "offline.html", "provenance.json"):
        assert (first / filename).read_bytes() == (second / filename).read_bytes()
    provenance = json.loads(text(first / "provenance.json"))
    html = text(first / "index.html")
    assert provenance["outputs"]["index.html"]["sha256"] == sha(html)
    assert provenance["outputs"]["index.html"]["bytes"] == len(html.encode("utf-8"))
    assert "not rerun" in provenance["scope"]
    assert set(p.name for p in first.iterdir()) == {
        "index.html",
        "offline.html",
        "provenance.json",
        "assets",
    }
    assert (first / "index.html").stat().st_size < 500_000
    for filename, metadata in provenance["outputs"].items():
        import hashlib

        assert (
            hashlib.sha256((first / filename).read_bytes()).hexdigest()
            == metadata["sha256"]
        )


@pytest.mark.parametrize("filename", ["lending_analysis.json", "lending_geography.svg"])
def test_changed_evidence_fails_before_replacing_the_report(
    report_root, tmp_path, filename
):
    output = tmp_path / "report"
    output.mkdir()
    (output / "index.html").write_text("Previous report", encoding="utf-8")
    changed = report_root / "docs/images" / filename
    changed.write_text(text(changed) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        render(report_root, output)
    assert text(output / "index.html") == "Previous report"
    assert not (output / "provenance.json").exists()


def test_report_rejects_crossed_readiness_and_csv_proof(report_root, tmp_path):
    proof_path = report_root / "docs/images/lending_verification.json"
    proof = json.loads(text(proof_path))
    proof["chart_generation_checks"]["inputs"]["bi_program_mix"]["sha256"] = "0" * 64
    proof_path.write_text(json.dumps(proof), encoding="utf-8")
    with pytest.raises(ValueError, match="different CSV inputs"):
        render(report_root, tmp_path / "report")
    proof["chart_generation_checks"]["inputs"]["bi_program_mix"]["sha256"] = json.loads(
        text(ROOT / "docs/images/lending_verification.json")
    )["chart_generation_checks"]["inputs"]["bi_program_mix"]["sha256"]
    proof["recorded_readiness"]["checked_at_utc"] = "2020-01-01T00:00:00Z"
    proof_path.write_text(json.dumps(proof), encoding="utf-8")
    with pytest.raises(ValueError, match="different readiness checks"):
        render(report_root, tmp_path / "report")


def test_recency_uses_owned_reasons_including_download_review(report_root, tmp_path):
    aggregate_path = report_root / "docs/images/lending_analysis.json"
    proof_path = report_root / "docs/images/lending_verification.json"
    a = json.loads(text(aggregate_path))
    a["sources"][0]["publication_status"] = "newer_release_available"
    a["sources"][0]["status"] = ["stale"]
    a["sources"][0]["reasons"] = ["newer_release_available"]
    # A published period can match while the local download review is due.
    a["sources"][1]["status"] = ["unknown"]
    a["sources"][1]["reasons"] = ["download_review_due"]
    aggregate_path.write_text(json.dumps(a), encoding="utf-8")
    proof = json.loads(text(proof_path))
    proof["public_outputs"]["lending_analysis.json"]["sha256"] = sha(
        text(aggregate_path)
    )
    proof_path.write_text(json.dumps(proof), encoding="utf-8")
    render(report_root, tmp_path / "report")
    html = text(tmp_path / "report/index.html")
    assert "Newer published period available" in html
    assert "Saved download review due" in html
    language_path = report_root / "powerbi/report_language.json"
    language_path.write_text(text(language_path) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="vocabulary differs"):
        render(report_root, tmp_path / "report")


def test_offline_charts_downloads_and_fragment_links_are_complete(
    report_root, tmp_path
):
    render(report_root, tmp_path / "report")
    parsed = ReportParser()
    parsed.feed(text(tmp_path / "report/index.html"))
    assert len(parsed.ids) == len(set(parsed.ids))
    for link in parsed.links:
        if link.startswith("#"):
            assert link[1:] in parsed.ids
        else:
            assert link.startswith(("https://", "data:", "assets/")) or link in {
                "provenance.json",
                "offline.html",
            }
    charts = [image for image in parsed.images if image.get("src")]
    assert len(charts) == 13
    for image in charts[:6]:
        assert image["alt"]
        assert image["src"].startswith("data:image/svg+xml;base64,")
        svg = base64.b64decode(image["src"].split(",", 1)[1]).decode("utf-8")
        assert "<svg" in svg
    assert all("src" not in attrs for attrs in parsed.scripts)
    downloads = [
        link for link in parsed.links if link.startswith("data:application/json")
    ]
    assert len(downloads) == 2
    aggregate = json.loads(base64.b64decode(downloads[0].split(",", 1)[1]))
    assert aggregate == json.loads(
        text(report_root / "docs/images/lending_analysis.json")
    )


def test_public_desktop_gallery_is_complete_and_offline_copy_embeds_the_same_captures(
    report_root, tmp_path
):
    output = tmp_path / "report"
    render(report_root, output)
    gallery = json.loads(text(report_root / "scripts/portfolio/desktop-gallery.json"))
    offline = ReportParser()
    offline.feed(text(output / "offline.html"))
    captures = [
        image
        for image in offline.images
        if image.get("src", "").startswith("data:image/png")
    ]
    assert len(captures) == len(gallery) == 7
    for item, capture in zip(gallery, captures):
        expected = (report_root / "docs/images/powerbi" / item["file"]).read_bytes()
        assert (output / "assets" / item["file"]).read_bytes() == expected
        assert base64.b64decode(capture["src"].split(",", 1)[1]) == expected
    assert "California" in captures[5]["alt"]


def test_narrow_charts_preserve_selected_values_rankings_and_periods(report_root):
    analysis = json.loads(text(report_root / "docs/images/lending_analysis.json"))
    charts = mobile_charts(
        analysis, json.loads(text(report_root / "powerbi/report_language.json"))
    )
    ns = {"svg": "http://www.w3.org/2000/svg"}
    for svg in charts.values():
        root = ET.fromstring(svg)
        assert root.attrib["viewBox"].split()[2] == "360"
        assert root.find("svg:title", ns).text
    findings = ET.fromstring(charts["findings"])
    assert len(findings.findall(".//svg:circle", ns)) == len(analysis["trend"]) * 2
    assert "2016–2025" in charts["findings"]
    assert "$40.93bn" in charts["findings"]
    assert "74.10k" in charts["findings"]
    assert "82.33%" in charts["programs"] and "17.67%" in charts["programs"]
    assert charts["geography"].index("California") < charts["geography"].index("Texas")
    assert "2023" in charts["geography"]
    assert "Not confirmed" in charts["coverage"]


def test_labels_are_escaped_and_unsupported_growth_is_not_presented(
    report_root, tmp_path
):
    aggregate_path = report_root / "docs/images/lending_analysis.json"
    proof_path = report_root / "docs/images/lending_verification.json"
    a = json.loads(text(aggregate_path))
    a["industries"][0]["label"] = '<script>alert("sector")</script>'
    aggregate_path.write_text(json.dumps(a), encoding="utf-8")
    proof = json.loads(text(proof_path))
    proof["public_outputs"]["lending_analysis.json"]["sha256"] = sha(
        text(aggregate_path)
    )
    proof_path.write_text(json.dumps(proof), encoding="utf-8")
    render(report_root, tmp_path / "report")
    html = text(tmp_path / "report/index.html")
    assert '<script>alert("sector")</script>' not in html
    assert "&lt;script&gt;alert(&quot;sector&quot;)&lt;/script&gt;" in html
    a["headline"]["growth"] = None
    aggregate_path.write_text(json.dumps(a), encoding="utf-8")
    proof["public_outputs"]["lending_analysis.json"]["sha256"] = sha(
        text(aggregate_path)
    )
    proof_path.write_text(json.dumps(proof), encoding="utf-8")
    with pytest.raises(ValueError, match="supported comparable annual change"):
        render(report_root, tmp_path / "report")


def test_checked_in_report_matches_its_current_inputs(tmp_path):
    render(ROOT, tmp_path / "report")
    for filename in ("index.html", "offline.html", "provenance.json"):
        assert text(tmp_path / "report" / filename) == text(
            ROOT / "reports/portfolio" / filename
        )
