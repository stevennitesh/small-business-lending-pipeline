from __future__ import annotations

import pytest

from pipelines.load.raw_load_local_sources import load_local_source_frame


class LocalSourceFrameError(RuntimeError):
    pass


def test_local_source_frame_rejects_empty_manifests():
    with pytest.raises(
        LocalSourceFrameError,
        match="^No manifests provided for raw table: raw_census_bds_state_year$",
    ):
        load_local_source_frame(
            "raw_census_bds_state_year",
            [],
            error_cls=LocalSourceFrameError,
        )
