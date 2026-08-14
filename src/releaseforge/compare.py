"""Read-only semantic comparison for two local Releaseforge proof packets."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from html import escape
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
_COMPARISON_BOUNDARY = (
    "This comparison records captured differences between two local proof packets. "
    "It does not establish approval, ownership, rights, distributor acceptance, "
    "release readiness, or which packet is correct."
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
    payload = {
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
    payload["comparison_id"] = comparison_id(payload)
    return payload


def comparison_id(payload: Mapping[str, Any]) -> str:
    """Return a stable identifier for comparison content excluding its own ID field."""
    canonical_payload = {key: value for key, value in payload.items() if key != "comparison_id"}
    encoded = json.dumps(
        canonical_payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"rfc_{hashlib.sha256(encoded).hexdigest()[:20]}"


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


def render_comparison_markdown(comparison: Comparison) -> str:
    """Render a portable review record from one captured comparison model."""
    payload = comparison_payload(comparison)
    lines = [
        "# Releaseforge local proof comparison",
        "",
        f"**Comparison ID: `{payload['comparison_id']}`**",
        "",
        f"> **Boundary:** {_markdown_value(_COMPARISON_BOUNDARY)}",
        "",
        "## Captured packets",
        "",
        "| Before proof ID | After proof ID |",
        "| --- | --- |",
        f"| `{payload['before_proof_id']}` | `{payload['after_proof_id']}` |",
        "",
        "## Result",
        "",
        "| Equivalent captured content | Captured changes |",
        "| --- | ---: |",
        f"| {payload['equivalent']} | {payload['change_count']} |",
        "",
        "## Captured changes",
        "",
    ]
    if payload["equivalent"]:
        lines.append("No captured differences were emitted.")
        return "\n".join(lines)

    lines.extend(
        [
            "| Evidence category | Subject | Change | Before | After |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for change in payload["changes"]:
        lines.append(
            "| "
            f"{_markdown_value(change['category'])} | "
            f"{_markdown_value(change['subject'])} | "
            f"{_markdown_value(change['code'])} | "
            f"{_markdown_value(change['before'])} | "
            f"{_markdown_value(change['after'])} |"
        )
    return "\n".join(lines)


def render_comparison_html(comparison: Comparison) -> str:
    """Render one self-contained offline comparison review surface."""
    payload = comparison_payload(comparison)
    result = "Equivalent captured content" if payload["equivalent"] else "Captured changes"
    state_class = "equivalent" if payload["equivalent"] else "changed"
    if payload["changes"]:
        change_rows = "".join(_comparison_html_row(change) for change in payload["changes"])
    else:
        change_rows = '<tr><td colspan="5">No captured differences were emitted.</td></tr>'
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>Releaseforge comparison {escape(payload["comparison_id"])}</title>
  <style>
    :root {{ color-scheme: dark; --ink: #101116; --surface: #181a21; --bone: #f1ede3; --muted: #aaa79f; --line: #343844; --accent: #bf9a63; --changed: #e5ba68; --ok: #8fcda0; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: radial-gradient(circle at top right, #24212d 0, var(--ink) 40rem); color: var(--bone); font: 16px/1.5 ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 48px 24px 72px; }}
    header {{ border-bottom: 1px solid var(--line); padding-bottom: 28px; margin-bottom: 28px; }}
    .eyebrow {{ color: var(--accent); font-size: .75rem; letter-spacing: .13em; text-transform: uppercase; }}
    h1 {{ margin: 8px 0 10px; font: 600 clamp(2rem, 6vw, 4.75rem)/.95 system-ui, sans-serif; letter-spacing: -.06em; }}
    h2 {{ margin: 40px 0 12px; font: 600 1rem/1.2 system-ui, sans-serif; letter-spacing: .02em; text-transform: uppercase; }}
    p {{ color: var(--muted); max-width: 76ch; }}
    .result {{ display: inline-flex; border: 1px solid var(--line); padding: .55rem .75rem; background: var(--surface); }}
    .result.changed {{ color: var(--changed); }}
    .result.equivalent {{ color: var(--ok); }}
    .boundary {{ border-left: 3px solid var(--accent); background: #1d1b1b; padding: 14px 16px; }}
    table {{ width: 100%; border-collapse: collapse; background: rgba(24, 26, 33, .78); }}
    th, td {{ text-align: left; vertical-align: top; padding: 11px 12px; border: 1px solid var(--line); }}
    th {{ color: var(--muted); font-size: .72rem; font-weight: 500; text-transform: uppercase; letter-spacing: .08em; }}
    td {{ font-size: .86rem; }}
    code {{ color: #dcc6a1; word-break: break-all; }}
    footer {{ margin-top: 48px; padding-top: 20px; border-top: 1px solid var(--line); color: var(--muted); font-size: .8rem; }}
    @media (max-width: 720px) {{ main {{ padding: 28px 14px 48px; }} table {{ display: block; overflow-x: auto; }} }}
  </style>
</head>
<body>
  <main>
    <header>
      <div class=\"eyebrow\">Local proof comparison · offline packet</div>
      <h1>{escape(result)}</h1>
      <p>Comparison ID: <code>{escape(payload["comparison_id"])}</code></p>
      <div class=\"result {state_class}\">{escape(result)} · {payload["change_count"]} change(s)</div>
    </header>

    <section class=\"boundary\"><strong>Boundary.</strong> {escape(_COMPARISON_BOUNDARY)}</section>

    <h2>Captured packets</h2>
    <table>
      <thead><tr><th>Before proof ID</th><th>After proof ID</th></tr></thead>
      <tbody><tr><td><code>{escape(payload["before_proof_id"])}</code></td><td><code>{escape(payload["after_proof_id"])}</code></td></tr></tbody>
    </table>

    <h2>Captured changes</h2>
    <table>
      <thead><tr><th>Evidence category</th><th>Subject</th><th>Change</th><th>Before</th><th>After</th></tr></thead>
      <tbody>{change_rows}</tbody>
    </table>

    <footer>Generated locally by Releaseforge. It contains no source files and makes no external network request.</footer>
  </main>
</body>
</html>
"""


