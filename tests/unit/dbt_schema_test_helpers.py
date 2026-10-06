from pathlib import Path
from typing import Any

import yaml


def schema_models(schema_path: Path) -> list[dict[str, Any]]:
    """Read dbt model entries from one schema YAML file."""
    schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    return schema["models"]


def models_by_name(schema_paths: list[Path]) -> dict[str, dict[str, Any]]:
    """Index dbt schema model entries by model name."""
    models: dict[str, dict[str, Any]] = {}
    for schema_path in schema_paths:
        models.update({model["name"]: model for model in schema_models(schema_path)})
    return models


def column(model: dict[str, Any], column_name: str) -> dict[str, Any]:
    """Return one dbt schema column entry by name."""
    return next(column for column in model["columns"] if column["name"] == column_name)


def dbt_test_name(test: Any) -> str:
    """Return the dbt generic test name from string or mapping syntax."""
    if isinstance(test, str):
        return test
    return next(iter(test))


def dbt_test_names(data_tests: list[Any]) -> set[str]:
    """Return all dbt generic test names from a schema test list."""
    return {dbt_test_name(test) for test in data_tests}


def find_dbt_test(data_tests: list[Any], test_name: str) -> Any:
    """Find one dbt generic test entry by name."""
    for test in data_tests:
        if dbt_test_name(test) == test_name:
            return test
    raise AssertionError(f"Missing dbt test: {test_name}")


def dbt_test_tags(test: Any) -> set[str]:
    """Return configured tags for a dbt generic test entry."""
    if isinstance(test, str):
        return set()
    config = test[dbt_test_name(test)].get("config", {})
    return set(config.get("tags", []))
