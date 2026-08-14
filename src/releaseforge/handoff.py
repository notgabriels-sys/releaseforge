"""Strict local intake for portable companion build manifests."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class HandoffError(ValueError):
    """Raised when a companion handoff input is unsafe or unsupported."""


@dataclass(frozen=True)
class MastergateMeasurement:
    """Safe captured PCM-WAV facts retained from one Mastergate manifest."""

    filename: str
    sha256: str
    byte_size: int
    sample_rate_hz: int
    bit_depth: int
    channels: int
    frame_count: int
    duration_seconds: float
    sample_peak_dbfs: float | None
    full_scale_sample_count: int


@dataclass(frozen=True)
class MastergateManifest:
    """The subset of a passing Mastergate build manifest safe for reconciliation."""

    manifest_sha256: str
    measurements: tuple[MastergateMeasurement, ...]


@dataclass(frozen=True)
class ReleaseledgerTrack:
    """A declared track value captured in a Releaseledger build manifest."""

    number: int
    title: str


@dataclass(frozen=True)
class ReleaseledgerManifest:
    """The shared declared metadata retained from a Releaseledger build manifest."""

    manifest_sha256: str
    artist: str
    title: str
    catalogue_number: str
    release_date: str | None
    tracks: tuple[ReleaseledgerTrack, ...]


_MASTERGATE_FIELDS = frozenset(
    {
        "contract",
        "contract_source",
        "declared_file_checks_passed",
        "errors",
        "input",
        "measurements",
        "overall_delivery_verdict",
        "schema_version",
    }
)
_MASTERGATE_CONTRACT_FIELDS = frozenset({"assets", "delivery", "format", "limits"})
_MASTERGATE_ASSET_FIELDS = frozenset({"expected_files"})
_MASTERGATE_DELIVERY_FIELDS = frozenset({"requirements_basis", "title"})
_MASTERGATE_FORMAT_FIELDS = frozenset({"bit_depth", "channels", "sample_rate_hz"})
_MASTERGATE_LIMIT_FIELDS = frozenset({"max_sample_peak_dbfs", "reject_full_scale_samples"})
_MASTERGATE_CONTRACT_SOURCE_FIELDS = frozenset({"filename", "sha256"})
_MASTERGATE_INPUT_FIELDS = frozenset({"directory_name"})
_MASTERGATE_MEASUREMENT_FIELDS = frozenset(
    {
        "bit_depth",
        "byte_size",
        "channels",
        "duration_seconds",
        "filename",
        "frame_count",
        "full_scale_sample_count",
        "sample_peak_dbfs",
        "sample_rate_hz",
        "sha256",
    }
)
_MASTERGATE_VERDICT = "RENDERED - QC INCOMPLETE"

_RELEASELEDGER_FIELDS = frozenset({"files", "release", "schema_version", "source", "tracks"})
_RELEASELEDGER_RELEASE_FIELDS = frozenset(
    {"artist", "catalog_number", "kind", "label", "release_date", "title"}
)
_RELEASELEDGER_SOURCE_FIELDS = frozenset({"filename", "sha256"})
_RELEASELEDGER_TRACK_FIELDS = frozenset({"duration", "isrc", "number", "title"})
_RELEASELEDGER_FILES = (
    "PLATFORM_CHECKLIST.md",
    "RELEASE.md",
    "manifest.json",
    "tracks.csv",
)


def load_mastergate_manifest(path: Path | str) -> MastergateManifest:
    """Load a passing version-1 Mastergate build manifest without retaining paths."""
    payload, manifest_sha256 = _load_json_object(path, "Mastergate manifest")
    _expect_exact_keys(payload, _MASTERGATE_FIELDS, "Mastergate manifest")
    if payload["schema_version"] != 1:
        raise HandoffError("Mastergate manifest schema_version must be 1")
    if payload["declared_file_checks_passed"] is not True:
        raise HandoffError("Mastergate manifest must record passing declared file checks")
    if payload["overall_delivery_verdict"] != _MASTERGATE_VERDICT:
        raise HandoffError("Mastergate manifest has an unsupported delivery verdict")
    if not _string_list(payload["errors"], "Mastergate manifest errors") == ():
        raise HandoffError("passing Mastergate manifest must not contain errors")

    contract = _mapping(payload["contract"], "Mastergate manifest contract")
    _expect_exact_keys(contract, _MASTERGATE_CONTRACT_FIELDS, "Mastergate manifest contract")
    _parse_mastergate_contract(contract)
    _parse_source_fingerprint(
        payload["contract_source"], _MASTERGATE_CONTRACT_SOURCE_FIELDS, "Mastergate contract source"
    )
    _parse_named_input(payload["input"], "Mastergate input")
    measurements = _parse_mastergate_measurements(payload["measurements"])
    return MastergateManifest(manifest_sha256=manifest_sha256, measurements=measurements)


def load_releaseledger_manifest(path: Path | str) -> ReleaseledgerManifest:
    """Load a version-1 Releaseledger build manifest without retaining source paths."""
    payload, manifest_sha256 = _load_json_object(path, "Releaseledger manifest")
    _expect_exact_keys(payload, _RELEASELEDGER_FIELDS, "Releaseledger manifest")
    if payload["schema_version"] != 1:
        raise HandoffError("Releaseledger manifest schema_version must be 1")
    if payload["files"] != list(_RELEASELEDGER_FILES):
        raise HandoffError("Releaseledger manifest has unsupported output files")

    release = _mapping(payload["release"], "Releaseledger manifest release")
    _expect_exact_keys(release, _RELEASELEDGER_RELEASE_FIELDS, "Releaseledger manifest release")
    _parse_source_fingerprint(
        payload["source"], _RELEASELEDGER_SOURCE_FIELDS, "Releaseledger source"
    )
    tracks = _parse_releaseledger_tracks(payload["tracks"])
    return ReleaseledgerManifest(
        manifest_sha256=manifest_sha256,
        artist=_nonblank_string(release["artist"], "Releaseledger manifest release.artist"),
        title=_nonblank_string(release["title"], "Releaseledger manifest release.title"),
        catalogue_number=_nonblank_string(
            release["catalog_number"], "Releaseledger manifest release.catalog_number"
        ),
        release_date=_optional_string(
            release["release_date"], "Releaseledger manifest release.release_date"
        ),
        tracks=tracks,
    )


def _load_json_object(path: Path | str, label: str) -> tuple[dict[str, Any], str]:
    requested = Path(path)
    try:
        raw = requested.read_bytes()
    except FileNotFoundError as error:
        raise HandoffError(f"{label} does not exist") from error
    except OSError as error:
        raise HandoffError(f"could not read {label}: {error}") from error
    try:
        payload = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise HandoffError(f"{label} must be UTF-8 JSON") from error
    except json.JSONDecodeError as error:
        raise HandoffError(f"{label} is not valid JSON") from error
    if not isinstance(payload, dict):
        raise HandoffError(f"{label} root must be an object")
    return payload, hashlib.sha256(raw).hexdigest()


def _parse_mastergate_contract(contract: dict[str, Any]) -> None:
    assets = _mapping(contract["assets"], "Mastergate manifest contract.assets")
    _expect_exact_keys(assets, _MASTERGATE_ASSET_FIELDS, "Mastergate manifest contract.assets")
    expected_files = _string_list(assets["expected_files"], "Mastergate expected files")
    if not expected_files:
        raise HandoffError("Mastergate expected files must be bare WAV filenames")
    for expected_file in expected_files:
        _bare_wav_filename(expected_file, "Mastergate expected file")

    delivery = _mapping(contract["delivery"], "Mastergate manifest contract.delivery")
    _expect_exact_keys(
        delivery, _MASTERGATE_DELIVERY_FIELDS, "Mastergate manifest contract.delivery"
    )
    _nonblank_string(delivery["requirements_basis"], "Mastergate requirements basis")
    _nonblank_string(delivery["title"], "Mastergate delivery title")

    audio_format = _mapping(contract["format"], "Mastergate manifest contract.format")
    _expect_exact_keys(
        audio_format, _MASTERGATE_FORMAT_FIELDS, "Mastergate manifest contract.format"
    )
    _positive_int(audio_format["bit_depth"], "Mastergate bit depth")
    _positive_int(audio_format["channels"], "Mastergate channels")
    _positive_int(audio_format["sample_rate_hz"], "Mastergate sample rate")

    limits = _mapping(contract["limits"], "Mastergate manifest contract.limits")
    _expect_exact_keys(limits, _MASTERGATE_LIMIT_FIELDS, "Mastergate manifest contract.limits")
    _optional_number(limits["max_sample_peak_dbfs"], "Mastergate max sample peak")
    if not isinstance(limits["reject_full_scale_samples"], bool):
        raise HandoffError("Mastergate reject_full_scale_samples must be boolean")


def _parse_source_fingerprint(value: Any, fields: frozenset[str], label: str) -> None:
    source = _mapping(value, label)
    _expect_exact_keys(source, fields, label)
    _bare_filename(source["filename"], f"{label} filename")
    _sha256(source["sha256"], f"{label} SHA-256")


def _parse_named_input(value: Any, label: str) -> None:
    input_value = _mapping(value, label)
    _expect_exact_keys(input_value, _MASTERGATE_INPUT_FIELDS, label)
    _bare_filename(input_value["directory_name"], f"{label} directory name")


def _parse_mastergate_measurements(value: Any) -> tuple[MastergateMeasurement, ...]:
    if not isinstance(value, list) or not value:
        raise HandoffError("Mastergate measurements must be a non-empty list")
    measurements: list[MastergateMeasurement] = []
    for index, raw_measurement in enumerate(value, start=1):
        label = f"Mastergate measurement {index}"
        measurement = _mapping(raw_measurement, label)
        _expect_exact_keys(measurement, _MASTERGATE_MEASUREMENT_FIELDS, label)
        measurements.append(
            MastergateMeasurement(
                filename=_bare_wav_filename(measurement["filename"], f"{label} filename"),
                sha256=_sha256(measurement["sha256"], f"{label} SHA-256"),
                byte_size=_positive_int(measurement["byte_size"], f"{label} byte size"),
                sample_rate_hz=_positive_int(measurement["sample_rate_hz"], f"{label} sample rate"),
                bit_depth=_positive_int(measurement["bit_depth"], f"{label} bit depth"),
                channels=_positive_int(measurement["channels"], f"{label} channels"),
                frame_count=_positive_int(measurement["frame_count"], f"{label} frame count"),
                duration_seconds=_nonnegative_number(
                    measurement["duration_seconds"], f"{label} duration"
                ),
                sample_peak_dbfs=_optional_number(
                    measurement["sample_peak_dbfs"], f"{label} sample peak"
                ),
                full_scale_sample_count=_nonnegative_int(
                    measurement["full_scale_sample_count"], f"{label} full-scale count"
                ),
            )
        )
    return tuple(measurements)


def _parse_releaseledger_tracks(value: Any) -> tuple[ReleaseledgerTrack, ...]:
    if not isinstance(value, list) or not value:
        raise HandoffError("Releaseledger tracks must be a non-empty list")
    tracks: list[ReleaseledgerTrack] = []
    for index, raw_track in enumerate(value, start=1):
        label = f"Releaseledger track {index}"
        track = _mapping(raw_track, label)
        _expect_exact_keys(track, _RELEASELEDGER_TRACK_FIELDS, label)
        _optional_string(track["duration"], f"{label} duration")
        _optional_string(track["isrc"], f"{label} ISRC")
        tracks.append(
            ReleaseledgerTrack(
                number=_positive_int(track["number"], f"{label} number"),
                title=_nonblank_string(track["title"], f"{label} title"),
            )
        )
    numbers = [track.number for track in tracks]
    if numbers != list(range(1, len(tracks) + 1)):
        raise HandoffError("Releaseledger track numbers must be contiguous and start at 1")
    return tuple(tracks)


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HandoffError(f"{label} must be an object")
    return value


def _expect_exact_keys(mapping: dict[str, Any], expected: frozenset[str], label: str) -> None:
    fields = set(mapping)
    if fields - expected:
        raise HandoffError(f"{label} has an unexpected field")
    if expected - fields:
        raise HandoffError(f"{label} is missing a required field")


def _string_list(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise HandoffError(f"{label} must be a list of strings")
    return tuple(value)


def _nonblank_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HandoffError(f"{label} must be a non-empty string")
    return value.strip()


def _optional_string(value: Any, label: str) -> str | None:
    if value is None:
        return None
    return _nonblank_string(value, label)


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise HandoffError(f"{label} must be a positive integer")
    return value


def _nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HandoffError(f"{label} must be a non-negative integer")
    return value


def _optional_number(value: Any, label: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise HandoffError(f"{label} must be a finite number or null")
    return float(value)


def _nonnegative_number(value: Any, label: str) -> float:
    parsed = _optional_number(value, label)
    if parsed is None or parsed < 0:
        raise HandoffError(f"{label} must be a non-negative finite number")
    return parsed


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise HandoffError(f"{label} must be a lowercase SHA-256 string")
    try:
        int(value, 16)
    except ValueError as error:
        raise HandoffError(f"{label} must be a lowercase SHA-256 string") from error
    if value != value.lower():
        raise HandoffError(f"{label} must be a lowercase SHA-256 string")
    return value


def _bare_wav_filename(value: Any, label: str) -> str:
    filename = _bare_filename(value, label)
    if not filename.lower().endswith(".wav"):
        raise HandoffError(f"{label} must be a bare WAV filename")
    return filename


def _bare_filename(value: Any, label: str) -> str:
    filename = _nonblank_string(value, label)
    if filename.startswith(".") or "/" in filename or "\\" in filename or filename in {".", ".."}:
        raise HandoffError(f"{label} must be a bare filename")
    return filename
