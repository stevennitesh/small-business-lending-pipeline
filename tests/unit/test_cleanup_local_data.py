from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from scripts import cleanup_local_data as cleanup


def test_cleanup_candidates_preserve_configured_sba_run(tmp_path):
    """Validate that cleanup candidates preserve configured SBA run."""
    keep_run = (
        tmp_path
        / "data"
        / "raw"
        / "sba"
        / "7a_foia"
        / "source_period=fy2020_present"
        / "ingestion_date=2026-05-14"
        / "pipeline_run_id=keep-me"
    )
    old_run = keep_run.parent / "pipeline_run_id=old-run"
    temp_dir = tmp_path / "data" / "warehouse" / "small_business_lending.duckdb.tmp"

    keep_run.mkdir(parents=True)
    old_run.mkdir()
    temp_dir.mkdir(parents=True)
    (keep_run / "current.csv").write_text("current")
    (old_run / "old.csv").write_text("old")
    (temp_dir / "duckdb_temp_storage_DEFAULT-0.tmp").write_text("temp")

    candidates = cleanup.find_candidates(root=tmp_path, keep_pipeline_run_id="keep-me")
    candidate_paths = {candidate.path for candidate in candidates}

    assert keep_run not in candidate_paths
    assert old_run in candidate_paths
    assert temp_dir in candidate_paths


def test_apply_cleanup_removes_only_candidates(tmp_path):
    """Validate that apply cleanup removes only candidates."""
    keep_run = tmp_path / "data" / "raw" / "sba" / "7a_foia" / "pipeline_run_id=keep-me"
    old_run = tmp_path / "data" / "raw" / "sba" / "7a_foia" / "pipeline_run_id=old-run"

    keep_run.mkdir(parents=True)
    old_run.mkdir()
    (keep_run / "current.csv").write_text("current")
    (old_run / "old.csv").write_text("old")

    candidates = cleanup.find_candidates(root=tmp_path, keep_pipeline_run_id="keep-me")
    cleanup.apply_cleanup(candidates, root=tmp_path)

    assert keep_run.exists()
    assert not old_run.exists()


def test_explicit_verification_cleanup_removes_derived_files_and_keeps_evidence(
    tmp_path,
):
    verification = tmp_path / ".tmp" / "review"
    (verification / "exports").mkdir(parents=True)
    warehouse = verification / "warehouse.duckdb"
    export = verification / "exports" / "bi_executive_overview.csv"
    keep = [
        verification / "findings.json",
        verification / "run_summary.json",
        verification / "source.csv",
    ]
    for p in [warehouse, export, *keep]:
        p.write_text("evidence")
    artifacts = (
        verification
        / "data"
        / "validation"
        / "pipeline_run_id=review"
        / "dbt_artifacts"
    )
    artifacts.mkdir(parents=True)
    (artifacts / "manifest.json").write_text("{}")
    (artifacts / "run_results.json").write_text(
        json.dumps(
            {"metadata": {"invocation_id": "review"}, "results": [{"status": "pass"}]}
        )
    )
    note = artifacts / "review-note.txt"
    note.write_text("keep")
    active = tmp_path / "data" / "warehouse" / "active.duckdb"
    active.parent.mkdir(parents=True)
    active.write_text("active")
    candidates = cleanup.find_verification_candidates(tmp_path, [".tmp/review"])
    assert {c.path for c in candidates} == {warehouse, export, artifacts}
    receipt_path = cleanup.write_cleanup_receipt(candidates, tmp_path)
    cleanup.apply_cleanup(candidates, root=tmp_path)
    assert all(p.is_file() for p in [active, *keep, receipt_path, note])
    assert not warehouse.exists() and not export.exists()
    assert not (artifacts / "manifest.json").exists()
    dbt_receipt = json.loads(
        (artifacts.parent / "dbt_artifact_receipt.json").read_text()
    )
    assert dbt_receipt["full_artifacts_retained"] is False
    assert dbt_receipt["invocation_id"] == "review"
    assert dbt_receipt["result_status_counts"] == {"pass": 1}
    receipt = json.loads(receipt_path.read_text())
    assert len(receipt["candidate_files"]) == 4
    assert all(len(item["sha256"]) == 64 for item in receipt["candidate_files"])


@pytest.mark.parametrize("directory", ["data", ".tmp", "../outside"])
def test_verification_scope_refuses_active_root_or_outside_folder(tmp_path, directory):
    with pytest.raises(ValueError, match="inside .tmp"):
        cleanup.find_verification_candidates(tmp_path, [directory])


def test_apply_checks_all_target_bounds_before_deleting_anything(tmp_path):
    allowed = tmp_path / ".tmp" / "review" / "warehouse.duckdb"
    allowed.parent.mkdir(parents=True)
    allowed.write_text("copy")
    protected = tmp_path / "README.md"
    protected.write_text("protected")
    candidates = [
        cleanup.CleanupCandidate(p, "test", p.stat().st_size)
        for p in [allowed, protected]
    ]
    with pytest.raises(ValueError, match="outside generated"):
        cleanup.apply_cleanup(candidates, root=tmp_path)
    assert allowed.is_file() and protected.is_file()


def test_failed_cleanup_does_not_mark_the_receipt_completed(tmp_path, monkeypatch):
    verification = tmp_path / ".tmp" / "review"
    verification.mkdir(parents=True)
    warehouse = verification / "warehouse.duckdb"
    warehouse.write_text("copy")
    monkeypatch.setattr(cleanup, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        cleanup,
        "parse_args",
        lambda: SimpleNamespace(
            run_evidence_only=False,
            verification_dir=[".tmp/review"],
            apply=True,
        ),
    )

    def fail_delete(*args, **kwargs):
        raise PermissionError("locked warehouse")

    monkeypatch.setattr(cleanup, "apply_cleanup", fail_delete)
    with pytest.raises(PermissionError, match="locked"):
        cleanup.main()
    receipt_path = next(
        (tmp_path / "data" / "validation").glob("verification_cleanup_*.json")
    )
    receipt = json.loads(receipt_path.read_text())
    assert receipt["status"] == "planned"
    assert "completed_at_utc" not in receipt
    assert warehouse.is_file()
