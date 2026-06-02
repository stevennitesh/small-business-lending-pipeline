from __future__ import annotations

from scripts import cleanup_local_data as cleanup


def test_cleanup_candidates_preserve_configured_sba_run(tmp_path):
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
    keep_run = tmp_path / "data" / "raw" / "sba" / "7a_foia" / "pipeline_run_id=keep-me"
    old_run = tmp_path / "data" / "raw" / "sba" / "7a_foia" / "pipeline_run_id=old-run"

    keep_run.mkdir(parents=True)
    old_run.mkdir()
    (keep_run / "current.csv").write_text("current")
    (old_run / "old.csv").write_text("old")

    candidates = cleanup.find_candidates(root=tmp_path, keep_pipeline_run_id="keep-me")
    cleanup.apply_cleanup(candidates)

    assert keep_run.exists()
    assert not old_run.exists()
