from __future__ import annotations

import json
from pathlib import Path

from scripts.benchmark_local_command import (
    collect_duckdb_sizes,
    command_slug,
    diff_disk_sizes,
    directory_size_bytes,
    parse_dbt_slow_nodes,
    parse_fresh_dbt_slow_nodes,
    render_text_summary,
)


def test_parse_dbt_slow_nodes_sorts_by_execution_time(tmp_path):
    run_results_path = tmp_path / "run_results.json"
    run_results_path.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "unique_id": "model.project.fast",
                        "status": "success",
                        "execution_time": 0.5,
                    },
                    {
                        "unique_id": "model.project.slow",
                        "status": "success",
                        "execution_time": 3.25,
                    },
                    {
                        "unique_id": "model.project.no_time",
                        "status": "skipped",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    slow_nodes = parse_dbt_slow_nodes(run_results_path)

    assert [node["unique_id"] for node in slow_nodes] == [
        "model.project.slow",
        "model.project.fast",
    ]
    assert slow_nodes[0]["execution_time_seconds"] == 3.25


def test_parse_dbt_slow_nodes_returns_empty_when_missing(tmp_path):
    assert parse_dbt_slow_nodes(tmp_path / "missing.json") == []


def test_parse_fresh_dbt_slow_nodes_ignores_stale_run_results(tmp_path):
    run_results_path = tmp_path / "run_results.json"
    run_results_path.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "unique_id": "model.project.stale",
                        "status": "success",
                        "execution_time": 1.0,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    mtime_before = run_results_path.stat().st_mtime

    assert parse_fresh_dbt_slow_nodes(
        run_results_path,
        run_results_mtime_before=mtime_before,
    ) == []


def test_directory_size_bytes_and_diff_disk_sizes(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "a.txt").write_text("abcd", encoding="utf-8")
    (data_dir / "b.txt").write_text("ef", encoding="utf-8")

    assert directory_size_bytes(data_dir) == 6
    assert diff_disk_sizes(
        {"data": 6, "missing": None},
        {"data": 10, "missing": 1},
    ) == {"data": 4, "missing": None}


def test_collect_duckdb_sizes_includes_wal(tmp_path):
    duckdb_path = tmp_path / "warehouse.duckdb"
    wal_path = tmp_path / "warehouse.duckdb.wal"
    duckdb_path.write_text("db", encoding="utf-8")
    wal_path.write_text("wal", encoding="utf-8")

    sizes = collect_duckdb_sizes(duckdb_path)

    assert sizes["bytes"] == 2
    assert sizes["wal_bytes"] == 3
    assert sizes["path"] == duckdb_path.as_posix()


def test_command_slug_and_text_summary_are_stable():
    assert command_slug('make benchmark-local COMMAND="make dbt-local"') == (
        "make-benchmark-local-command-make-dbt-local"
    )

    summary = render_text_summary(
        {
            "command": {"text": "make dbt-local", "exit_code": 0},
            "wall_time_seconds": 1.2,
            "max_rss_bytes": 1234,
            "disk_sizes_bytes": {"delta": {"data": 42}},
            "duckdb": {
                "path": "data/warehouse/small_business_lending.duckdb",
                "bytes": 10,
                "wal_path": "data/warehouse/small_business_lending.duckdb.wal",
                "wal_bytes": None,
            },
            "dbt_slow_nodes": [
                {
                    "unique_id": "model.project.slow",
                    "status": "success",
                    "execution_time_seconds": 2.0,
                }
            ],
        }
    )

    assert "Command: make dbt-local" in summary
    assert "- data: 42" in summary
    assert "model.project.slow [success]: 2.0" in summary
