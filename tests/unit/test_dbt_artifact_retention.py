"""Protect run receipts while enforcing both count and byte retention limits."""

import hashlib
import json
import os
from pathlib import Path

import pytest

from pipelines.storage import dbt_artifacts as evidence


def _target(tmp_path, invocation="run", padding=0):
    target = tmp_path / "target"
    target.mkdir(exist_ok=True)
    (target / "manifest.json").write_text(json.dumps({"padding": "x" * padding}))
    (target / "run_results.json").write_text(
        json.dumps(
            {
                "metadata": {"invocation_id": invocation},
                "results": [{"status": "pass"}, {"status": "success"}],
            }
        )
    )
    return target


def test_fourth_collection_expires_only_oldest_pair_and_keeps_receipt_and_summary(
    tmp_path,
):
    validation = tmp_path / "validation"
    target = _target(tmp_path)
    first = validation / "pipeline_run_id=0"
    expected = hashlib.sha256((target / "manifest.json").read_bytes()).hexdigest()
    for number in range(4):
        run = validation / f"pipeline_run_id={number}"
        evidence.retain_dbt_artifacts(target, run)
        (run / "run_summary.json").write_text('{"status": "success"}')
        receipt = run / evidence.DBT_RECEIPT_NAME
        os.utime(receipt, ns=(number + 1, number + 1))
    assert not (first / "dbt_artifacts").exists()
    assert (first / "run_summary.json").is_file()
    receipt = json.loads((first / evidence.DBT_RECEIPT_NAME).read_text())
    assert receipt["full_artifacts_retained"] is False
    assert receipt["artifacts"]["manifest.json"]["sha256"] == expected
    assert receipt["result_status_counts"] == {"pass": 1, "success": 1}
    assert len(list(validation.glob("*/dbt_artifacts"))) == 3


def test_byte_budget_can_keep_fewer_than_three_pairs_without_deleting_other_files(
    tmp_path,
):
    validation = tmp_path / "validation"
    target = _target(tmp_path, padding=100)
    runs = []
    for number in range(3):
        run = validation / f"pipeline_run_id={number}"
        evidence.retain_dbt_artifacts(target, run)
        os.utime(run / evidence.DBT_RECEIPT_NAME, ns=(number + 1, number + 1))
        runs.append(run)
    unknown = runs[0] / "dbt_artifacts" / "review-note.txt"
    unknown.write_text("keep")
    pair_size = sum(p.stat().st_size for p in (runs[-1] / "dbt_artifacts").iterdir())
    assert evidence.expired_dbt_artifact_dirs(validation, max_bytes=pair_size * 2) == [
        runs[0] / "dbt_artifacts"
    ]
    evidence.prune_dbt_artifacts(validation, max_bytes=pair_size * 2)
    assert unknown.read_text() == "keep"
    assert all((p / "dbt_artifacts" / "manifest.json").exists() for p in runs[1:])


def test_oversized_pair_fails_before_copying_or_pruning_existing_history(
    tmp_path, monkeypatch
):
    validation = tmp_path / "validation"
    target = _target(tmp_path)
    previous = validation / "pipeline_run_id=previous"
    evidence.retain_dbt_artifacts(target, previous)
    monkeypatch.setattr(evidence, "MAX_DBT_ARTIFACT_BYTES", 1)
    current = validation / "pipeline_run_id=current"
    with pytest.raises(RuntimeError, match="20 MiB"):
        evidence.retain_dbt_artifacts(target, current)
    assert not current.exists()
    assert (previous / "dbt_artifacts" / "manifest.json").is_file()


def test_legacy_pair_gets_a_receipt_before_expiry(tmp_path):
    validation = tmp_path / "validation"
    target = _target(tmp_path)
    oldest = validation / "pipeline_run_id=old"
    oldest.mkdir(parents=True)
    target.rename(oldest / "dbt_artifacts")
    evidence.prune_dbt_artifacts(validation, max_bytes=1)
    receipt = json.loads((oldest / evidence.DBT_RECEIPT_NAME).read_text())
    assert receipt["full_artifacts_retained"] is False
    assert receipt["invocation_id"] == "run"
    assert receipt["result_status_counts"]["pass"] == 1
    assert not (oldest / "dbt_artifacts").exists()


def test_redirected_history_is_rejected_without_touching_target(tmp_path):
    validation = tmp_path / "validation"
    run = validation / "pipeline_run_id=redirected"
    run.mkdir(parents=True)
    target = _target(tmp_path)
    (run / "dbt_artifacts").symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="Redirected"):
        evidence.prune_dbt_artifacts(validation)
    assert (target / "manifest.json").is_file()


def test_current_pair_survives_future_timestamps_on_previous_receipts(tmp_path):
    target = _target(tmp_path)
    validation = tmp_path / "validation"
    for number in range(3):
        run = validation / f"pipeline_run_id={number}"
        evidence.retain_dbt_artifacts(target, run)
        os.utime(
            run / evidence.DBT_RECEIPT_NAME,
            ns=(2_000_000_000_000_000_000 + number,) * 2,
        )
    current = validation / "pipeline_run_id=current"
    paths = evidence.retain_dbt_artifacts(target, current)
    assert all(Path(path).is_file() for path in paths.values())
    assert len(list(validation.glob("*/dbt_artifacts"))) == 3


def test_partial_expiry_cannot_report_the_full_pair_as_retained(tmp_path, monkeypatch):
    target = _target(tmp_path)
    run = tmp_path / "validation" / "pipeline_run_id=locked"
    evidence.retain_dbt_artifacts(target, run)
    unlink = Path.unlink

    def fail_on_results(path, *args, **kwargs):
        if path.name == "run_results.json":
            raise PermissionError("locked results")
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_on_results)
    with pytest.raises(PermissionError, match="locked"):
        evidence.expire_dbt_artifacts(run / "dbt_artifacts")
    receipt = json.loads((run / evidence.DBT_RECEIPT_NAME).read_text())
    assert receipt["full_artifacts_retained"] is False
    assert "pruned_at_utc" not in receipt
    assert (run / "dbt_artifacts" / "run_results.json").is_file()
