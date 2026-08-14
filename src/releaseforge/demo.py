"""Create a safe, synthetic local demonstration of the Releaseforge workflow."""

from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from releaseforge.config import ConfigError, load_plan
from releaseforge.evaluate import evaluate_release
from releaseforge.inspect import InspectionError, inspect_release
from releaseforge.report import ReportError, make_report, write_packet

_PLAN = """# Synthetic Releaseforge demo only. Do not treat these declarations as real evidence.

[release]
title = "Synthetic Releaseforge Demo"
artist = "Illustrative Artist"
catalogue_number = "DEMO-001"
planned_release_date = "2026-09-01"

[requirements]
minimum_cover_pixels = 3000
require_square_cover = true
allowed_audio_extensions = [".wav", ".flac", ".aiff"]

[assets]
cover = "artwork/final-cover.jpg"

[declarations]
rights_review = "declared_current"
metadata_review = "declared_current"
artwork_approval = "declared_current"

[[tracks]]
number = 1
title = "Synthetic One-Second WAV"
file = "audio/01-synthetic-tone.wav"
declared_master_status = "declared_final"
"""

_GUIDE = """# Releaseforge synthetic demo

Everything in this directory was generated locally by `releaseforge demo`.
The two release folders, audio files, cover images, and declarations are
synthetic. They are not a real release and do not establish rights, approval,
distributor acceptance, or readiness for public release.

## What was created

- `release-v1/` and `release-v2/`: two complete synthetic release folders.
- `proof-v1/` and `proof-v2/`: packets created through the standard build path.

The cover bytes differ between the two versions. The rest of the simulated
release is unchanged, so comparison has one clear verified-file difference.

## Try it

From this directory, run:

```bash
releaseforge compare proof-v1 proof-v2
releaseforge compare proof-v1 proof-v2 --json
```

The command returns exit status `1` because it found a captured change. That
exit code means “different packets,” not an application failure.

You can delete this entire synthetic demo when you are done. For real work, use
`releaseforge init` in a new or existing release folder and verify every
declared workflow requirement against the actual delivery destination.
"""


class DemoError(ValueError):
    """Raised when a synthetic demo cannot be created safely."""


@dataclass(frozen=True)
class Demo:
    """The components created for a synthetic two-version workflow."""

    root: Path
    guide: Path
    release_v1: Path
    release_v2: Path
    proof_v1: Path
    proof_v2: Path


def create_demo(destination: Path | str) -> Demo:
    """Create two synthetic release folders and packets in one new destination only."""
    root = Path(destination)
    if root.exists():
        raise DemoError(f"demo destination already exists: {root.name}")
    try:
        root.mkdir(parents=True, exist_ok=False)
        release_v1 = _write_release(root / "release-v1", color=(12, 24, 36))
        release_v2 = _write_release(root / "release-v2", color=(62, 22, 48))
        proof_v1 = _build_packet(release_v1, root / "proof-v1")
        proof_v2 = _build_packet(release_v2, root / "proof-v2")
        guide = root / "START_HERE.md"
        guide.write_text(_GUIDE, encoding="utf-8")
    except (ConfigError, InspectionError, OSError, ReportError) as error:
        raise DemoError(f"could not create synthetic demo: {error}") from error
    return Demo(
        root=root,
        guide=guide,
        release_v1=release_v1,
        release_v2=release_v2,
        proof_v1=proof_v1,
        proof_v2=proof_v2,
    )


def _write_release(release_dir: Path, *, color: tuple[int, int, int]) -> Path:
    artwork_dir = release_dir / "artwork"
    audio_dir = release_dir / "audio"
    artwork_dir.mkdir(parents=True)
    audio_dir.mkdir()
    (release_dir / "release.toml").write_text(_PLAN, encoding="utf-8")
    Image.new("RGB", (3000, 3000), color=color).save(artwork_dir / "final-cover.jpg", quality=90)
    with wave.open(str(audio_dir / "01-synthetic-tone.wav"), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(44_100)
        output.writeframes(b"\x00\x00" * 44_100)
    return release_dir


def _build_packet(release_dir: Path, output_dir: Path) -> Path:
    plan = load_plan(release_dir)
    inspection = inspect_release(plan)
    report = make_report(plan, inspection, evaluate_release(plan, inspection))
    return write_packet(report, output_dir)
