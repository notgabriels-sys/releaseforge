from __future__ import annotations

import pytest
from PIL import Image

from releaseforge.cli import main
from releaseforge.config import load_plan
from releaseforge.inspect import InspectionError, inspect_release
from tests.helpers import tree_digest, write_plan


def test_build_rejects_an_output_inside_the_release_source(synthetic_release, capsys):
    before = tree_digest(synthetic_release)

    assert (
        main(["build", str(synthetic_release), "--output", str(synthetic_release / "proof")]) == 2
    )

    assert tree_digest(synthetic_release) == before
    assert "outside the release source directory" in capsys.readouterr().err


def test_inspection_rejects_a_path_that_escapes_via_symlink(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    Image.new("RGB", (3000, 3000), color=(12, 24, 36)).save(outside / "cover.jpg")

    release_dir = write_plan(tmp_path / "release")
    (release_dir / "artwork").symlink_to(outside, target_is_directory=True)

    with pytest.raises(InspectionError, match="must stay inside release directory"):
        inspect_release(load_plan(release_dir))
