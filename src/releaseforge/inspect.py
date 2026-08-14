"""Read verified local asset facts without modifying the release source tree."""

from __future__ import annotations

import hashlib
import wave
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from PIL import Image, UnidentifiedImageError

from releaseforge.config import ConfigError, ReleasePlan, resolve_asset_path


class InspectionError(ValueError):
    """Raised when a declared local asset cannot be safely read."""


@dataclass(frozen=True)
class AssetFact:
    """A fact read directly from one local asset's bytes or container header."""

    role: str
    relative_path: PurePosixPath
    byte_size: int
    sha256: str
    extension: str
    width: int | None = None
    height: int | None = None
    image_mode: str | None = None
    duration_seconds: float | None = None
    sample_rate: int | None = None
    channels: int | None = None
    sample_width_bytes: int | None = None


@dataclass(frozen=True)
class Inspection:
    """Verified facts gathered from every source asset in a release declaration."""

    assets: tuple[AssetFact, ...]

    def by_role(self, role: str) -> AssetFact:
        """Return one fact by its stable report role."""
        for asset in self.assets:
            if asset.role == role:
                return asset
        raise KeyError(f"no inspected asset has role {role!r}")


def inspect_release(plan: ReleasePlan) -> Inspection:
    """Inspect the declared cover and tracks in a deterministic declaration order."""
    assets = [_inspect_cover(plan, plan.cover_relative_path)]
    assets.extend(_inspect_track(plan, track.number, track.relative_path) for track in plan.tracks)
    return Inspection(assets=tuple(assets))


def _inspect_cover(plan: ReleasePlan, relative_path: PurePosixPath) -> AssetFact:
    path = _existing_asset_path(plan, relative_path, "cover")
    byte_size, sha256 = _file_facts(path)
    try:
        with Image.open(path) as image:
            image.load()
            width, height, image_mode = image.width, image.height, image.mode
    except (UnidentifiedImageError, OSError) as error:
        raise InspectionError(
            f"cover is not a readable image: {relative_path.as_posix()}"
        ) from error
    return AssetFact(
        role="cover",
        relative_path=relative_path,
        byte_size=byte_size,
        sha256=sha256,
        extension=path.suffix.lower(),
        width=width,
        height=height,
        image_mode=image_mode,
    )


def _inspect_track(plan: ReleasePlan, number: int, relative_path: PurePosixPath) -> AssetFact:
    path = _existing_asset_path(plan, relative_path, f"track:{number}")
    byte_size, sha256 = _file_facts(path)
    extension = path.suffix.lower()
    wav_facts = _read_wav_facts(path, relative_path) if extension == ".wav" else {}
    return AssetFact(
        role=f"track:{number}",
        relative_path=relative_path,
        byte_size=byte_size,
        sha256=sha256,
        extension=extension,
        **wav_facts,
    )


def _existing_asset_path(plan: ReleasePlan, relative_path: PurePosixPath, role: str) -> Path:
    try:
        path = resolve_asset_path(plan, relative_path)
    except ConfigError as error:
        raise InspectionError(str(error)) from error
    if not path.is_file():
        raise InspectionError(
            f"{role} asset does not exist or is not a regular file: {relative_path.as_posix()}"
        )
    return path


def _file_facts(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        return path.stat().st_size, digest.hexdigest()
    except OSError as error:
        raise InspectionError(f"could not read asset: {path.name}") from error


def _read_wav_facts(path: Path, relative_path: PurePosixPath) -> dict[str, int | float]:
    try:
        with wave.open(str(path), "rb") as source:
            frame_rate = source.getframerate()
            frame_count = source.getnframes()
            if frame_rate <= 0:
                raise InspectionError(
                    f"WAV track has an invalid frame rate: {relative_path.as_posix()}"
                )
            return {
                "duration_seconds": frame_count / frame_rate,
                "sample_rate": frame_rate,
                "channels": source.getnchannels(),
                "sample_width_bytes": source.getsampwidth(),
            }
    except (EOFError, OSError, wave.Error) as error:
        raise InspectionError(f"WAV track is not readable: {relative_path.as_posix()}") from error
