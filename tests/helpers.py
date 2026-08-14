"""Small, explicit release-plan fixtures shared by tests."""

from __future__ import annotations

import wave
from pathlib import Path

from PIL import Image


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


def write_synthetic_release(
    release_dir: Path,
    *,
    cover_size: tuple[int, int] = (3000, 3000),
    cover_mode: str = "RGB",
    duration_seconds: float = 1.0,
) -> Path:
    """Create one valid local release folder for file-inspection tests."""
    root = write_plan(release_dir)
    artwork_dir = root / "artwork"
    audio_dir = root / "audio"
    artwork_dir.mkdir(exist_ok=True)
    audio_dir.mkdir(exist_ok=True)
    Image.new(cover_mode, cover_size, color=(12, 24, 36)).save(artwork_dir / "cover.jpg")

    frame_rate = 44_100
    frame_count = round(frame_rate * duration_seconds)
    with wave.open(str(audio_dir / "01-track.wav"), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(frame_rate)
        output.writeframes(b"\x00\x00" * frame_count)
    return root
