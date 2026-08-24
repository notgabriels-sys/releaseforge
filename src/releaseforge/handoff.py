"""Strict local intake for portable companion manifest captures."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

from releaseforge.compare import Packet
from releaseforge.coverforge import CoverforgeManifest


class HandoffError(ValueError):
    """Raised when a companion handoff input is unsafe or unsupported."""


@dataclass(frozen=True)
class ReleaseledgerTrack:
    """A declared track value captured in a Releaseledger-compatible manifest."""

    number: int
    title: str


@dataclass(frozen=True)
class ReleaseledgerManifest:
    """Safe metadata captured from a schema-compatible Releaseledger version-1 manifest."""

    manifest_sha256: str
    artist: str
    title: str
    catalogue_number: str
    release_date: str | None
    tracks: tuple[ReleaseledgerTrack, ...]


@dataclass(frozen=True)
class HandoffFinding:
    """One bounded discrepancy between captured companion values."""

    code: str
    severity: str
    evidence_category: str
    subject: str
    message: str


@dataclass(frozen=True)
class ReleaseledgerAlignment:
    """The shared declared metadata relationship with a Releaseledger manifest."""

    matching_fields: tuple[str, ...]
    mismatched_fields: tuple[str, ...]
    matching_track_numbers: tuple[int, ...]
    missing_releaseledger_track_numbers: tuple[int, ...]
    unmatched_releaseledger_track_numbers: tuple[int, ...]


@dataclass(frozen=True)
class CoverforgeLinkage:
    """The captured visual-source relationship with a Coverforge manifest."""

    state: str
    matching_source_fields: tuple[str, ...]
    mismatched_source_fields: tuple[str, ...]
    skipped_target_keys: tuple[str, ...]
    over_size_cap_target_keys: tuple[str, ...]


@dataclass(frozen=True)
class Handoff:
    """One local comparison of validated Releaseforge and companion captures."""

    proof: Packet
    releaseledger: ReleaseledgerManifest | None
    coverforge: CoverforgeManifest | None
    releaseledger_alignment: ReleaseledgerAlignment | None
    coverforge_linkage: CoverforgeLinkage | None
    findings: tuple[HandoffFinding, ...]

    @property
    def is_aligned(self) -> bool:
        """Return true only when all selected captured relationships align."""
        return not self.findings


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
_MARKDOWN_ESCAPES = str.maketrans(
    {character: f"\\{character}" for character in r"\`*_[](){}#!+~-|"}
)
_HANDOFF_BOUNDARY = (
    "This handoff records relationships between a validated Releaseforge proof packet "
    "and selected local Releaseledger- or Coverforge-compatible manifest "
    "captures. Schema recognition and a SHA-256 identify only the local manifest bytes "
    "supplied to this run; they do not authenticate the producer or prove an upstream build "
    "occurred. It does not establish current-file verification, approval, ownership, rights, "
    "external delivery, distributor acceptance, or release readiness."
)


def load_releaseledger_manifest(path: Path | str) -> ReleaseledgerManifest:
    """Load a schema-compatible Releaseledger version-1 manifest without source paths."""
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


def build_handoff(
    proof: Packet,
    *,
    releaseledger: ReleaseledgerManifest | None = None,
    coverforge: CoverforgeManifest | None = None,
) -> Handoff:
    """Reconcile selected captured evidence without reading source media or paths."""
    if releaseledger is None and coverforge is None:
        raise HandoffError("handoff requires at least one companion manifest")

    releaseledger_alignment, releaseledger_findings = _reconcile_releaseledger(proof, releaseledger)
    coverforge_linkage, coverforge_findings = _reconcile_coverforge(proof, coverforge)
    return Handoff(
        proof=proof,
        releaseledger=releaseledger,
        coverforge=coverforge,
        releaseledger_alignment=releaseledger_alignment,
        coverforge_linkage=coverforge_linkage,
        findings=tuple(releaseledger_findings + coverforge_findings),
    )


def handoff_exit_code(handoff: Handoff) -> int:
    """Return the non-error status for an aligned or discrepant local handoff."""
    return 0 if handoff.is_aligned else 1


def handoff_payload(handoff: Handoff) -> dict[str, Any]:
    """Return a deterministic, path-free handoff record from selected captures."""
    proof_assets = handoff.proof.payload.get("assets")
    if not isinstance(proof_assets, list):
        raise HandoffError("Releaseforge proof packet has no valid assets")
    payload: dict[str, Any] = {
        "schema_version": 2,
        "boundary": _HANDOFF_BOUNDARY,
        "releaseforge": {
            "proof_id": handoff.proof.proof_id,
            "release": _proof_release(handoff.proof),
            "decision": _proof_decision(handoff.proof),
            "captured_asset_count": len(proof_assets),
        },
        "releaseledger": _releaseledger_payload(handoff),
        "coverforge": _coverforge_payload(handoff),
        "findings": [
            {
                "code": finding.code,
                "severity": finding.severity,
                "evidence_category": finding.evidence_category,
                "subject": finding.subject,
                "message": finding.message,
            }
            for finding in handoff.findings
        ],
    }
    payload["handoff_id"] = handoff_id(payload)
    return payload


def handoff_id(payload: Mapping[str, Any]) -> str:
    """Return a stable identifier for handoff content excluding its own ID field."""
    canonical_payload = {key: value for key, value in payload.items() if key != "handoff_id"}
    encoded = json.dumps(
        canonical_payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"rfh_{hashlib.sha256(encoded).hexdigest()[:20]}"


def render_handoff_markdown(handoff: Handoff) -> str:
    """Render a portable handoff review record without input locations."""
    payload = handoff_payload(handoff)
    release = payload["releaseforge"]["release"]
    decision = payload["releaseforge"]["decision"]
    lines = [
        "# Releaseforge local companion handoff",
        "",
        f"**Handoff ID: `{payload['handoff_id']}`**",
        "",
        f"> **Boundary:** {_markdown_value(_HANDOFF_BOUNDARY)}",
        "",
        "## Releaseforge proof capture",
        "",
        "| Field | Captured value |",
        "| --- | --- |",
        f"| Proof ID | `{_markdown_value(payload['releaseforge']['proof_id'])}` |",
        f"| Artist | {_markdown_value(release['artist'])} |",
        f"| Title | {_markdown_value(release['title'])} |",
        f"| Catalogue number | {_markdown_value(release['catalogue_number'])} |",
        f"| Planned release date | {_markdown_value(release['planned_release_date'])} |",
        f"| Local decision | {_markdown_value(decision['state'])} |",
        f"| Captured assets | {payload['releaseforge']['captured_asset_count']} |",
        "",
        "## Companion captures",
        "",
    ]
    lines.extend(_markdown_companion_lines(payload))
    lines.extend(["", "## Handoff findings", ""])
    if payload["findings"]:
        lines.extend(
            [
                "| Severity | Subject | Evidence category | Finding |",
                "| --- | --- | --- | --- |",
            ]
        )
        lines.extend(
            "| {severity} | {subject} | {evidence} | {message} |".format(
                severity=_markdown_value(finding["severity"]),
                subject=_markdown_value(finding["subject"]),
                evidence=_markdown_value(finding["evidence_category"]),
                message=_markdown_value(finding["message"]),
            )
            for finding in payload["findings"]
        )
    else:
        lines.append("No captured relationship discrepancy was emitted.")
    return "\n".join(lines) + "\n"


def render_handoff_html(handoff: Handoff) -> str:
    """Render one self-contained offline handoff review surface."""
    payload = handoff_payload(handoff)
    release = payload["releaseforge"]["release"]
    decision = payload["releaseforge"]["decision"]
    findings = payload["findings"]
    finding_rows = "".join(
        _html_row(
            finding["severity"],
            finding["subject"],
            finding["evidence_category"],
            finding["message"],
        )
        for finding in findings
    )
    if not finding_rows:
        finding_rows = (
            '<tr><td colspan="4">No captured relationship discrepancy was emitted.</td></tr>'
        )
    companion_rows = "".join(_html_companion_rows(payload))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Releaseforge handoff {escape(str(payload["handoff_id"]))}</title>
  <style>
    :root {{ color-scheme: dark; --ink: #101116; --surface: #181a21; --bone: #f1ede3; --muted: #aaa79f; --line: #343844; --accent: #bf9a63; --warn: #e5ba68; --ok: #8fcda0; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: radial-gradient(circle at top right, #24212d 0, var(--ink) 40rem); color: var(--bone); font: 16px/1.5 ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 48px 24px 72px; }}
    header {{ border-bottom: 1px solid var(--line); padding-bottom: 28px; margin-bottom: 28px; }}
    .eyebrow {{ color: var(--accent); font-size: .75rem; letter-spacing: .13em; text-transform: uppercase; }}
    h1 {{ margin: 8px 0 10px; font: 600 clamp(2rem, 6vw, 4.75rem)/.95 system-ui, sans-serif; letter-spacing: -.06em; }}
    h2 {{ margin: 40px 0 12px; font: 600 1rem/1.2 system-ui, sans-serif; letter-spacing: .02em; text-transform: uppercase; }}
    p {{ color: var(--muted); max-width: 76ch; }}
    .boundary {{ border-left: 3px solid var(--accent); background: #1d1b1b; padding: 14px 16px; }}
    table {{ width: 100%; border-collapse: collapse; background: rgba(24, 26, 33, .78); }}
    th, td {{ text-align: left; vertical-align: top; padding: 11px 12px; border: 1px solid var(--line); }}
    th {{ color: var(--muted); font-size: .72rem; font-weight: 500; text-transform: uppercase; letter-spacing: .08em; }}
    td {{ font-size: .86rem; }}
    code {{ color: #dcc6a1; word-break: break-all; }}
    .state {{ color: {"var(--ok)" if handoff.is_aligned else "var(--warn)"}; }}
    footer {{ margin-top: 48px; padding-top: 20px; border-top: 1px solid var(--line); color: var(--muted); font-size: .8rem; }}
    @media (max-width: 720px) {{ main {{ padding: 28px 14px 48px; }} table {{ display: block; overflow-x: auto; }} }}
  </style>
</head>
<body>
  <main>
    <header>
      <div class="eyebrow">Local companion evidence · offline packet</div>
      <h1>{escape(str(release["title"]))}</h1>
      <p>{escape(str(release["artist"]))} · {escape(str(release["catalogue_number"]))} · planned {escape(str(release["planned_release_date"]))}</p>
      <p class="state">{"Aligned captured relationships" if handoff.is_aligned else "Needs evidence review"}</p>
      <p>Handoff ID: <code>{escape(str(payload["handoff_id"]))}</code></p>
    </header>

    <section class="boundary"><strong>Boundary.</strong> {escape(_HANDOFF_BOUNDARY)}</section>

    <h2>Releaseforge proof capture</h2>
    <table>
      <thead><tr><th>Proof ID</th><th>Local decision</th><th>Captured assets</th></tr></thead>
      <tbody><tr><td><code>{escape(str(payload["releaseforge"]["proof_id"]))}</code></td><td>{escape(str(decision["state"]))}</td><td>{payload["releaseforge"]["captured_asset_count"]}</td></tr></tbody>
    </table>

    <h2>Companion captures</h2>
    <table>
      <thead><tr><th>Capture</th><th>Manifest SHA-256</th><th>Recorded relationship</th></tr></thead>
      <tbody>{companion_rows}</tbody>
    </table>

    <h2>Handoff findings</h2>
    <table>
      <thead><tr><th>Severity</th><th>Subject</th><th>Evidence category</th><th>Finding</th></tr></thead>
      <tbody>{finding_rows}</tbody>
    </table>

    <footer>Generated locally by Releaseforge. It contains no source files and makes no external network request.</footer>
  </main>
</body>
</html>
"""


