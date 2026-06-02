from __future__ import annotations

import argparse
import json

try:
    from scripts.repo_bootstrap import add_repo_root_to_path
except ModuleNotFoundError:
    from repo_bootstrap import add_repo_root_to_path

add_repo_root_to_path()

from pipelines.powerbi.model_contract import (
    MODEL_PATH,
    validate_powerbi_model,
)


def main() -> None:
    """Validate the source-controlled Power BI model contract."""
    parser = argparse.ArgumentParser(
        description="Validate the Power BI model contract."
    )
    parser.add_argument("--model-path", default=str(MODEL_PATH))
    args = parser.parse_args()

    summary = validate_powerbi_model(args.model_path)
    print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
