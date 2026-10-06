"""Execution helpers for timing and completing flow stages."""

from __future__ import annotations

import time
from typing import Any, Callable

from pipelines.flows.run_models import FlowRunState


def run_timed_stage(
    stage_durations_seconds: dict[str, float],
    stage_name: str,
    stage_callable: Callable[..., Any],
    *args,
    **kwargs,
):
    """Execute a stage and record its elapsed wall-clock duration."""
    started_at = time.perf_counter()
    try:
        return stage_callable(*args, **kwargs)
    finally:
        stage_durations_seconds[stage_name] = round(
            time.perf_counter() - started_at,
            3,
        )


def run_timed_flow_stage(
    state: FlowRunState,
    stage_name: str,
    stage_callable: Callable[..., Any],
    *args,
    completed_stages: tuple[str, ...] | None = None,
    **kwargs,
):
    """Execute a timed stage and mark one or more logical flow stages complete."""
    result = run_timed_stage(
        state.stage_durations_seconds,
        stage_name,
        stage_callable,
        *args,
        **kwargs,
    )
    if completed_stages is None:
        state.complete(stage_name)
    else:
        # A single adapter can complete multiple logical stages; extraction
        # returns both raw artifacts and manifests, so failure summaries keep the
        # user-facing stage order even when implementation is consolidated.
        state.complete_many(list(completed_stages))
    return result
