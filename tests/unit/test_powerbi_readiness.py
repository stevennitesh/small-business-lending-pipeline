"""Failure-oriented checks for the saved-data CSV readiness command."""

import duckdb
import pytest

from scripts.verify_powerbi_readiness import check_csv


def test_readiness_preserves_text_keys_and_rejects_stale_or_duplicated_export(tmp_path):
    """A parseable export must still match current data and its declared grain."""
    path = tmp_path / "bi_state_filter.csv"
    fields = [
        "state_key",
        "state_fips",
        "state_name",
        "state_abbr",
        "census_region",
        "census_division",
    ]
    with duckdb.connect() as connection:
        connection.execute(
            "create table bi_state_filter as select '01' as state_key, '01' as state_fips, 'Alabama' as state_name, 'AL' as state_abbr, 'South' as census_region, 'East South Central' as census_division"
        )
        connection.execute("copy bi_state_filter to ? (header)", [str(path)])
        types = dict.fromkeys(fields, "text")
        result = check_csv(connection, "bi_state_filter", path, types, ["state_key"])
        assert result["leading_zero_text_values"] == {"state_key": 1, "state_fips": 1}
        original = path.read_text()
        path.write_text(original.replace("Alabama", "Old label"))
        with pytest.raises(ValueError, match="warehouse_differences=2"):
            check_csv(connection, "bi_state_filter", path, types, ["state_key"])
        path.write_text(original + original.splitlines()[1] + "\n")
        with pytest.raises(ValueError, match="duplicate_grains=1"):
            check_csv(connection, "bi_state_filter", path, types, ["state_key"])


def test_readiness_rejects_missing_or_incorrect_numeric_types(tmp_path):
    """Lexical CSV validation rejects a stale type map and nonnumeric years."""
    path = tmp_path / "bi_year_filter.csv"
    with duckdb.connect() as connection:
        connection.execute(
            "create table bi_year_filter as select 2025 as year, '2025' as year_label"
        )
        path.write_text("year,year_label\n2025,2025\n")
        with pytest.raises(ValueError, match="missing Power Query types"):
            check_csv(
                connection, "bi_year_filter", path, {"year_label": "text"}, ["year"]
            )
        with pytest.raises(ValueError, match="Power Query text, expected number"):
            check_csv(
                connection,
                "bi_year_filter",
                path,
                {"year": "text", "year_label": "text"},
                ["year"],
            )
        path.write_text("year,year_label\nunknown,2025\n")
        with pytest.raises(ValueError, match="invalid typed value"):
            check_csv(
                connection,
                "bi_year_filter",
                path,
                {"year": "number", "year_label": "text"},
                ["year"],
            )