def write_handoff_packet(
    handoff: Handoff,
    output_dir: Path | str,
    *,
    protected_roots: tuple[Path | str, ...] = (),
) -> Path:
    """Write one new portable handoff packet outside all input packet trees."""
    output_path = Path(output_dir).resolve()
    _reject_protected_output(output_path, protected_roots)
    if output_path.exists():
        raise HandoffError(f"handoff output directory already exists: {output_path.name}")
    try:
        output_path.mkdir(parents=True, exist_ok=False)
        (output_path / "RELEASE_HANDOFF.md").write_text(
            render_handoff_markdown(handoff), encoding="utf-8"
        )
        (output_path / "RELEASE_HANDOFF.json").write_text(
            json.dumps(handoff_payload(handoff), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        (output_path / "RELEASE_HANDOFF.html").write_text(
            render_handoff_html(handoff), encoding="utf-8"
        )
    except OSError as error:
        raise HandoffError(f"could not write handoff packet: {error}") from error
    return output_path


def _releaseledger_payload(handoff: Handoff) -> dict[str, Any] | None:
    if handoff.releaseledger is None:
        return None
    assert handoff.releaseledger_alignment is not None
    alignment = handoff.releaseledger_alignment
    return {
        "manifest_sha256": handoff.releaseledger.manifest_sha256,
        "alignment": {
            "matching_fields": list(alignment.matching_fields),
            "mismatched_fields": list(alignment.mismatched_fields),
            "matching_track_numbers": list(alignment.matching_track_numbers),
            "missing_releaseledger_track_numbers": list(
                alignment.missing_releaseledger_track_numbers
            ),
            "unmatched_releaseledger_track_numbers": list(
                alignment.unmatched_releaseledger_track_numbers
            ),
        },
    }


def _coverforge_payload(handoff: Handoff) -> dict[str, Any] | None:
    if handoff.coverforge is None:
        return None
    assert handoff.coverforge_linkage is not None
    linkage = handoff.coverforge_linkage
    return {
        "manifest_sha256": handoff.coverforge.manifest_sha256,
        "capture_id": handoff.coverforge.capture_id,
        "captured_output_count": len(handoff.coverforge.outputs),
        "captured_preflight_finding_count": handoff.coverforge.preflight_finding_count,
        "linkage": {
            "state": linkage.state,
            "matching_source_fields": list(linkage.matching_source_fields),
            "mismatched_source_fields": list(linkage.mismatched_source_fields),
            "skipped_target_keys": list(linkage.skipped_target_keys),
            "over_size_cap_target_keys": list(linkage.over_size_cap_target_keys),
        },
    }


def _proof_decision(proof: Packet) -> dict[str, Any]:
    decision = proof.payload.get("decision")
    if not isinstance(decision, dict):
        raise HandoffError("Releaseforge proof packet has no valid decision data")
    state = _nonblank_string(decision.get("state"), "Releaseforge proof packet decision.state")
    return {"state": state}


def _markdown_companion_lines(payload: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    releaseledger = payload["releaseledger"]
    if releaseledger is not None:
        alignment = releaseledger["alignment"]
        lines.extend(
            [
                "### Releaseledger-compatible v1 manifest capture",
                "",
                f"- Manifest SHA-256: `{releaseledger['manifest_sha256']}`",
                f"- Matching declared fields: {_markdown_value(alignment['matching_fields'])}",
                f"- Mismatched declared fields: {_markdown_value(alignment['mismatched_fields'])}",
                f"- Matching track numbers: {_markdown_value(alignment['matching_track_numbers'])}",
            ]
        )
    coverforge = payload["coverforge"]
    if coverforge is not None:
        linkage = coverforge["linkage"]
        lines.extend(
            [
                "### Coverforge-compatible v1 manifest capture",
                "",
                f"- Manifest SHA-256: `{coverforge['manifest_sha256']}`",
                f"- Capture ID: `{coverforge['capture_id']}`",
                f"- Captured outputs: {coverforge['captured_output_count']}",
                (
                    "- Captured preflight findings: "
                    f"{coverforge['captured_preflight_finding_count']}"
                ),
                f"- Captured source linkage: {_markdown_value(linkage['state'])}",
                (f"- Matching source fields: {_markdown_value(linkage['matching_source_fields'])}"),
                (
                    "- Mismatched source fields: "
                    f"{_markdown_value(linkage['mismatched_source_fields'])}"
                ),
                f"- Skipped targets: {_markdown_value(linkage['skipped_target_keys'])}",
                (
                    "- Over-size-cap targets: "
                    f"{_markdown_value(linkage['over_size_cap_target_keys'])}"
                ),
            ]
        )
    return lines or ["No companion capture was supplied."]


def _html_companion_rows(payload: dict[str, Any]) -> list[str]:
    rows: list[str] = []
    releaseledger = payload["releaseledger"]
    if releaseledger is not None:
        alignment = releaseledger["alignment"]
        rows.append(
            _html_row(
                "Releaseledger-compatible v1 manifest capture",
                releaseledger["manifest_sha256"],
                "matching declared fields: " + (", ".join(alignment["matching_fields"]) or "none"),
            )
        )
    coverforge = payload["coverforge"]
    if coverforge is not None:
        linkage = coverforge["linkage"]
        rows.append(
            _html_row(
                "Coverforge-compatible v1 manifest capture",
                coverforge["manifest_sha256"],
                (
                    f"{linkage['state']}; matching source fields: "
                    f"{', '.join(linkage['matching_source_fields']) or 'none'}"
                ),
            )
        )
    return rows or ['<tr><td colspan="3">No companion capture was supplied.</td></tr>']


def _html_row(*values: object) -> str:
    return f"<tr>{''.join(f'<td>{escape(str(value))}</td>' for value in values)}</tr>"


def _markdown_value(value: object) -> str:
    text = escape(str(value), quote=False).replace("\r", " ").replace("\n", " ")
    return text.translate(_MARKDOWN_ESCAPES)


def _reject_protected_output(output_path: Path, protected_roots: tuple[Path | str, ...]) -> None:
    for root in protected_roots:
        try:
            output_path.relative_to(Path(root).resolve())
        except ValueError:
            continue
        raise HandoffError("handoff output directory must be outside input packet directories")


def _reconcile_coverforge(
    proof: Packet, coverforge: CoverforgeManifest | None
) -> tuple[CoverforgeLinkage | None, list[HandoffFinding]]:
    if coverforge is None:
        return None, []
    cover = _proof_cover(proof)
    source = coverforge.source
    compared_fields = (
        ("sha256", source.sha256, cover["sha256"]),
        ("byte_size", source.byte_size, cover["byte_size"]),
        ("dimensions", (source.width, source.height), (cover["width"], cover["height"])),
        ("mode", source.mode, cover["image_mode"]),
    )
    matching_fields: list[str] = []
    mismatched_fields: list[str] = []
    findings: list[HandoffFinding] = []
    finding_codes = {
        "sha256": "coverforge_source_sha256_mismatch",
        "byte_size": "coverforge_source_byte_size_mismatch",
        "dimensions": "coverforge_source_dimensions_mismatch",
        "mode": "coverforge_source_mode_mismatch",
    }
    for field, coverforge_value, proof_value in compared_fields:
        if coverforge_value == proof_value:
            matching_fields.append(field)
            continue
        mismatched_fields.append(field)
        findings.append(
            HandoffFinding(
                code=finding_codes[field],
                severity="needs_evidence",
                evidence_category="captured_companion_manifest",
                subject="cover",
                message=(
                    "The Coverforge manifest source "
                    f"{field.replace('_', ' ')} does not match the captured Releaseforge cover. "
                    "Review the intended handoff relationship."
                ),
            )
        )

    skipped_target_keys = coverforge.skipped_target_keys
    for target_key in skipped_target_keys:
        findings.append(
            HandoffFinding(
                code="coverforge_target_skipped",
                severity="needs_evidence",
                evidence_category="captured_companion_manifest",
                subject=f"coverforge-target:{target_key}",
                message=(
                    "The Coverforge capture records this selected target as not produced. "
                    "Review the intended visual handoff."
                ),
            )
        )
    over_size_cap_target_keys = tuple(
        output.target_key for output in coverforge.outputs if output.over_size_cap
    )
    for target_key in over_size_cap_target_keys:
        findings.append(
            HandoffFinding(
                code="coverforge_output_over_size_cap",
                severity="needs_evidence",
                evidence_category="captured_companion_manifest",
                subject=f"coverforge-target:{target_key}",
                message=(
                    "The Coverforge capture records this visual output as over its configured "
                    "size cap. Review the intended visual handoff."
                ),
            )
        )
    return (
        CoverforgeLinkage(
            state="aligned" if not findings else "needs_evidence",
            matching_source_fields=tuple(matching_fields),
            mismatched_source_fields=tuple(mismatched_fields),
            skipped_target_keys=skipped_target_keys,
            over_size_cap_target_keys=over_size_cap_target_keys,
        ),
        findings,
    )


def _reconcile_releaseledger(
    proof: Packet, releaseledger: ReleaseledgerManifest | None
) -> tuple[ReleaseledgerAlignment | None, list[HandoffFinding]]:
    if releaseledger is None:
        return None, []
    release = _proof_release(proof)
    matching_fields: list[str] = []
    mismatched_fields: list[str] = []
    findings: list[HandoffFinding] = []
    for field, companion_value, proof_value in (
        ("artist", releaseledger.artist, release["artist"]),
        ("title", releaseledger.title, release["title"]),
        ("catalogue_number", releaseledger.catalogue_number, release["catalogue_number"]),
    ):
        _append_field_alignment(
            field,
            companion_value,
            proof_value,
            matching_fields,
            mismatched_fields,
            findings,
        )
    if releaseledger.release_date is not None:
        _append_field_alignment(
            "release_date",
            releaseledger.release_date,
            release["planned_release_date"],
            matching_fields,
            mismatched_fields,
            findings,
        )

    proof_track_numbers = set(_proof_track_numbers(proof))
    ledger_track_numbers = {track.number for track in releaseledger.tracks}
    matching_track_numbers = tuple(sorted(proof_track_numbers & ledger_track_numbers))
    missing_releaseledger_track_numbers = tuple(sorted(proof_track_numbers - ledger_track_numbers))
    findings.extend(
        HandoffFinding(
            code="releaseledger_track_missing",
            severity="needs_evidence",
            evidence_category="declared",
            subject=f"track:{number}",
            message=(
                "Releaseledger has no declared track at this captured Releaseforge "
                "position. Review the intended handoff relationship."
            ),
        )
        for number in missing_releaseledger_track_numbers
    )
    unmatched_releaseledger_track_numbers = tuple(
        sorted(ledger_track_numbers - proof_track_numbers)
    )
    findings.extend(
        HandoffFinding(
            code="releaseledger_track_unmatched",
            severity="needs_evidence",
            evidence_category="declared",
            subject=f"releaseledger-track:{number}",
            message=(
                "Releaseledger contains a declared numbered track with no matching "
                "Releaseforge proof track. Review the intended handoff relationship."
            ),
        )
        for number in unmatched_releaseledger_track_numbers
    )
    return (
        ReleaseledgerAlignment(
            matching_fields=tuple(matching_fields),
            mismatched_fields=tuple(mismatched_fields),
            matching_track_numbers=matching_track_numbers,
            missing_releaseledger_track_numbers=missing_releaseledger_track_numbers,
            unmatched_releaseledger_track_numbers=unmatched_releaseledger_track_numbers,
        ),
        findings,
    )


def _append_field_alignment(
    field: str,
    companion_value: str,
    proof_value: str,
    matching_fields: list[str],
    mismatched_fields: list[str],
    findings: list[HandoffFinding],
) -> None:
    if companion_value == proof_value:
        matching_fields.append(field)
        return
    mismatched_fields.append(field)
    findings.append(
        HandoffFinding(
            code=f"releaseledger_{field}_mismatch",
            severity="needs_evidence",
            evidence_category="declared",
            subject=f"release:{field}",
            message=(
                "Releaseledger's declared release value does not align with the captured "
                "Releaseforge proof. Review the intended handoff relationship."
            ),
        )
    )


def _proof_cover(proof: Packet) -> dict[str, Any]:
    assets = proof.payload.get("assets")
    if not isinstance(assets, list):
        raise HandoffError("Releaseforge proof packet has no valid assets")
    covers = [asset for asset in assets if isinstance(asset, dict) and asset.get("role") == "cover"]
    if len(covers) != 1:
        raise HandoffError("Releaseforge proof packet must contain exactly one valid cover asset")
    cover = covers[0]
    return {
        "sha256": _sha256(cover.get("sha256"), "Releaseforge proof packet cover SHA-256"),
        "byte_size": _positive_int(
            cover.get("byte_size"), "Releaseforge proof packet cover byte size"
        ),
        "width": _positive_int(cover.get("width"), "Releaseforge proof packet cover width"),
        "height": _positive_int(cover.get("height"), "Releaseforge proof packet cover height"),
        "image_mode": _nonblank_string(
            cover.get("image_mode"), "Releaseforge proof packet cover image mode"
        ),
    }


def _proof_release(proof: Packet) -> dict[str, str]:
    release = proof.payload.get("release")
    if not isinstance(release, dict):
        raise HandoffError("Releaseforge proof packet has no valid release data")
    required = ("artist", "title", "catalogue_number", "planned_release_date")
    return {
        field: _nonblank_string(release.get(field), f"Releaseforge proof packet release.{field}")
        for field in required
    }


def _proof_track_numbers(proof: Packet) -> tuple[int, ...]:
    assets = proof.payload.get("assets")
    if not isinstance(assets, list):
        raise HandoffError("Releaseforge proof packet has no valid assets")
    tracks: list[int] = []
    for asset in assets:
        if not isinstance(asset, dict):
            raise HandoffError("Releaseforge proof packet asset must be an object")
        role = asset.get("role")
        if not isinstance(role, str) or not role.startswith("track:"):
            continue
        try:
            number = int(role.removeprefix("track:"))
        except ValueError as error:
            raise HandoffError("Releaseforge proof packet track role is invalid") from error
        tracks.append(number)
    return tuple(sorted(set(tracks)))


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


def _parse_source_fingerprint(value: Any, fields: frozenset[str], label: str) -> None:
    source = _mapping(value, label)
    _expect_exact_keys(source, fields, label)
    _bare_filename(source["filename"], f"{label} filename")
    _sha256(source["sha256"], f"{label} SHA-256")


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


def _bare_filename(value: Any, label: str) -> str:
    filename = _nonblank_string(value, label)
    if filename.startswith(".") or "/" in filename or "\\" in filename or filename in {".", ".."}:
        raise HandoffError(f"{label} must be a bare filename")
    return filename
