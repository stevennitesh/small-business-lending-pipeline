from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipelines.powerbi.model_contract import (
    MODEL_PATH,
    validate_powerbi_model,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the Power BI model contract.")
    parser.add_argument("--model-path", default=str(MODEL_PATH))
    args = parser.parse_args()

    summary = validate_powerbi_model(args.model_path)
    print(json.dumps(summary.__dict__, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
