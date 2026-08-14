from __future__ import annotations

import pytest

from releaseforge.config import load_plan
from releaseforge.inspect import InspectionError, inspect_release
from tests.helpers import write_plan


def test_inspect_release_records_hash_and_image_geometry(synthetic_release):
    facts = inspect_release(load_plan(synthetic_release))
    cover = facts.by_role("cover")

    assert cover.sha256
    assert cover.byte_size > 0
    assert (cover.width, cover.height, cover.image_mode) == (3000, 3000, "RGB")
    assert cover.duration_seconds is None


def test_inspect_release_records_pcm_wav_duration(synthetic_release):
    track = inspect_release(load_plan(synthetic_release)).by_role("track:1")

    assert track.extension == ".wav"
    assert track.duration_seconds == pytest.approx(1.0)
    assert track.sample_rate == 44_100
    assert track.channels == 1


def test_inspect_release_rejects_a_missing_declared_asset(tmp_path):
    with pytest.raises(InspectionError, match="does not exist or is not a regular file"):
        inspect_release(load_plan(write_plan(tmp_path)))
