"""Render portable, offline release-proof documents from one deterministic model."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

from releaseforge.config import ReleasePlan
from releaseforge.evaluate import Evaluation, Finding
from releaseforge.inspect import AssetFact, Inspection

BOUNDARY = (
    "This packet does not establish that an asset is owned, licensed, approved, "
    "accepted by a distributor, or ready for public release. It records local file "
    "facts and supplied declarations for human review."
)


class ReportError(ValueError):
    """Raised when a portable proof packet cannot be created safely."""


@dataclass(frozen=True)
class Report:
    """One immutable source shared by every Releaseforge output format."""

    plan: ReleasePlan
    inspection: Inspection
    evaluation: Evaluation


def make_report(plan: ReleasePlan, inspection: Inspection, evaluation: Evaluation) -> Report:
    """Bind validated plan data, verified file facts, and deterministic findings."""
    return Report(plan=plan, inspection=inspection, evaluation=evaluation)


def report_payload(report: Report) -> dict[str, Any]:
    """Return a JSON-ready report without machine-specific source paths."""
    plan = report.plan
    payload = {
        "schema_version": 1,
        "boundary": BOUNDARY,
        "decision": {
            "state": report.evaluation.decision,
            "profile_checked": report.evaluation.is_ready,
            "blocker_count": report.evaluation.blocker_count,
            "warning_count": report.evaluation.warning_count,
            "needs_evidence_count": report.evaluation.needs_evidence_count,
        },
        "release": {
            "title": plan.release.title,
            "artist": plan.release.artist,
            "catalogue_number": plan.release.catalogue_number,
            "planned_release_date": plan.release.planned_release_date.isoformat(),
            "evidence_category": "declared",
        },
        "requirements": {
            "minimum_cover_pixels": plan.requirements.minimum_cover_pixels,
            "require_square_cover": plan.requirements.require_square_cover,
            "allowed_audio_extensions": list(plan.requirements.allowed_audio_extensions),
            "evidence_category": "declared",
            "note": "Workflow requirements chosen by the user; not a distributor policy statement.",
        },
        "declarations": {
            "rights_review": _declaration_payload(plan.declarations.rights_review),
            "metadata_review": _declaration_payload(plan.declarations.metadata_review),
            "artwork_approval": _declaration_payload(plan.declarations.artwork_approval),
        },
        "assets": [_asset_payload(asset) for asset in report.inspection.assets],
        "findings": [_finding_payload(finding) for finding in report.evaluation.findings],
    }
    payload["proof_id"] = packet_proof_id(payload)
    return payload


def packet_proof_id(payload: Mapping[str, Any]) -> str:
    """Return a stable identifier for every packet field except its proof-ID field."""
    canonical_payload = {key: value for key, value in payload.items() if key != "proof_id"}
    encoded = json.dumps(
        canonical_payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"rfp_{hashlib.sha256(encoded).hexdigest()[:20]}"


def render_markdown(report: Report) -> str:
    """Render a portable Markdown decision record with no source absolute paths."""
    payload = report_payload(report)
    decision = payload["decision"]
    release = payload["release"]
    requirements = payload["requirements"]
    lines = [
        "# Releaseforge local release proof",
        "",
        f"**Decision: {_markdown(decision['state'])}**",
        "",
        f"> **Boundary:** {_markdown(BOUNDARY)}",
        "",
        "## Decision summary",
        "",
        "| Blockers | Warnings | Needs evidence | Profile checked |",
        "| ---: | ---: | ---: | --- |",
        (
            f"| {decision['blocker_count']} | {decision['warning_count']} | "
            f"{decision['needs_evidence_count']} | {decision['profile_checked']} |"
        ),
        "",
        "## Declared release data",
        "",
        "| Field | Supplied value | Evidence category |",
        "| --- | --- | --- |",
        f"| Title | {_markdown(release['title'])} | declared |",
        f"| Primary artist | {_markdown(release['artist'])} | declared |",
        f"| Catalogue number | {_markdown(release['catalogue_number'])} | declared |",
        f"| Planned release date | {_markdown(release['planned_release_date'])} | declared |",
        "",
        "## Declared workflow profile",
        "",
        f"{_markdown(requirements['note'])}",
        "",
        "| Minimum cover pixels | Square cover required | Allowed audio extensions |",
        "| ---: | --- | --- |",
        (
            f"| {requirements['minimum_cover_pixels']} | {requirements['require_square_cover']} | "
            f"{_markdown(', '.join(requirements['allowed_audio_extensions']))} |"
        ),
        "",
        "## Supplied declarations",
        "",
        "| Review | Supplied status | Evidence category |",
        "| --- | --- | --- |",
    ]
    for name, declaration in payload["declarations"].items():
        lines.append(
            f"| {_markdown(name.replace('_', ' '))} | {_markdown(declaration['value'])} | "
            f"{_markdown(declaration['evidence_category'])} |"
        )

    lines.extend(
        [
            "",
            "## Verified local asset facts",
            "",
            "| Role | Relative path | Verified facts | SHA-256 |",
            "| --- | --- | --- | --- |",
        ]
    )
    for asset in payload["assets"]:
        lines.append(
            f"| {_markdown(asset['role'])} | {_markdown(asset['relative_path'])} | "
            f"{_markdown(_asset_summary(asset))} | `{asset['sha256']}` |"
        )

    lines.extend(["", "## Findings", ""])
    if payload["findings"]:
        lines.extend(
            [
                "| Severity | Subject | Evidence category | Finding |",
                "| --- | --- | --- | --- |",
            ]
        )
        for finding in payload["findings"]:
            lines.append(
                f"| {_markdown(finding['severity'])} | {_markdown(finding['subject'])} | "
                f"{_markdown(finding['evidence_category'])} | {_markdown(finding['message'])} |"
            )
    else:
        lines.append("No blockers, warnings, or pending-evidence findings were emitted.")

    lines.extend(
        [
            "",
            "## Evidence categories",
            "",
            "- `verified_file_fact`: read directly from local file bytes or a file header.",
            "- `declared`: supplied in `release.toml`; its truth remains outside this tool.",
            "- `needs_evidence`: a supplied declaration still needs external human review.",
            "- `blocker`: a configured workflow condition is not met.",
            "",
        ]
    )
    return "\n".join(lines)


def render_html(report: Report) -> str:
    """Render one self-contained, offline HTML review surface."""
    payload = report_payload(report)
    decision = payload["decision"]
    release = payload["release"]
    requirements = payload["requirements"]
    state_class = _state_class(decision["state"])
    declaration_rows = "".join(
        _table_row(
            name.replace("_", " "),
            declaration["value"],
            declaration["evidence_category"],
        )
        for name, declaration in payload["declarations"].items()
    )
    asset_rows = "".join(_asset_table_row(asset) for asset in payload["assets"])
    finding_rows = "".join(_finding_table_row(finding) for finding in payload["findings"])
    if not finding_rows:
        finding_rows = '<tr><td colspan="4">No blockers, warnings, or pending-evidence findings were emitted.</td></tr>'
    title = f"Releaseforge proof — {release['artist']} — {release['title']}"
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>{escape(title)}</title>
  <style>
    :root {{
      color-scheme: dark;
      --ink: #101116;
      --surface: #181a21;
      --surface-2: #22252e;
      --bone: #f1ede3;
      --muted: #aaa79f;
      --line: #343844;
      --accent: #bf9a63;
      --danger: #f08080;
      --warn: #e5ba68;
      --ok: #8fcda0;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: radial-gradient(circle at top right, #24212d 0, var(--ink) 40rem);
      color: var(--bone);
      font: 16px/1.5 ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 48px 24px 72px; }}
    header {{ border-bottom: 1px solid var(--line); padding-bottom: 28px; margin-bottom: 28px; }}
    .eyebrow {{ color: var(--accent); font-size: .75rem; letter-spacing: .13em; text-transform: uppercase; }}
    h1 {{ margin: 8px 0 10px; font: 600 clamp(2rem, 6vw, 4.75rem)/.95 system-ui, sans-serif; letter-spacing: -.06em; }}
    h2 {{ margin: 40px 0 12px; font: 600 1rem/1.2 system-ui, sans-serif; letter-spacing: .02em; text-transform: uppercase; }}
    p {{ color: var(--muted); max-width: 76ch; }}
    .decision {{ display: inline-flex; align-items: center; gap: .55rem; border: 1px solid var(--line); padding: .55rem .75rem; background: var(--surface); }}
    .decision::before {{ content: \"\"; width: .55rem; height: .55rem; border-radius: 50%; background: var(--accent); }}
    .decision.blocked::before {{ background: var(--danger); }}
    .decision.needs-evidence::before {{ background: var(--warn); }}
    .decision.profile-checked::before {{ background: var(--ok); }}
    .summary {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 22px 0; }}
    .metric {{ padding: 16px; background: var(--surface); border: 1px solid var(--line); }}
    .metric span {{ display: block; color: var(--muted); font-size: .72rem; text-transform: uppercase; letter-spacing: .08em; }}
    .metric strong {{ display: block; margin-top: 5px; font: 600 1.7rem/1 system-ui, sans-serif; }}
    .boundary {{ border-left: 3px solid var(--accent); background: #1d1b1b; padding: 14px 16px; }}
    .boundary strong {{ color: var(--bone); }}
    table {{ width: 100%; border-collapse: collapse; background: rgba(24, 26, 33, .78); overflow: hidden; }}
    th, td {{ text-align: left; vertical-align: top; padding: 11px 12px; border: 1px solid var(--line); }}
    th {{ color: var(--muted); font-size: .72rem; font-weight: 500; text-transform: uppercase; letter-spacing: .08em; }}
    td {{ font-size: .86rem; }}
    code {{ color: #dcc6a1; word-break: break-all; }}
    .tag {{ display: inline-block; border: 1px solid currentColor; padding: .1rem .35rem; font-size: .72rem; text-transform: uppercase; }}
    .tag.blocker {{ color: var(--danger); }}
    .tag.warning, .tag.needs_evidence {{ color: var(--warn); }}
    .tag.info {{ color: var(--ok); }}
    footer {{ margin-top: 48px; padding-top: 20px; border-top: 1px solid var(--line); color: var(--muted); font-size: .8rem; }}
    @media (max-width: 720px) {{ .summary {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} main {{ padding: 28px 14px 48px; }} table {{ display: block; overflow-x: auto; }} }}
  </style>
</head>
<body>
  <main>
    <header>
      <div class=\"eyebrow\">Local release proof · offline packet</div>
      <h1>{escape(release["title"])}</h1>
      <p>{escape(release["artist"])} · {escape(release["catalogue_number"])} · planned {escape(release["planned_release_date"])}</p>
      <div class=\"decision {state_class}\">{escape(decision["state"])}</div>
    </header>

    <section class=\"summary\" aria-label=\"Decision summary\">
      <div class=\"metric\"><span>Blockers</span><strong>{decision["blocker_count"]}</strong></div>
      <div class=\"metric\"><span>Warnings</span><strong>{decision["warning_count"]}</strong></div>
      <div class=\"metric\"><span>Needs evidence</span><strong>{decision["needs_evidence_count"]}</strong></div>
      <div class=\"metric\"><span>Profile checked</span><strong>{str(decision["profile_checked"]).lower()}</strong></div>
    </section>

    <section class=\"boundary\"><strong>Boundary.</strong> {escape(BOUNDARY)}</section>

    <h2>Declared release data</h2>
    <table>
      <thead><tr><th>Field</th><th>Supplied value</th><th>Evidence</th></tr></thead>
      <tbody>
        {_table_row("Title", release["title"], "declared")}
        {_table_row("Primary artist", release["artist"], "declared")}
        {_table_row("Catalogue number", release["catalogue_number"], "declared")}
        {_table_row("Planned release date", release["planned_release_date"], "declared")}
      </tbody>
    </table>

    <h2>Declared workflow profile</h2>
    <p>{escape(requirements["note"])}</p>
    <table>
      <thead><tr><th>Minimum cover pixels</th><th>Square cover</th><th>Allowed extensions</th></tr></thead>
      <tbody><tr><td>{requirements["minimum_cover_pixels"]}</td><td>{str(requirements["require_square_cover"]).lower()}</td><td>{escape(", ".join(requirements["allowed_audio_extensions"]))}</td></tr></tbody>
    </table>

    <h2>Supplied declarations</h2>
    <table>
      <thead><tr><th>Review</th><th>Supplied status</th><th>Evidence</th></tr></thead>
      <tbody>{declaration_rows}</tbody>
    </table>

    <h2>Verified local asset facts</h2>
    <table>
      <thead><tr><th>Role</th><th>Relative path</th><th>Verified facts</th><th>SHA-256</th></tr></thead>
      <tbody>{asset_rows}</tbody>
    </table>

    <h2>Findings</h2>
    <table>
      <thead><tr><th>Severity</th><th>Subject</th><th>Evidence</th><th>Finding</th></tr></thead>
      <tbody>{finding_rows}</tbody>
    </table>

    <footer>Generated locally by Releaseforge. It contains no source files and makes no external network request.</footer>
  </main>
</body>
</html>
"""


