import re
from pathlib import Path


MODEL_ROOT = Path("dbt/models")

SELECT_STAR_RE = re.compile(r"\bselect\s+\*", re.IGNORECASE)
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
)

select state_key
from standalone
"""

    assert wildcard_projection_findings(sql) == [
        (3, "select *"),
        (9, "hidden.*"),
        (16, "*"),
    ]


def wildcard_projection_findings(sql: str) -> list[tuple[int, str]]:
    findings = []
    previous_code_line = ""

    for line_number, line in enumerate(sql.splitlines(), start=1):
        code_line = line.split("--", 1)[0]
        stripped = code_line.strip()
        if not stripped:
            continue

        if SELECT_STAR_RE.search(code_line):
            findings.append((line_number, "select *"))

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
    return (
        previous_code_line == "select"
        and (stripped_line == "*" or stripped_line.startswith("*,"))
    )
