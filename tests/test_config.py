from __future__ import annotations

import pytest

from releaseforge.config import ConfigError, load_plan
from tests.helpers import write_plan


def test_load_plan_accepts_complete_relative_release(tmp_path):
    plan = load_plan(write_plan(tmp_path))

    assert plan.release.title == "Synthetic Release"
    assert plan.release.artist == "Synthetic Artist"
    assert plan.tracks[0].number == 1
    assert plan.tracks[0].relative_path.as_posix() == "audio/01-track.wav"
    assert plan.cover_relative_path.as_posix() == "artwork/cover.jpg"


def test_load_plan_rejects_path_escape(tmp_path):
    with pytest.raises(ConfigError, match="must stay inside"):
        load_plan(write_plan(tmp_path, cover_path="../cover.jpg"))


def test_load_plan_rejects_non_contiguous_track_numbers(tmp_path):
    root = write_plan(tmp_path, track_number=2)

    with pytest.raises(ConfigError, match="contiguous"):
        load_plan(root)


def test_load_plan_rejects_unknown_declaration_state(tmp_path):
    root = write_plan(tmp_path, rights_review="ready")

    with pytest.raises(ConfigError, match="rights_review"):
        load_plan(root)
