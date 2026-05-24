from __future__ import annotations

import argparse
import json
import os
import re
import resource
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_OUTPUT_DIR = Path(".tmp/benchmarks")
DEFAULT_RUN_RESULTS_PATH = Path("dbt/target/run_results.json")
DEFAULT_DUCKDB_PATH = Path("data/warehouse/small_business_lending.duckdb")
DEFAULT_SIZE_PATHS = (
    Path("data"),
    Path("data/raw"),
    Path("data/warehouse"),
    Path("data/exports/powerbi"),
    Path("dbt/target"),
)


@dataclass(frozen=True)
class BenchmarkPaths:
    output_dir: Path = DEFAULT_OUTPUT_DIR
    run_results_path: Path = DEFAULT_RUN_RESULTS_PATH
    duckdb_path: Path = DEFAULT_DUCKDB_PATH
    size_paths: tuple[Path, ...] = DEFAULT_SIZE_PATHS


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    paths = BenchmarkPaths(output_dir=args.output_dir)
    result = run_benchmark(args.command, paths=paths)
    json_path, text_path = write_benchmark_outputs(result, paths.output_dir)
    print(f"Benchmark JSON: {json_path}")
    print(f"Benchmark text: {text_path}")
    return int(result["command"]["exit_code"])


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark a local pipeline command and write evidence under .tmp/benchmarks.",
    )
    parser.add_argument(
        "--command",
        required=True,
        help='Command to benchmark, for example: --command "make dbt-local"',
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for benchmark JSON and text outputs.",
    )
    return parser.parse_args(argv)


def run_benchmark(command: str, *, paths: BenchmarkPaths) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc)
    sizes_before = collect_disk_sizes(paths.size_paths)
    run_results_mtime_before = file_mtime(paths.run_results_path)
    started = time.perf_counter()
    completed = subprocess.run(command, shell=True, check=False)
    wall_time_seconds = time.perf_counter() - started
    max_rss_bytes = get_child_max_rss_bytes()
    sizes_after = collect_disk_sizes(paths.size_paths)

    return {
        "benchmark_started_at": started_at.isoformat(),
        "benchmark_completed_at": datetime.now(timezone.utc).isoformat(),
        "command": {
            "text": command,
            "exit_code": completed.returncode,
        },
        "wall_time_seconds": round(wall_time_seconds, 3),
        "max_rss_bytes": max_rss_bytes,
        "disk_sizes_bytes": {
            "before": sizes_before,
            "after": sizes_after,
            "delta": diff_disk_sizes(sizes_before, sizes_after),
        },
        "duckdb": collect_duckdb_sizes(paths.duckdb_path),
        "dbt_slow_nodes": parse_fresh_dbt_slow_nodes(
            paths.run_results_path,
            run_results_mtime_before=run_results_mtime_before,
        ),
    }


def collect_disk_sizes(paths: tuple[Path, ...]) -> dict[str, int | None]:
    return {path.as_posix(): directory_size_bytes(path) for path in paths}


def directory_size_bytes(path: Path) -> int | None:
    if not path.exists():
        return None
    if path.is_file():
        return path.stat().st_size

    total = 0
    for root, dirs, files in os.walk(path):
        dirs[:] = [directory for directory in dirs if not Path(root, directory).is_symlink()]
        for filename in files:
            file_path = Path(root, filename)
            if not file_path.is_symlink():
                total += file_path.stat().st_size
    return total


def diff_disk_sizes(
    before: dict[str, int | None],
    after: dict[str, int | None],
) -> dict[str, int | None]:
    deltas: dict[str, int | None] = {}
    for path, after_size in after.items():
        before_size = before.get(path)
        if before_size is None and after_size is None:
            deltas[path] = None
        elif before_size is None:
            deltas[path] = after_size
        elif after_size is None:
            deltas[path] = -before_size
        else:
            deltas[path] = after_size - before_size
    return deltas


def collect_duckdb_sizes(duckdb_path: Path) -> dict[str, int | None]:
    wal_path = duckdb_path.with_suffix(f"{duckdb_path.suffix}.wal")
    return {
        "path": duckdb_path.as_posix(),
        "bytes": file_size_bytes(duckdb_path),
        "wal_path": wal_path.as_posix(),
        "wal_bytes": file_size_bytes(wal_path),
    }


def file_size_bytes(path: Path) -> int | None:
    return path.stat().st_size if path.exists() else None


def file_mtime(path: Path) -> float | None:
    return path.stat().st_mtime if path.exists() else None


def get_child_max_rss_bytes() -> int | None:
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    max_rss = int(usage.ru_maxrss)
    if max_rss <= 0:
        return None
    if sys.platform == "darwin":
        return max_rss
    return max_rss * 1024


def parse_dbt_slow_nodes(run_results_path: Path, *, limit: int = 10) -> list[dict[str, Any]]:
    if not run_results_path.exists():
        return []

    payload = json.loads(run_results_path.read_text(encoding="utf-8"))
    results = payload.get("results", [])
    slow_nodes = [
        {
            "unique_id": result.get("unique_id"),
            "status": result.get("status"),
            "execution_time_seconds": result.get("execution_time"),
        }
        for result in results
        if result.get("execution_time") is not None
    ]
    return sorted(
        slow_nodes,
        key=lambda node: float(node["execution_time_seconds"] or 0),
        reverse=True,
    )[:limit]


def parse_fresh_dbt_slow_nodes(
    run_results_path: Path,
    *,
    run_results_mtime_before: float | None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    run_results_mtime_after = file_mtime(run_results_path)
    if run_results_mtime_after is None:
        return []
    if (
        run_results_mtime_before is not None
        and run_results_mtime_after <= run_results_mtime_before
    ):
        return []
    return parse_dbt_slow_nodes(run_results_path, limit=limit)


def write_benchmark_outputs(
    result: dict[str, Any],
    output_dir: Path,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    slug = command_slug(result["command"]["text"])
    base_path = output_dir / f"{timestamp}-{slug}"
    json_path = base_path.with_suffix(".json")
    text_path = base_path.with_suffix(".txt")

    json_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    text_path.write_text(render_text_summary(result), encoding="utf-8")
    return json_path, text_path


def command_slug(command: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", command.strip().lower()).strip("-")
    return slug[:80] or "local-command"


def render_text_summary(result: dict[str, Any]) -> str:
    lines = [
        "Local Pipeline Benchmark",
        f"Command: {result['command']['text']}",
        f"Exit code: {result['command']['exit_code']}",
        f"Wall time seconds: {result['wall_time_seconds']}",
        f"Max RSS bytes: {result['max_rss_bytes']}",
        "Disk size deltas bytes:",
    ]
    lines.extend(
        f"- {path}: {delta}"
        for path, delta in result["disk_sizes_bytes"]["delta"].items()
    )
    lines.append("DuckDB:")
    lines.append(f"- {result['duckdb']['path']}: {result['duckdb']['bytes']}")
    lines.append(f"- {result['duckdb']['wal_path']}: {result['duckdb']['wal_bytes']}")
    lines.append("Slow dbt nodes:")
    if result["dbt_slow_nodes"]:
        lines.extend(
            f"- {node['unique_id']} [{node['status']}]: {node['execution_time_seconds']}"
            for node in result["dbt_slow_nodes"]
        )
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
