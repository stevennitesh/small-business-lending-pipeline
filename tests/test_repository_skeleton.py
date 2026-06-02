from pathlib import Path


def test_repository_skeleton_directories_exist():
    """Validate that repository skeleton directories exist."""
    required_dirs = [
        "config",
        "docs",
        "pipelines",
        "pipelines/extract",
        "pipelines/load",
        "pipelines/validation",
        "pipelines/flows",
        "pipelines/utils",
        "dbt",
        "dbt/models",
        "dbt/seeds",
        "dbt/macros",
        "dbt/tests",
        "tests",
        "scripts",
        "data",
        "powerbi/screenshots",
    ]

    missing = [path for path in required_dirs if not Path(path).is_dir()]

    assert missing == []


def test_environment_template_exists():
    """Validate that environment template exists."""
    assert Path(".env.example").is_file()


def test_runtime_files_exist():
    """Validate that runtime files exist."""
    required_files = [
        "requirements.txt",
        "Dockerfile",
        "docker-compose.yml",
        "Makefile",
        "scripts/run_local_pipeline.sh",
        "scripts/run_cloud_pipeline.sh",
        "scripts/run_dbt_local.sh",
    ]

    missing = [path for path in required_files if not Path(path).is_file()]

    assert missing == []


def test_local_runtime_scripts_are_executable():
    """Validate that local runtime scripts are executable."""
    scripts = [
        Path("scripts/run_local_pipeline.sh"),
        Path("scripts/run_cloud_pipeline.sh"),
        Path("scripts/run_dbt_local.sh"),
    ]

    non_executable = [str(path) for path in scripts if not path.stat().st_mode & 0o111]

    assert non_executable == []


def test_required_runtime_dependencies_are_declared():
    """Validate that required runtime dependencies are declared."""
    required_dependencies = {
        "requests",
        "pandas",
        "pyyaml",
        "python-dotenv",
        "boto3",
        "duckdb",
        "snowflake-connector-python",
        "dbt-core",
        "dbt-duckdb",
        "dbt-snowflake",
        "prefect",
        "pytest",
    }
    declared_dependencies = {
        line.strip().split("[", 1)[0]
        for line in Path("requirements.txt").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }

    assert required_dependencies <= declared_dependencies
