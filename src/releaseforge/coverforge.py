"""Strict local intake for portable Coverforge manifest captures."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class CoverforgeError(ValueError):
    """Raised when a Coverforge companion capture is unsafe or unsupported."""


@dataclass(frozen=True)
class CoverforgeSource:
    """Path-free source facts retained from one Coverforge manifest."""

    sha256: str
    byte_size: int
    width: int
    height: int
    mode: str
    file_format: str


@dataclass(frozen=True)
class CoverforgeOutput:
    """Path-free output facts retained from one Coverforge manifest."""

    target_key: str
    width: int
    height: int
    file_format: str
    byte_size: int
    sha256: str
    over_size_cap: bool


@dataclass(frozen=True)
class CoverforgeManifest:
    """Validated, portable subset of a Coverforge version-1 manifest."""

    manifest_sha256: str
    capture_id: str
    source: CoverforgeSource
    outputs: tuple[CoverforgeOutput, ...]
    skipped_target_keys: tuple[str, ...]
    preflight_finding_count: int


_ROOT_FIELDS = frozenset(
    {
        "schema_version",
        "generated_by",
        "boundary",
        "slug",
        "source",
        "outputs",
        "skipped",
        "findings",
        "capture_id",
    }
)
_SOURCE_FIELDS = frozenset({"sha256", "bytes", "dimensions", "mode", "format"})
_OUTPUT_FIELDS = frozenset(
    {
        "target",
        "name",
        "file",
        "dimensions",
        "format",
        "quality",
        "bytes",
        "size",
        "over_size_cap",
        "sha256",
    }
)
_SKIPPED_FIELDS = frozenset({"target", "reason"})
_FINDING_FIELDS = frozenset({"level", "code", "message", "target"})
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_CAPTURE_ID_PATTERN = re.compile(r"^cfp_[0-9a-f]{20}$")
_DIMENSIONS_PATTERN = re.compile(r"^([1-9][0-9]*)x([1-9][0-9]*)$")
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_IMAGE_MODE_PATTERN = re.compile(r"^[A-Za-z0-9;]+$")


def load_coverforge_manifest(path: Path | str) -> CoverforgeManifest:
    """Load one strict, path-free Coverforge version-1 manifest capture."""
    payload, manifest_sha256 = _load_json_object(path)
    _expect_exact_keys(payload, _ROOT_FIELDS, "Coverforge manifest")
    if payload["schema_version"] != 1:
        raise CoverforgeError("Coverforge manifest schema_version must be 1")
    if payload["generated_by"] != "coverforge":
        raise CoverforgeError("Coverforge manifest generated_by must be coverforge")
    _nonblank_text(payload["boundary"], "Coverforge manifest boundary")
    _safe_slug(payload["slug"])
    capture_id = _validate_capture_id(payload)
    source = _parse_source(payload["source"])
    outputs = _parse_outputs(payload["outputs"])
    skipped_target_keys = _parse_skipped(payload["skipped"], {item.target_key for item in outputs})
    _validate_findings(payload["findings"])
    return CoverforgeManifest(
        manifest_sha256=manifest_sha256,
        capture_id=capture_id,
        source=source,
        outputs=outputs,
        skipped_target_keys=skipped_target_keys,
        preflight_finding_count=len(payload["findings"]),
    )


def _load_json_object(path: Path | str) -> tuple[dict[str, Any], str]:
    requested = Path(path)
    try:
        raw = requested.read_bytes()
    except FileNotFoundError as error:
        raise CoverforgeError("Coverforge manifest does not exist") from error
    except OSError as error:
        raise CoverforgeError(f"could not read Coverforge manifest: {error}") from error
    try:
        payload = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise CoverforgeError("Coverforge manifest must be UTF-8 JSON") from error
    except json.JSONDecodeError as error:
        raise CoverforgeError("Coverforge manifest is not valid JSON") from error
    if not isinstance(payload, dict):
        raise CoverforgeError("Coverforge manifest root must be an object")
    return payload, hashlib.sha256(raw).hexdigest()


def _validate_capture_id(payload: Mapping[str, Any]) -> str:
    capture_id = payload.get("capture_id")
    if not isinstance(capture_id, str) or not _CAPTURE_ID_PATTERN.fullmatch(capture_id):
        raise CoverforgeError("Coverforge manifest capture_id is invalid")
    if capture_id != _canonical_capture_id(payload):
        raise CoverforgeError("Coverforge manifest capture_id does not match its content")
    return capture_id


def _canonical_capture_id(payload: Mapping[str, Any]) -> str:
    canonical = {key: value for key, value in payload.items() if key != "capture_id"}
    encoded = json.dumps(
        canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return f"cfp_{hashlib.sha256(encoded).hexdigest()[:20]}"


def _parse_source(value: Any) -> CoverforgeSource:
    source = _mapping(value, "Coverforge manifest source")
    _expect_exact_keys(source, _SOURCE_FIELDS, "Coverforge manifest source")
    width, height = _dimensions(source["dimensions"], "Coverforge manifest source dimensions")
    return CoverforgeSource(
        sha256=_sha256(source["sha256"], "Coverforge manifest source SHA-256"),
        byte_size=_positive_int(source["bytes"], "Coverforge manifest source bytes"),
        width=width,
        height=height,
        mode=_image_mode(source["mode"], "Coverforge manifest source mode"),
        file_format=_safe_label(source["format"], "Coverforge manifest source format"),
    )


def _parse_outputs(value: Any) -> tuple[CoverforgeOutput, ...]:
    if not isinstance(value, list) or not value:
        raise CoverforgeError("Coverforge manifest outputs must be a non-empty list")
    outputs: list[CoverforgeOutput] = []
    seen_target_keys: set[str] = set()
    for index, raw_output in enumerate(value, start=1):
        label = f"Coverforge manifest output {index}"
        output = _mapping(raw_output, label)
        _expect_exact_keys(output, _OUTPUT_FIELDS, label)
        target_key = _safe_label(output["target"], f"{label} target")
        if target_key in seen_target_keys:
            raise CoverforgeError("Coverforge manifest output targets must be unique")
        seen_target_keys.add(target_key)
        _nonblank_text(output["name"], f"{label} name")
        _bare_filename(output["file"], f"{label} file")
        width, height = _dimensions(output["dimensions"], f"{label} dimensions")
        file_format = _safe_identifier(output["format"], f"{label} format")
        if file_format not in {"jpeg", "png"}:
            raise CoverforgeError(f"{label} format must be jpeg or png")
        quality = _positive_int(output["quality"], f"{label} quality")
        if quality > 100:
            raise CoverforgeError(f"{label} quality must be at most 100")
        _positive_int(output["bytes"], f"{label} bytes")
        _nonblank_text(output["size"], f"{label} size")
        if not isinstance(output["over_size_cap"], bool):
            raise CoverforgeError(f"{label} over_size_cap must be boolean")
        outputs.append(
            CoverforgeOutput(
                target_key=target_key,
                width=width,
                height=height,
                file_format=file_format,
                byte_size=_positive_int(output["bytes"], f"{label} bytes"),
                sha256=_sha256(output["sha256"], f"{label} SHA-256"),
                over_size_cap=output["over_size_cap"],
            )
        )
    return tuple(outputs)


def _parse_skipped(value: Any, output_target_keys: set[str]) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise CoverforgeError("Coverforge manifest skipped must be a list")
    target_keys: list[str] = []
    for index, raw_skipped in enumerate(value, start=1):
        label = f"Coverforge manifest skipped item {index}"
        skipped = _mapping(raw_skipped, label)
        _expect_exact_keys(skipped, _SKIPPED_FIELDS, label)
        target_key = _safe_label(skipped["target"], f"{label} target")
        if target_key in output_target_keys or target_key in target_keys:
            raise CoverforgeError("Coverforge manifest skipped targets must be unique")
        _nonblank_text(skipped["reason"], f"{label} reason")
        target_keys.append(target_key)
    return tuple(target_keys)


def _validate_findings(value: Any) -> None:
    if not isinstance(value, list):
        raise CoverforgeError("Coverforge manifest findings must be a list")
    for index, raw_finding in enumerate(value, start=1):
        label = f"Coverforge manifest finding {index}"
        finding = _mapping(raw_finding, label)
        _expect_exact_keys(finding, _FINDING_FIELDS, label)
        if finding["level"] not in {"error", "warn", "info"}:
            raise CoverforgeError(f"{label} level is unsupported")
        _safe_identifier(finding["code"], f"{label} code")
        _nonblank_text(finding["message"], f"{label} message")
        target = finding["target"]
        if target is not None:
            _safe_label(target, f"{label} target")


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CoverforgeError(f"{label} must be an object")
    return value


def _expect_exact_keys(mapping: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    fields = set(mapping)
    if fields - expected:
        raise CoverforgeError(f"{label} has an unexpected field")
    if expected - fields:
        raise CoverforgeError(f"{label} is missing a required field")


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_PATTERN.fullmatch(value):
        raise CoverforgeError(f"{label} must be a lowercase SHA-256 string")
    return value


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise CoverforgeError(f"{label} must be a positive integer")
    return value


def _dimensions(value: Any, label: str) -> tuple[int, int]:
    if not isinstance(value, str):
        raise CoverforgeError(f"{label} must be widthxheight text")
    match = _DIMENSIONS_PATTERN.fullmatch(value)
    if match is None:
        raise CoverforgeError(f"{label} must be widthxheight text")
    return int(match.group(1)), int(match.group(2))


def _safe_slug(value: Any) -> None:
    slug = _nonblank_text(value, "Coverforge manifest slug")
    if Path(slug).is_absolute() or "/" in slug or "\\" in slug or slug in {".", ".."}:
        raise CoverforgeError("Coverforge manifest slug must be path-free")


def _safe_identifier(value: Any, label: str) -> str:
    identifier = _nonblank_text(value, label)
    if not _IDENTIFIER_PATTERN.fullmatch(identifier):
        raise CoverforgeError(f"{label} must be a safe identifier")
    return identifier


def _safe_label(value: Any, label: str) -> str:
    label_value = _nonblank_text(value, label)
    if (
        Path(label_value).is_absolute()
        or "/" in label_value
        or "\\" in label_value
        or label_value in {".", ".."}
    ):
        raise CoverforgeError(f"{label} must be path-free")
    return label_value


def _image_mode(value: Any, label: str) -> str:
    mode = _nonblank_text(value, label)
    if not _IMAGE_MODE_PATTERN.fullmatch(mode):
        raise CoverforgeError(f"{label} must be a supported image mode")
    return mode


def _bare_filename(value: Any, label: str) -> str:
    filename = _nonblank_text(value, label)
    if (
        filename.startswith(".")
        or Path(filename).is_absolute()
        or "/" in filename
        or "\\" in filename
        or filename in {".", ".."}
    ):
        raise CoverforgeError(f"{label} must be a bare filename")
    return filename


def _nonblank_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or any(ord(char) < 32 for char in value):
        raise CoverforgeError(f"{label} must be non-empty text without control characters")
    return value
