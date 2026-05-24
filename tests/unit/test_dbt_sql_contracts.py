import re
from pathlib import Path


MODEL_ROOT = Path("dbt/models")

SELECT_STAR_RE = re.compile(r"\bselect\s+(distinct\s+)?\*", re.IGNORECASE)
DISTINCT_STAR_RE = re.compile(r"\bdistinct\s+\*", re.IGNORECASE)
ALIAS_STAR_RE = re.compile(r"\b[a-zA-Z_][a-zA-Z0-9_]*\.\*")

EXPECTED_PRODUCTION_WILDCARD_PROJECTIONS = set()


def test_production_dbt_models_do_not_use_wildcard_projections():
    findings = {
        (path.as_posix(), line_number, token)
        for path in sorted(MODEL_ROOT.rglob("*.sql"))
        for line_number, token in wildcard_projection_findings(path.read_text())
    }

    assert findings == EXPECTED_PRODUCTION_WILDCARD_PROJECTIONS


def test_wildcard_projection_matcher_ignores_valid_star_uses():
    sql = """
with rollup as (
    select
        count(*) as row_count,
        loan_count * 1000.0 as loans_scaled
    from some_model
)

select
    state_key,
    row_count
from rollup
"""

    assert wildcard_projection_findings(sql) == []


def test_wildcard_projection_matcher_flags_projection_wildcards():
    sql = """
with hidden as (
    select *
    from some_model
),

spread as (
    select
        hidden.*,
        1 as marker
    from hidden
),

standalone as (
    select
        *,
        2 as marker
    from spread
),

distinct_inline as (
    select distinct *
    from spread
),

distinct_multiline as (
    select distinct
        *
    from spread
),

select_then_distinct as (
    select
        distinct *,
        3 as marker
    from spread
)

select state_key
from select_then_distinct
"""

    assert wildcard_projection_findings(sql) == [
        (3, "select *"),
        (9, "hidden.*"),
        (16, "*"),
        (22, "select distinct *"),
        (28, "*"),
        (34, "distinct *"),
    ]


def wildcard_projection_findings(sql: str) -> list[tuple[int, str]]:
    findings = []
    previous_code_line = ""

    for line_number, line in enumerate(sql.splitlines(), start=1):
        code_line = line.split("--", 1)[0]
        stripped = code_line.strip()
        if not stripped:
            continue

        select_star_match = SELECT_STAR_RE.search(code_line)
        if select_star_match:
            token = "select distinct *" if select_star_match.group(1) else "select *"
            findings.append((line_number, token))

        if _is_distinct_star_after_select(stripped, previous_code_line):
            findings.append((line_number, "distinct *"))

        if _is_standalone_star_after_select(stripped, previous_code_line):
            findings.append((line_number, "*"))

        findings.extend(
            (line_number, match.group(0))
            for match in ALIAS_STAR_RE.finditer(code_line)
        )
        previous_code_line = stripped.lower()

    return findings


def _is_standalone_star_after_select(
    stripped_line: str,
    previous_code_line: str,
) -> bool:
    normalized_previous = previous_code_line.lower()
    return (
        normalized_previous in {"select", "select distinct"}
        and (stripped_line == "*" or stripped_line.startswith("*,"))
    )


def _is_distinct_star_after_select(
    stripped_line: str,
    previous_code_line: str,
) -> bool:
    return previous_code_line.lower() == "select" and bool(
        DISTINCT_STAR_RE.match(stripped_line)
    )
