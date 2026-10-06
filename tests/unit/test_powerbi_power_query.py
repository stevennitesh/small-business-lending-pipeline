"""Static M handoff checks where Power BI's M runtime is unavailable."""

from collections import Counter
from pathlib import Path
import json
import re

from pipelines.powerbi.export_schema import BI_EXPORT_TABLES


def _column_type_fields():
    source = Path("powerbi/power_query/local_csv_queries.pq").read_text(
        encoding="utf-8"
    )
    record = source.split("ColumnTypes = [", 1)[1].split("\n    ],", 1)[0]
    return re.findall(
        r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*type\s+(\w+)\s*,?\s*$", record, re.M
    )


def test_power_query_record_fields_are_unique():
    """Duplicate M record fields invalidate every CSV loader before import."""
    fields = _column_type_fields()
    assert fields
    assert all(count == 1 for count in Counter(name for name, _ in fields).values())
    source = Path("powerbi/power_query/local_csv_queries.pq").read_text(
        encoding="utf-8"
    )
    exports = re.findall(r'^\s*(bi_\w+)\s*=\s*LoadCsv\("(bi_\w+)"\)', source, re.M)
    assert len(exports) == len(BI_EXPORT_TABLES)
    assert {name for name, _ in exports} == set(BI_EXPORT_TABLES)
    assert all(name == argument for name, argument in exports)


def test_power_query_flags_and_dates_have_correct_types():
    """Coverage flags stay logical and dates/timestamps cannot shadow them."""
    types = dict(_column_type_fields())
    model = json.loads(
        Path("powerbi/lending_dashboard_model.json").read_text(encoding="utf-8")
    )
    columns = {
        column for table in model["tables"] for column in table["required_columns"]
    }
    for column in columns:
        if column.startswith(("is_", "has_")):
            assert types[column] == "logical", column
        elif column.endswith("_utc"):
            assert types[column] == "datetimezone", column
        elif column.endswith("_date") or column in {
            "coverage_evidence_as_of",
            "source_calendar_start",
            "source_calendar_end",
        }:
            assert types[column] == "date", column
    assert (
        types["observed_expected_month_count"]
        == types["unexpected_month_count"]
        == "number"
    )
