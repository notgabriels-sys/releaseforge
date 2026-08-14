"""Strict parsing for local Releaseforge workflow declarations."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any


class ConfigError(ValueError):
    """Raised when a release declaration is structurally unsafe or incomplete."""


DECLARATION_STATES = frozenset({"declared_current", "declared_pending", "declared_unknown"})
MASTER_STATES = frozenset({"declared_final", "declared_pending", "declared_unknown"})


@dataclass(frozen=True)
class ReleaseMeta:
    """Declared release-level data; presence is checked but truth is not established."""

    title: str
    artist: str
    catalogue_number: str
    planned_release_date: date


@dataclass(frozen=True)
class RequirementPlan:
    """The user's chosen workflow checks, not a distributor policy statement."""

    minimum_cover_pixels: int
    require_square_cover: bool
    allowed_audio_extensions: tuple[str, ...]


@dataclass(frozen=True)
class DeclarationPlan:
    """Declared review states requiring human evidence outside this tool."""

    rights_review: str
    metadata_review: str
    artwork_approval: str


@dataclass(frozen=True)
class TrackPlan:
    """One declared ordered track and its local source path."""

    number: int
    title: str
    relative_path: PurePosixPath
    declared_master_status: str


@dataclass(frozen=True)
class ReleasePlan:
    """A validated release declaration rooted at one local release directory."""

    root: Path
    release: ReleaseMeta
    requirements: RequirementPlan
    cover_relative_path: PurePosixPath
    tracks: tuple[TrackPlan, ...]
    declarations: DeclarationPlan


def load_plan(release_dir: Path | str) -> ReleasePlan:
    """Load ``release.toml`` from *release_dir* and validate its strict schema."""
    root = Path(release_dir).resolve()
    if not root.is_dir():
        raise ConfigError(f"release directory does not exist or is not a directory: {release_dir}")

    path = root / "release.toml"
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ConfigError("release.toml does not exist") from error
    except OSError as error:
        raise ConfigError(f"could not read release.toml: {error}") from error
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"release.toml is not valid TOML: {error}") from error

    _expect_exact_keys(
        document, {"release", "requirements", "assets", "declarations", "tracks"}, "root"
    )
    release = _parse_release(_mapping(document, "release", "root"))
    requirements = _parse_requirements(_mapping(document, "requirements", "root"))
    cover_relative_path = _parse_relative_path(
        _string(_mapping(document, "assets", "root"), "cover", "assets"),
        "assets.cover",
    )
    declarations = _parse_declarations(_mapping(document, "declarations", "root"))
    tracks = _parse_tracks(document["tracks"])

    all_paths = (cover_relative_path, *(track.relative_path for track in tracks))
    if len(set(all_paths)) != len(all_paths):
        raise ConfigError("declared asset paths must be unique")

    return ReleasePlan(
        root=root,
        release=release,
        requirements=requirements,
        cover_relative_path=cover_relative_path,
        tracks=tracks,
        declarations=declarations,
    )


