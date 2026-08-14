from __future__ import annotations

import struct

import pytest

from releaseforge.config import load_plan
from releaseforge.inspect import InspectionError, inspect_release
from tests.helpers import write_plan, write_synthetic_release


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


def test_inspect_release_rejects_a_wav_with_an_invalid_frame_rate(tmp_path):
    release = write_synthetic_release(tmp_path / "synthetic-release")
    track = release / "audio" / "01-track.wav"
    track.write_bytes(
        b"RIFF"
        + struct.pack("<I", 36)
        + b"WAVEfmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, 0, 0, 1, 8)
        + b"data"
        + struct.pack("<I", 0)
    )

    with pytest.raises(InspectionError, match="invalid frame rate"):
        inspect_release(load_plan(release))
