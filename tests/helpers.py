"""Small, explicit release-plan fixtures shared by tests."""

from __future__ import annotations

from pathlib import Path


def write_plan(
    release_dir: Path,
    *,
    cover_path: str = "artwork/cover.jpg",
    track_number: int = 1,
    track_path: str = "audio/01-track.wav",
    rights_review: str = "declared_current",
    metadata_review: str = "declared_current",
    artwork_approval: str = "declared_current",
) -> Path:
    """Write one complete synthetic declaration and return its release directory."""
    release_dir.mkdir(parents=True, exist_ok=True)
    (release_dir / "release.toml").write_text(
        f'''[release]
title = "Synthetic Release"
artist = "Synthetic Artist"
catalogue_number = "SYN-001"
planned_release_date = "2026-09-01"

[requirements]
minimum_cover_pixels = 3000
require_square_cover = true
allowed_audio_extensions = [".wav", ".flac", ".aiff"]

[assets]
cover = "{cover_path}"

[declarations]
rights_review = "{rights_review}"
metadata_review = "{metadata_review}"
artwork_approval = "{artwork_approval}"

[[tracks]]
number = {track_number}
title = "Synthetic Track"
file = "{track_path}"
declared_master_status = "declared_final"
''',
        encoding="utf-8",
    )
    return release_dir
