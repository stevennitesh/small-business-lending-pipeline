"""Shared argparse option builders for source extractor CLIs."""

from __future__ import annotations

import argparse


def add_common_extraction_arguments(
    parser: argparse.ArgumentParser,
    *,
    config_default: str,
    s3_bucket_default: str,
) -> None:
    """Add CLI options shared by source-specific extract commands."""
    parser.add_argument("--config", default=config_default)
    parser.add_argument("--data-root", default="data")
    parser.add_argument("--s3-bucket", default=s3_bucket_default)
    parser.add_argument("--pipeline-run-id")


def add_year_range_arguments(parser: argparse.ArgumentParser) -> None:
    """Add optional inclusive year bounds for extractors that support them."""
    parser.add_argument("--start-year", type=int)
    parser.add_argument("--end-year", type=int)
