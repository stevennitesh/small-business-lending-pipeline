"""A later dbt invocation must not replace a flow's retained build evidence."""

from dataclasses import replace
from pathlib import Path

import pytest

from pipelines.flows.dbt_bi import collect_dbt_artifacts_for_context
from pipelines.flows.run_models import LocalRunContext


def _context(tmp_path, run_mode="local"):
    return LocalRunContext(
        pipeline_run_id="first",
        run_mode=run_mode,
        extract_mode="fixture",
        data_root=tmp_path / "data",
        duckdb_path=tmp_path / "warehouse.duckdb",
        dbt_project_dir=tmp_path / "dbt",
        dbt_profiles_dir=tmp_path / "profiles",
        dbt_target="dev_duckdb" if run_mode == "local" else "dev_snowflake",
        powerbi_export_dir=tmp_path / "exports",
        run_started_at_utc="2026-10-04T00:00:00Z",
    )


@pytest.mark.parametrize("run_mode", ["local", "cloud"])
def test_each_run_keeps_both_artifacts_after_shared_target_is_overwritten(
    tmp_path, run_mode
):
    context = _context(tmp_path, run_mode)
    target_dir = context.dbt_project_dir / "target"
    target_dir.mkdir(parents=True)
    names = ("manifest.json", "run_results.json")
    first_contents = {name: '{"invocation_id": "first"}' for name in names}
    for name, content in first_contents.items():
        (target_dir / name).write_text(content)
    first_artifacts = collect_dbt_artifacts_for_context(context)
    for name in names:
        (target_dir / name).write_text('{"invocation_id": "second"}')
    second_context = replace(context, pipeline_run_id="second")
    second_artifacts = collect_dbt_artifacts_for_context(second_context)
    for name in names:
        first_path = Path(first_artifacts[name])
        assert first_path == context.run_validation_dir / "dbt_artifacts" / name
        assert first_path.read_text() == first_contents[name]
        assert Path(second_artifacts[name]).read_text() == '{"invocation_id": "second"}'
        assert first_artifacts[name] != second_artifacts[name]


@pytest.mark.parametrize("present", [(), ("manifest.json",), ("run_results.json",)])
def test_incomplete_build_artifact_pair_cannot_be_reported_as_complete(
    tmp_path, present
):
    context = _context(tmp_path)
    target_dir = context.dbt_project_dir / "target"
    target_dir.mkdir(parents=True)
    for name in present:
        (target_dir / name).write_text("{}")
    with pytest.raises(RuntimeError, match="did not produce artifacts"):
        collect_dbt_artifacts_for_context(context)
    assert not (context.run_validation_dir / "dbt_artifacts").exists()
