"""Strict local intake for portable companion build manifests."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

from releaseforge.compare import Packet


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


@dataclass(frozen=True)
class HandoffFinding:
    """One bounded discrepancy between captured companion values."""

    code: str
    severity: str
    evidence_category: str
    subject: str
    message: str


@dataclass(frozen=True)
class MastergateLinkage:
    """The captured SHA-256 relationship between Releaseforge WAVs and Mastergate."""

    state: str
    matched_releaseforge_wav_roles: tuple[str, ...]
    unmatched_releaseforge_wav_roles: tuple[str, ...]
    unmatched_mastergate_measurement_hashes: tuple[str, ...]


@dataclass(frozen=True)
class ReleaseledgerAlignment:
    """The shared declared metadata relationship with a Releaseledger manifest."""

    matching_fields: tuple[str, ...]
    mismatched_fields: tuple[str, ...]
    matching_track_numbers: tuple[int, ...]
    missing_releaseledger_track_numbers: tuple[int, ...]
    unmatched_releaseledger_track_numbers: tuple[int, ...]


@dataclass(frozen=True)
class Handoff:
    """One local comparison of validated Releaseforge and companion captures."""

    proof: Packet
    mastergate: MastergateManifest | None
    releaseledger: ReleaseledgerManifest | None
    mastergate_linkage: MastergateLinkage | None
    releaseledger_alignment: ReleaseledgerAlignment | None
    findings: tuple[HandoffFinding, ...]

    @property
    def is_aligned(self) -> bool:
        """Return true only when all selected captured relationships align."""
        return not self.findings


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
_HANDOFF_BOUNDARY = (
    "This handoff records relationships between a validated Releaseforge proof packet "
    "and selected local companion manifests. It does not establish current-file "
    "verification, approval, ownership, rights, external delivery, distributor "
    "acceptance, or release readiness."
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


def build_handoff(
    proof: Packet,
    *,
    mastergate: MastergateManifest | None = None,
    releaseledger: ReleaseledgerManifest | None = None,
) -> Handoff:
    """Reconcile selected captured evidence without reading source media or paths."""
    if mastergate is None and releaseledger is None:
        raise HandoffError("handoff requires at least one companion manifest")

    mastergate_linkage, mastergate_findings = _reconcile_mastergate(proof, mastergate)
    releaseledger_alignment, releaseledger_findings = _reconcile_releaseledger(proof, releaseledger)
    return Handoff(
        proof=proof,
        mastergate=mastergate,
        releaseledger=releaseledger,
        mastergate_linkage=mastergate_linkage,
        releaseledger_alignment=releaseledger_alignment,
        findings=tuple(mastergate_findings + releaseledger_findings),
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
        "schema_version": 1,
        "boundary": _HANDOFF_BOUNDARY,
        "releaseforge": {
            "proof_id": handoff.proof.proof_id,
            "release": _proof_release(handoff.proof),
            "decision": _proof_decision(handoff.proof),
            "captured_asset_count": len(proof_assets),
        },
        "mastergate": _mastergate_payload(handoff),
        "releaseledger": _releaseledger_payload(handoff),
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


def _mastergate_payload(handoff: Handoff) -> dict[str, Any] | None:
    if handoff.mastergate is None:
        return None
    assert handoff.mastergate_linkage is not None
    linkage = handoff.mastergate_linkage
    return {
        "manifest_sha256": handoff.mastergate.manifest_sha256,
        "captured_measurement_count": len(handoff.mastergate.measurements),
        "linkage": {
            "state": linkage.state,
            "matched_releaseforge_wav_roles": list(linkage.matched_releaseforge_wav_roles),
            "unmatched_releaseforge_wav_roles": list(linkage.unmatched_releaseforge_wav_roles),
            "unmatched_mastergate_measurement_hashes": list(
                linkage.unmatched_mastergate_measurement_hashes
            ),
        },
    }


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


def _proof_decision(proof: Packet) -> dict[str, Any]:
    decision = proof.payload.get("decision")
    if not isinstance(decision, dict):
        raise HandoffError("Releaseforge proof packet has no valid decision data")
    state = _nonblank_string(decision.get("state"), "Releaseforge proof packet decision.state")
    return {"state": state}


def _markdown_companion_lines(payload: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    mastergate = payload["mastergate"]
    if mastergate is not None:
        linkage = mastergate["linkage"]
        lines.extend(
            [
                "### Mastergate capture",
                "",
                f"- Manifest SHA-256: `{mastergate['manifest_sha256']}`",
                f"- Captured measurements: {mastergate['captured_measurement_count']}",
                f"- Captured WAV linkage: {_markdown_value(linkage['state'])}",
                f"- Matched Releaseforge WAV roles: {_markdown_value(linkage['matched_releaseforge_wav_roles'])}",
                f"- Unmatched Releaseforge WAV roles: {_markdown_value(linkage['unmatched_releaseforge_wav_roles'])}",
            ]
        )
    releaseledger = payload["releaseledger"]
    if releaseledger is not None:
        alignment = releaseledger["alignment"]
        lines.extend(
            [
                "### Releaseledger capture",
                "",
                f"- Manifest SHA-256: `{releaseledger['manifest_sha256']}`",
                f"- Matching declared fields: {_markdown_value(alignment['matching_fields'])}",
                f"- Mismatched declared fields: {_markdown_value(alignment['mismatched_fields'])}",
                f"- Matching track numbers: {_markdown_value(alignment['matching_track_numbers'])}",
            ]
        )
    return lines or ["No companion capture was supplied."]


def _html_companion_rows(payload: dict[str, Any]) -> list[str]:
    rows: list[str] = []
    mastergate = payload["mastergate"]
    if mastergate is not None:
        linkage = mastergate["linkage"]
        rows.append(
            _html_row(
                "Mastergate build manifest",
                mastergate["manifest_sha256"],
                f"{linkage['state']}; matched WAV roles: {', '.join(linkage['matched_releaseforge_wav_roles']) or 'none'}",
            )
        )
    releaseledger = payload["releaseledger"]
    if releaseledger is not None:
        alignment = releaseledger["alignment"]
        rows.append(
            _html_row(
                "Releaseledger build manifest",
                releaseledger["manifest_sha256"],
                "matching declared fields: " + (", ".join(alignment["matching_fields"]) or "none"),
            )
        )
    return rows or ['<tr><td colspan="3">No companion capture was supplied.</td></tr>']


def _html_row(*values: object) -> str:
    return f"<tr>{''.join(f'<td>{escape(str(value))}</td>' for value in values)}</tr>"


def _markdown_value(value: object) -> str:
    return escape(str(value), quote=False).replace("|", "\\|").replace("\n", " ")


def _reject_protected_output(output_path: Path, protected_roots: tuple[Path | str, ...]) -> None:
    for root in protected_roots:
        try:
            output_path.relative_to(Path(root).resolve())
        except ValueError:
            continue
        raise HandoffError("handoff output directory must be outside input packet directories")


def _reconcile_mastergate(
    proof: Packet, mastergate: MastergateManifest | None
) -> tuple[MastergateLinkage | None, list[HandoffFinding]]:
    if mastergate is None:
        return None, []
    wav_assets = _proof_wav_assets(proof)
    if not wav_assets:
        return (
            MastergateLinkage(
                state="not_applicable",
                matched_releaseforge_wav_roles=(),
                unmatched_releaseforge_wav_roles=(),
                unmatched_mastergate_measurement_hashes=(),
            ),
            [],
        )

    measurement_hashes = {measurement.sha256 for measurement in mastergate.measurements}
    proof_hashes = {sha256 for _, sha256 in wav_assets}
    matched_roles = tuple(role for role, sha256 in wav_assets if sha256 in measurement_hashes)
    unmatched_roles = tuple(role for role, sha256 in wav_assets if sha256 not in measurement_hashes)
    unmatched_measurements = tuple(
        sorted({measurement.sha256 for measurement in mastergate.measurements} - proof_hashes)
    )
    findings = [
        HandoffFinding(
            code="mastergate_wav_hash_unmatched",
            severity="needs_evidence",
            evidence_category="captured_companion_manifest",
            subject=role,
            message=(
                "No identical captured Mastergate SHA-256 value was found for this "
                "Releaseforge WAV asset. Review the intended handoff relationship."
            ),
        )
        for role in unmatched_roles
    ]
    if not unmatched_roles:
        findings.extend(
            HandoffFinding(
                code="mastergate_measurement_hash_unmatched",
                severity="needs_evidence",
                evidence_category="captured_companion_manifest",
                subject="mastergate",
                message=(
                    "A captured Mastergate measurement SHA-256 value did not match a "
                    "Releaseforge WAV asset. Review the intended handoff relationship."
                ),
            )
            for _ in unmatched_measurements
        )
    return (
        MastergateLinkage(
            state="aligned" if not findings else "needs_evidence",
            matched_releaseforge_wav_roles=matched_roles,
            unmatched_releaseforge_wav_roles=unmatched_roles,
            unmatched_mastergate_measurement_hashes=unmatched_measurements,
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


def _proof_wav_assets(proof: Packet) -> tuple[tuple[str, str], ...]:
    assets = proof.payload.get("assets")
    if not isinstance(assets, list):
        raise HandoffError("Releaseforge proof packet has no valid assets")
    wav_assets: list[tuple[str, str]] = []
    for asset in assets:
        if not isinstance(asset, dict):
            raise HandoffError("Releaseforge proof packet asset must be an object")
        if asset.get("extension") != ".wav":
            continue
        role = asset.get("role")
        sha256 = asset.get("sha256")
        if not isinstance(role, str):
            raise HandoffError("Releaseforge proof packet WAV asset has no valid role")
        wav_assets.append((role, _sha256(sha256, "Releaseforge proof packet WAV SHA-256")))
    return tuple(wav_assets)


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
