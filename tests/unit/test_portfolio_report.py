"""Check the report's evidence boundary, portability and offline reading path."""

import base64
from html.parser import HTMLParser
import json
import shutil

import pytest

from scripts.render_portfolio_report import ROOT, render, sha, text


@pytest.fixture
def report_root(tmp_path):
    root = tmp_path / "checkout"
    for relative in (
        "docs/images",
        "scripts/portfolio",
    ):
        shutil.copytree(ROOT / relative, root / relative)
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
        if source.is_file():
            source.write_bytes(text(source).replace("\n", "\r\n").encode("utf-8"))
    render(report_root, second)
    for filename in ("index.html", "provenance.json"):
        assert (first / filename).read_bytes() == (second / filename).read_bytes()
    provenance = json.loads(text(first / "provenance.json"))
    html = text(first / "index.html")
    assert provenance["outputs"]["index.html"]["sha256"] == sha(html)
    assert provenance["outputs"]["index.html"]["bytes"] == len(html.encode("utf-8"))
    assert "not rerun" in provenance["scope"]
    assert set(p.name for p in first.iterdir()) == {"index.html", "provenance.json"}
    assert sum(p.stat().st_size for p in first.iterdir()) < 500_000


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
            assert link.startswith(("https://", "data:")) or link == "provenance.json"
    charts = [image for image in parsed.images if image.get("src")]
    assert len(charts) == 6
    for image in charts:
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
    for filename in ("index.html", "provenance.json"):
        assert text(tmp_path / "report" / filename) == text(
            ROOT / "reports/portfolio" / filename
        )