def resolve_asset_path(plan: ReleasePlan, relative_path: PurePosixPath) -> Path:
    """Resolve a declared path and reject symlink or lexical escapes from the release root."""
    root = plan.root.resolve()
    candidate = (root / Path(*relative_path.parts)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ConfigError(
            f"{relative_path.as_posix()} must stay inside release directory"
        ) from error
    return candidate


def _parse_release(section: dict[str, Any]) -> ReleaseMeta:
    _expect_exact_keys(
        section, {"title", "artist", "catalogue_number", "planned_release_date"}, "release"
    )
    raw_date = _string(section, "planned_release_date", "release")
    try:
        planned_release_date = date.fromisoformat(raw_date)
    except ValueError as error:
        raise ConfigError("release.planned_release_date must use YYYY-MM-DD") from error
    return ReleaseMeta(
        title=_string(section, "title", "release"),
        artist=_string(section, "artist", "release"),
        catalogue_number=_string(section, "catalogue_number", "release"),
        planned_release_date=planned_release_date,
    )


def _parse_requirements(section: dict[str, Any]) -> RequirementPlan:
    _expect_exact_keys(
        section,
        {"minimum_cover_pixels", "require_square_cover", "allowed_audio_extensions"},
        "requirements",
    )
    minimum_cover_pixels = section["minimum_cover_pixels"]
    if isinstance(minimum_cover_pixels, bool) or not isinstance(minimum_cover_pixels, int):
        raise ConfigError("requirements.minimum_cover_pixels must be a positive integer")
    if minimum_cover_pixels <= 0:
        raise ConfigError("requirements.minimum_cover_pixels must be a positive integer")

    require_square_cover = section["require_square_cover"]
    if not isinstance(require_square_cover, bool):
        raise ConfigError("requirements.require_square_cover must be true or false")

    raw_extensions = section["allowed_audio_extensions"]
    if not isinstance(raw_extensions, list) or not raw_extensions:
        raise ConfigError("requirements.allowed_audio_extensions must be a non-empty list")
    extensions: list[str] = []
    for raw_extension in raw_extensions:
        if not isinstance(raw_extension, str) or not raw_extension.startswith("."):
            raise ConfigError(
                "requirements.allowed_audio_extensions must use extensions such as '.wav'"
            )
        extension = raw_extension.lower()
        if (
            extension != raw_extension
            or len(extension) == 1
            or "/" in extension
            or "\\" in extension
        ):
            raise ConfigError(
                "requirements.allowed_audio_extensions must be lowercase file extensions"
            )
        extensions.append(extension)
    if len(set(extensions)) != len(extensions):
        raise ConfigError("requirements.allowed_audio_extensions must not repeat values")

    return RequirementPlan(
        minimum_cover_pixels=minimum_cover_pixels,
        require_square_cover=require_square_cover,
        allowed_audio_extensions=tuple(extensions),
    )


def _parse_declarations(section: dict[str, Any]) -> DeclarationPlan:
    _expect_exact_keys(
        section, {"rights_review", "metadata_review", "artwork_approval"}, "declarations"
    )
    values = {
        key: _state(section, key, "declarations", DECLARATION_STATES)
        for key in ("rights_review", "metadata_review", "artwork_approval")
    }
    return DeclarationPlan(**values)


def _parse_tracks(raw_tracks: Any) -> tuple[TrackPlan, ...]:
    if not isinstance(raw_tracks, list) or not raw_tracks:
        raise ConfigError("tracks must contain at least one [[tracks]] entry")

    tracks: list[TrackPlan] = []
    for index, raw_track in enumerate(raw_tracks, start=1):
        if not isinstance(raw_track, dict):
            raise ConfigError(f"tracks entry {index} must be a table")
        _expect_exact_keys(
            raw_track, {"number", "title", "file", "declared_master_status"}, f"tracks[{index}]"
        )
        number = raw_track["number"]
        if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
            raise ConfigError(f"tracks[{index}].number must be a positive integer")
        tracks.append(
            TrackPlan(
                number=number,
                title=_string(raw_track, "title", f"tracks[{index}]"),
                relative_path=_parse_relative_path(
                    _string(raw_track, "file", f"tracks[{index}]"),
                    f"tracks[{index}].file",
                ),
                declared_master_status=_state(
                    raw_track,
                    "declared_master_status",
                    f"tracks[{index}]",
                    MASTER_STATES,
                ),
            )
        )

    numbers = sorted(track.number for track in tracks)
    if numbers != list(range(1, len(tracks) + 1)):
        raise ConfigError("track numbers must be contiguous, start at 1, and not repeat")
    return tuple(sorted(tracks, key=lambda track: track.number))


def _mapping(document: dict[str, Any], key: str, location: str) -> dict[str, Any]:
    value = document.get(key)
    if not isinstance(value, dict):
        raise ConfigError(f"{location}.{key} must be a table")
    return value


def _expect_exact_keys(document: dict[str, Any], expected: set[str], location: str) -> None:
    present = set(document)
    missing = sorted(expected - present)
    unexpected = sorted(present - expected)
    if missing:
        raise ConfigError(f"{location} is missing required field(s): {', '.join(missing)}")
    if unexpected:
        raise ConfigError(f"{location} has unknown field(s): {', '.join(unexpected)}")


def _string(document: dict[str, Any], key: str, location: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{location}.{key} must be a non-empty string")
    return value.strip()


def _state(document: dict[str, Any], key: str, location: str, allowed: frozenset[str]) -> str:
    value = _string(document, key, location)
    if value not in allowed:
        choices = ", ".join(sorted(allowed))
        raise ConfigError(f"{location}.{key} must be one of: {choices}")
    return value


def _parse_relative_path(value: str, location: str) -> PurePosixPath:
    if "\\" in value:
        raise ConfigError(f"{location} must use relative POSIX-style paths")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ConfigError(f"{location} must stay inside release directory")
    return path