def write_packet(report: Report, output_dir: Path | str) -> Path:
    """Create exactly the documented output files in a new directory outside the source tree."""
    output_path = Path(output_dir).resolve()
    _reject_source_tree_output(report, output_path)
    if output_path.exists():
        raise ReportError(f"output directory already exists: {output_path.name}")
    try:
        output_path.mkdir(parents=True, exist_ok=False)
        (output_path / "RELEASE_PROOF.md").write_text(render_markdown(report), encoding="utf-8")
        (output_path / "RELEASE_PROOF.json").write_text(
            json.dumps(report_payload(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (output_path / "RELEASE_READINESS.html").write_text(render_html(report), encoding="utf-8")
    except OSError as error:
        raise ReportError(f"could not write output packet: {error}") from error
    return output_path


def _declaration_payload(value: str) -> dict[str, str]:
    return {
        "value": value,
        "evidence_category": "declared",
        "note": "Supplied in release.toml; truth remains outside this tool.",
    }


def _asset_payload(asset: AssetFact) -> dict[str, Any]:
    return {
        "role": asset.role,
        "relative_path": asset.relative_path.as_posix(),
        "evidence_category": "verified_file_fact",
        "byte_size": asset.byte_size,
        "sha256": asset.sha256,
        "extension": asset.extension,
        "width": asset.width,
        "height": asset.height,
        "image_mode": asset.image_mode,
        "duration_seconds": asset.duration_seconds,
        "sample_rate": asset.sample_rate,
        "channels": asset.channels,
        "sample_width_bytes": asset.sample_width_bytes,
    }


def _finding_payload(finding: Finding) -> dict[str, str]:
    return {
        "code": finding.code,
        "severity": finding.severity,
        "evidence_category": finding.evidence_category,
        "message": finding.message,
        "subject": finding.subject,
    }


def _asset_summary(asset: dict[str, Any]) -> str:
    facts = [f"{asset['byte_size']} bytes", asset["extension"]]
    if asset["width"] is not None and asset["height"] is not None:
        image = f"{asset['width']}×{asset['height']}"
        if asset["image_mode"]:
            image = f"{image} {asset['image_mode']}"
        facts.append(image)
    if asset["duration_seconds"] is not None:
        audio = f"{asset['duration_seconds']:.3f} s"
        if asset["sample_rate"]:
            audio = f"{audio} · {asset['sample_rate']} Hz"
        if asset["channels"]:
            audio = f"{audio} · {asset['channels']} ch"
        facts.append(audio)
    return " · ".join(facts)


def _markdown(value: Any) -> str:
    return escape(str(value), quote=False).replace("|", "\\|").replace("\n", " ")


def _state_class(state: str) -> str:
    return {
        "BLOCKED": "blocked",
        "NEEDS EVIDENCE": "needs-evidence",
        "PROFILE CHECKED": "profile-checked",
        "REVIEW WARNINGS": "review-warnings",
    }.get(state, "review-warnings")


def _table_row(*values: Any) -> str:
    return f"<tr>{''.join(f'<td>{escape(str(value))}</td>' for value in values)}</tr>"


def _asset_table_row(asset: dict[str, Any]) -> str:
    return (
        "<tr>"
        f"<td>{escape(asset['role'])}</td>"
        f"<td>{escape(asset['relative_path'])}</td>"
        f"<td>{escape(_asset_summary(asset))}</td>"
        f"<td><code>{escape(asset['sha256'])}</code></td>"
        "</tr>"
    )


def _finding_table_row(finding: dict[str, str]) -> str:
    severity = escape(finding["severity"])
    return (
        "<tr>"
        f'<td><span class="tag {severity}">{severity}</span></td>'
        f"<td>{escape(finding['subject'])}</td>"
        f"<td>{escape(finding['evidence_category'])}</td>"
        f"<td>{escape(finding['message'])}</td>"
        "</tr>"
    )


def _reject_source_tree_output(report: Report, output_path: Path) -> None:
    try:
        output_path.relative_to(report.plan.root.resolve())
    except ValueError:
        return
    raise ReportError("output directory must be outside the release source directory")
