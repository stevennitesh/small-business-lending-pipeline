from pathlib import Path


def test_repository_skeleton_directories_exist():
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
    assert Path(".env.example").is_file()
