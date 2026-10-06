"""Pass the same dated reporting policies to local and cloud dbt commands."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from pipelines.utils.config import load_project_config
from pipelines.utils.source_config_models import load_yaml_file


def dbt_policy_vars(config_dir: Path | str = "config") -> dict:
    """Load source age thresholds and explicit publisher coverage evidence."""
    config_dir = Path(config_dir)
    config = load_project_config(config_dir)
    policy = load_yaml_file(config_dir / "reporting_policy.yml")["reporting_policy"]
    for field in (
        "evidence_as_of",
        "sba_calendar_start",
        "sba_calendar_end",
        "bls_observation_end",
    ):
        date.fromisoformat(policy[field])
    if policy["sba_calendar_start"] > policy["sba_calendar_end"]:
        raise ValueError("SBA calendar coverage start exceeds end")
    release = policy.get("census_bds_release", {})
    year = release.get("latest_year")
    if type(year) is not int or year < 1978:
        raise ValueError("Census BDS release requires an integer latest_year >= 1978")
    released_on = date.fromisoformat(release["released_on"])
    verified_on = date.fromisoformat(release["verified_on"])
    if year > released_on.year or verified_on < released_on:
        raise ValueError("Census BDS release dates do not support the declared year")
    if (
        not isinstance(release.get("source_url"), str)
        or not release["source_url"].strip()
    ):
        raise ValueError("Census BDS release requires a source_url")
    for source, period_field in (
        ("sba", "sba_calendar_end"),
        ("bls", "bls_observation_end"),
    ):
        evidence = policy.get("source_publications", {}).get(source, {})
        verified = date.fromisoformat(evidence["verified_on"])
        published = (
            date.fromisoformat(evidence["released_on"])
            if evidence.get("released_on") is not None
            else None
        )
        if verified < date.fromisoformat(policy[period_field]):
            raise ValueError(
                f"{source} publication verification precedes its reference period"
            )
        if published is not None and (
            published > verified or published < date.fromisoformat(policy[period_field])
        ):
            raise ValueError(
                f"{source} publication dates do not support its reference period"
            )
        if (
            not isinstance(evidence.get("source_url"), str)
            or not evidence["source_url"].strip()
        ):
            raise ValueError(f"{source} publication requires a source_url")
        if evidence.get("next_scheduled_release") is not None:
            scheduled = date.fromisoformat(evidence["next_scheduled_release"])
            if published is not None and scheduled <= published:
                raise ValueError(
                    f"{source} next scheduled release must follow the saved publication"
                )
    omissions = policy["bls_publisher_omissions"]
    if len({(item["year"], item["month"]) for item in omissions}) != len(omissions):
        raise ValueError("Duplicate BLS publisher omission")
    for item in omissions:
        if not 1 <= item["month"] <= 12 or not isinstance(item["year"], int):
            raise ValueError("Invalid BLS publisher omission")
    return {
        "reporting_policy": policy,
        "source_freshness_rules": {
            config.sources[key].source_system: rule
            for key, rule in config.freshness_rules.items()
        },
    }


if __name__ == "__main__":
    print(json.dumps(dbt_policy_vars()))