def write_comparison_packet(
    comparison: Comparison,
    output_dir: Path | str,
    *,
    protected_roots: tuple[Path | str, ...] = (),
) -> Path:
    """Write one new portable comparison packet outside its input proof packet trees."""
    output_path = Path(output_dir).resolve()
    _reject_protected_output(output_path, protected_roots)
    if output_path.exists():
        raise ComparisonError(f"comparison output directory already exists: {output_path.name}")
    try:
        output_path.mkdir(parents=True, exist_ok=False)
        (output_path / "RELEASE_COMPARISON.md").write_text(
            render_comparison_markdown(comparison), encoding="utf-8"
        )
        (output_path / "RELEASE_COMPARISON.json").write_text(
            json.dumps(comparison_payload(comparison), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        (output_path / "RELEASE_COMPARISON.html").write_text(
            render_comparison_html(comparison), encoding="utf-8"
        )
    except OSError as error:
        raise ComparisonError(f"could not write comparison packet: {error}") from error
    return output_path


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


def _reject_protected_output(output_path: Path, protected_roots: tuple[Path | str, ...]) -> None:
    for root in protected_roots:
        try:
            output_path.relative_to(Path(root).resolve())
        except ValueError:
            continue
        raise ComparisonError(
            "comparison output directory must be outside input proof packet directories"
        )


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


def _comparison_html_row(change: dict[str, Any]) -> str:
    return (
        "<tr>"
        f"<td>{escape(str(change['category']))}</td>"
        f"<td>{escape(str(change['subject']))}</td>"
        f"<td>{escape(str(change['code']))}</td>"
        f"<td><code>{escape(_display_value(change['before']))}</code></td>"
        f"<td><code>{escape(_display_value(change['after']))}</code></td>"
        "</tr>"
    )


def _markdown_value(value: object | None) -> str:
    return escape(_display_value(value), quote=False).replace("|", "\\|").replace("\n", " ")


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
