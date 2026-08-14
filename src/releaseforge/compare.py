"""Read-only semantic comparison for two local Releaseforge proof packets."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from releaseforge.report import packet_proof_id

ChangeCategory = Literal[
    "verified_asset",
    "declared_release",
    "declared_profile",
    "declaration",
    "decision",
    "finding",
]

_CATEGORY_ORDER = {
    "verified_asset": 0,
    "declared_release": 1,
    "declared_profile": 2,
    "declaration": 3,
    "decision": 4,
    "finding": 5,
}
_ASSET_FACT_FIELDS = (
    "byte_size",
    "extension",
    "width",
    "height",
    "image_mode",
    "duration_seconds",
    "sample_rate",
    "channels",
    "sample_width_bytes",
)
_PACKET_FIELDS = frozenset(
    {
        "schema_version",
        "proof_id",
        "boundary",
        "decision",
        "release",
        "requirements",
        "declarations",
        "assets",
        "findings",
    }
)
_RELEASE_FIELDS = frozenset(
    {"title", "artist", "catalogue_number", "planned_release_date", "evidence_category"}
)
_REQUIREMENT_FIELDS = frozenset(
    {
        "minimum_cover_pixels",
        "require_square_cover",
        "allowed_audio_extensions",
        "evidence_category",
        "note",
    }
)
_DECLARATION_NAMES = frozenset({"rights_review", "metadata_review", "artwork_approval"})
_DECLARATION_FIELDS = frozenset({"value", "evidence_category", "note"})
_ASSET_FIELDS = frozenset(
    {
        "role",
        "relative_path",
        "evidence_category",
        "byte_size",
        "sha256",
        "extension",
        "width",
        "height",
        "image_mode",
        "duration_seconds",
        "sample_rate",
        "channels",
        "sample_width_bytes",
    }
)
_FINDING_FIELDS = frozenset({"code", "severity", "evidence_category", "message", "subject"})
_DECISION_FIELDS = frozenset(
    {"state", "profile_checked", "blocker_count", "warning_count", "needs_evidence_count"}
)


class ComparisonError(ValueError):
    """Raised when a local proof packet cannot be safely compared."""


@dataclass(frozen=True)
class Packet:
    """One validated packet whose ID matches its captured content."""

    proof_id: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class Change:
    """One captured difference without an inference about which version is correct."""

    code: str
    category: ChangeCategory
    subject: str
    before: object | None
    after: object | None


@dataclass(frozen=True)
class Comparison:
    """A stable, source-path-free change list for two validated proof packets."""

    before_proof_id: str
    after_proof_id: str
    changes: tuple[Change, ...]

    @property
    def is_equal(self) -> bool:
        return not self.changes


def load_packet(path: Path | str) -> Packet:
    """Load a direct packet JSON file or a directory containing one, without writing anything."""
    requested = Path(path)
    packet_path = requested / "RELEASE_PROOF.json" if requested.is_dir() else requested
    try:
        payload = json.loads(packet_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ComparisonError("proof packet does not exist") from error
    except OSError as error:
        raise ComparisonError(f"could not read proof packet: {error}") from error
    except json.JSONDecodeError as error:
        raise ComparisonError("proof packet is not valid JSON") from error

    _validate_packet_payload(payload)
    stored_proof_id = payload["proof_id"]
    computed_proof_id = packet_proof_id(payload)
    if stored_proof_id != computed_proof_id:
        raise ComparisonError("proof ID does not match packet contents")
    return Packet(proof_id=stored_proof_id, payload=payload)


def compare_packets(before: Packet, after: Packet) -> Comparison:
    """Return every semantic difference between validated packets in stable order."""
    if before.proof_id == after.proof_id:
        return Comparison(before.proof_id, after.proof_id, ())

    changes: list[Change] = []
    _compare_mapping(
        before.payload["release"],
        after.payload["release"],
        category="declared_release",
        code="release_value_changed",
        ignore={"evidence_category"},
        changes=changes,
    )
    _compare_mapping(
        before.payload["requirements"],
        after.payload["requirements"],
        category="declared_profile",
        code="requirement_value_changed",
        ignore={"evidence_category", "note"},
        changes=changes,
    )
    _compare_declarations(before.payload["declarations"], after.payload["declarations"], changes)
    _compare_assets(before.payload["assets"], after.payload["assets"], changes)
    _compare_decision(before.payload["decision"], after.payload["decision"], changes)
    _compare_findings(before.payload["findings"], after.payload["findings"], changes)
    return Comparison(
        before_proof_id=before.proof_id,
        after_proof_id=after.proof_id,
        changes=tuple(sorted(changes, key=_change_sort_key)),
    )


def comparison_payload(comparison: Comparison) -> dict[str, Any]:
    """Return a machine-readable comparison without either local packet path."""
    category_counts = {
        category: sum(change.category == category for change in comparison.changes)
        for category in _CATEGORY_ORDER
    }
    return {
        "schema_version": 1,
        "before_proof_id": comparison.before_proof_id,
        "after_proof_id": comparison.after_proof_id,
        "equivalent": comparison.is_equal,
        "change_count": len(comparison.changes),
        "category_counts": category_counts,
        "changes": [
            {
                "code": change.code,
                "category": change.category,
                "subject": change.subject,
                "before": change.before,
                "after": change.after,
            }
            for change in comparison.changes
        ],
    }


def render_comparison_text(comparison: Comparison) -> str:
    """Render concise human-facing output without source packet locations."""
    payload = comparison_payload(comparison)
    lines = [
        "RELEASE PROOF COMPARISON",
        f"Before: {payload['before_proof_id']}",
        f"After:  {payload['after_proof_id']}",
    ]
    if payload["equivalent"]:
        lines.append("Result: equivalent captured packet content.")
        return "\n".join(lines)

    lines.append(f"Result: {payload['change_count']} captured change(s).")
    for change in payload["changes"]:
        lines.append(f"- {change['category'].upper()} | {change['subject']} | {change['code']}")
        lines.append(f"  before: {_display_value(change['before'])}")
        lines.append(f"  after:  {_display_value(change['after'])}")
    return "\n".join(lines)


def _validate_packet_payload(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise ComparisonError("proof packet root must be an object")
    _validate_fields(payload, "proof packet", _PACKET_FIELDS)
    if payload.get("schema_version") != 1:
        raise ComparisonError("proof packet schema_version must be 1")
    proof_id = payload.get("proof_id")
    if not isinstance(proof_id, str) or not proof_id.startswith("rfp_"):
        raise ComparisonError("proof packet has no valid proof ID")
    _validate_fields(
        _mapping(payload["release"], "proof packet release"),
        "proof packet release",
        _RELEASE_FIELDS,
    )
    _validate_fields(
        _mapping(payload["requirements"], "proof packet requirements"),
        "proof packet requirements",
        _REQUIREMENT_FIELDS,
    )
    _validate_fields(
        _mapping(payload["decision"], "proof packet decision"),
        "proof packet decision",
        _DECISION_FIELDS,
    )
    for key in ("assets", "findings"):
        if not isinstance(payload.get(key), list):
            raise ComparisonError(f"proof packet {key} must be a list")
    _validate_assets(payload["assets"])
    _validate_findings(payload["findings"])
    _validate_declarations(payload["declarations"])


def _validate_assets(assets: list[Any]) -> None:
    roles: set[str] = set()
    for asset in assets:
        mapping = _mapping(asset, "proof packet asset")
        _validate_fields(mapping, "proof packet asset", _ASSET_FIELDS)
        for key in ("role", "relative_path", "sha256"):
            if not isinstance(mapping.get(key), str) or not mapping[key]:
                raise ComparisonError(f"proof packet asset {key} must be a non-empty string")
        _validate_relative_asset_path(mapping["relative_path"])
        if mapping["role"] in roles:
            raise ComparisonError("proof packet asset roles must be unique")
        roles.add(mapping["role"])


def _validate_findings(findings: list[Any]) -> None:
    for finding in findings:
        mapping = _mapping(finding, "proof packet finding")
        _validate_fields(mapping, "proof packet finding", _FINDING_FIELDS)
        for key in ("code", "severity", "evidence_category", "message", "subject"):
            if not isinstance(mapping.get(key), str):
                raise ComparisonError(f"proof packet finding {key} must be a string")


def _validate_declarations(declarations: Any) -> None:
    declaration_map = _mapping(declarations, "proof packet declarations")
    _validate_fields(declaration_map, "proof packet declarations", _DECLARATION_NAMES)
    for name, declaration in declaration_map.items():
        mapping = _mapping(declaration, f"proof packet declaration {name}")
        _validate_fields(mapping, f"proof packet declaration {name}", _DECLARATION_FIELDS)
        if not isinstance(mapping.get("value"), str):
            raise ComparisonError(f"proof packet declaration {name} value must be a string")


def _validate_relative_asset_path(relative_path: str) -> None:
    path = PurePosixPath(relative_path)
    has_windows_drive = len(relative_path) > 1 and relative_path[1] == ":"
    if (
        "\\" in relative_path
        or path.is_absolute()
        or ".." in path.parts
        or relative_path == "."
        or has_windows_drive
    ):
        raise ComparisonError("proof packet relative asset path is not a safe POSIX-relative path")


def _compare_mapping(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    *,
    category: ChangeCategory,
    code: str,
    ignore: set[str],
    changes: list[Change],
) -> None:
    names = sorted((set(before) | set(after)) - ignore)
    for name in names:
        before_value = before.get(name)
        after_value = after.get(name)
        if before_value != after_value:
            changes.append(
                Change(
                    code=code,
                    category=category,
                    subject=name,
                    before=before_value,
                    after=after_value,
                )
            )


def _compare_declarations(
    before: Mapping[str, Any], after: Mapping[str, Any], changes: list[Change]
) -> None:
    for name in sorted(set(before) | set(after)):
        before_value = _declaration_value(before.get(name))
        after_value = _declaration_value(after.get(name))
        if before_value != after_value:
            changes.append(
                Change(
                    code="declaration_value_changed",
                    category="declaration",
                    subject=name,
                    before=before_value,
                    after=after_value,
                )
            )


def _compare_assets(before: list[Any], after: list[Any], changes: list[Change]) -> None:
    before_assets = _asset_map(before)
    after_assets = _asset_map(after)
    for role in sorted(set(before_assets) | set(after_assets)):
        before_asset = before_assets.get(role)
        after_asset = after_assets.get(role)
        if before_asset is None:
            changes.append(
                Change(
                    code="asset_added",
                    category="verified_asset",
                    subject=role,
                    before=None,
                    after=_asset_summary(after_asset),
                )
            )
            continue
        if after_asset is None:
            changes.append(
                Change(
                    code="asset_removed",
                    category="verified_asset",
                    subject=role,
                    before=_asset_summary(before_asset),
                    after=None,
                )
            )
            continue
        if before_asset["sha256"] != after_asset["sha256"]:
            changes.append(
                Change(
                    code="asset_bytes_changed",
                    category="verified_asset",
                    subject=role,
                    before=before_asset["sha256"],
                    after=after_asset["sha256"],
                )
            )
        if before_asset["relative_path"] != after_asset["relative_path"]:
            changes.append(
                Change(
                    code="asset_relative_path_changed",
                    category="verified_asset",
                    subject=role,
                    before=before_asset["relative_path"],
                    after=after_asset["relative_path"],
                )
            )
        before_facts = {field: before_asset.get(field) for field in _ASSET_FACT_FIELDS}
        after_facts = {field: after_asset.get(field) for field in _ASSET_FACT_FIELDS}
        if before_facts != after_facts:
            changes.append(
                Change(
                    code="asset_facts_changed",
                    category="verified_asset",
                    subject=role,
                    before=before_facts,
                    after=after_facts,
                )
            )


def _compare_decision(
    before: Mapping[str, Any], after: Mapping[str, Any], changes: list[Change]
) -> None:
    if before != after:
        changes.append(
            Change(
                code="decision_changed",
                category="decision",
                subject="release",
                before=dict(before),
                after=dict(after),
            )
        )


def _compare_findings(before: list[Any], after: list[Any], changes: list[Change]) -> None:
    before_findings = {_finding_key(finding): finding for finding in before}
    after_findings = {_finding_key(finding): finding for finding in after}
    for key in sorted(set(before_findings) - set(after_findings)):
        finding = before_findings[key]
        changes.append(
            Change(
                code="finding_removed",
                category="finding",
                subject=finding["subject"],
                before=_finding_summary(finding),
                after=None,
            )
        )
    for key in sorted(set(after_findings) - set(before_findings)):
        finding = after_findings[key]
        changes.append(
            Change(
                code="finding_added",
                category="finding",
                subject=finding["subject"],
                before=None,
                after=_finding_summary(finding),
            )
        )


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ComparisonError(f"{label} must be an object")
    return value


def _validate_fields(mapping: Mapping[str, Any], label: str, expected: frozenset[str]) -> None:
    fields = set(mapping)
    if fields - expected:
        raise ComparisonError(f"{label} has an unexpected field")
    if expected - fields:
        raise ComparisonError(f"{label} is missing a required field")


def _asset_map(assets: list[Any]) -> dict[str, dict[str, Any]]:
    return {asset["role"]: asset for asset in assets}


def _asset_summary(asset: dict[str, Any] | None) -> dict[str, Any] | None:
    if asset is None:
        return None
    return {
        "relative_path": asset["relative_path"],
        "sha256": asset["sha256"],
        "byte_size": asset.get("byte_size"),
    }


def _finding_summary(finding: dict[str, Any]) -> dict[str, str]:
    """Return only stable finding identifiers, excluding free-form message text."""
    return {
        "code": finding["code"],
        "severity": finding["severity"],
        "evidence_category": finding["evidence_category"],
        "subject": finding["subject"],
    }


def _declaration_value(value: Any) -> str | None:
    if value is None:
        return None
    return value["value"]


def _finding_key(finding: dict[str, Any]) -> str:
    return json.dumps(finding, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _change_sort_key(change: Change) -> tuple[int, str, str, str, str]:
    return (
        _CATEGORY_ORDER[change.category],
        change.subject,
        change.code,
        _display_value(change.before),
        _display_value(change.after),
    )


def _display_value(value: object | None) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
