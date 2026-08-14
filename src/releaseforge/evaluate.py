"""Evaluate only the release workflow requirements declared by the user."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from releaseforge.config import DeclarationPlan, ReleasePlan
from releaseforge.inspect import AssetFact, Inspection

Severity = Literal["blocker", "warning", "needs_evidence", "info"]
EvidenceCategory = Literal["verified_file_fact", "declared", "needs_evidence", "blocker"]


@dataclass(frozen=True)
class Finding:
    """One human-reviewable result from a local fact or supplied declaration."""

    code: str
    severity: Severity
    evidence_category: EvidenceCategory
    message: str
    subject: str


@dataclass(frozen=True)
class Evaluation:
    """The deterministic workflow decision and every reason behind it."""

    findings: tuple[Finding, ...]

    @property
    def blocker_count(self) -> int:
        return sum(finding.severity == "blocker" for finding in self.findings)

    @property
    def warning_count(self) -> int:
        return sum(finding.severity == "warning" for finding in self.findings)

    @property
    def needs_evidence_count(self) -> int:
        return sum(finding.severity == "needs_evidence" for finding in self.findings)

    @property
    def is_ready(self) -> bool:
        """Return true only when the selected profile has no blockers or pending evidence."""
        return self.blocker_count == 0 and self.needs_evidence_count == 0

    @property
    def decision(self) -> str:
        """Return a human-facing state without implying external approval."""
        if self.blocker_count:
            return "BLOCKED"
        if self.needs_evidence_count:
            return "NEEDS EVIDENCE"
        if self.warning_count:
            return "REVIEW WARNINGS"
        return "PROFILE CHECKED"


def evaluate_release(plan: ReleasePlan, inspection: Inspection) -> Evaluation:
    """Evaluate local facts against the plan's explicit, user-declared workflow profile."""
    findings: list[Finding] = []
    _evaluate_cover(plan, inspection.by_role("cover"), findings)
    _evaluate_tracks(plan, inspection, findings)
    _evaluate_declarations(plan.declarations, findings)
    return Evaluation(findings=tuple(findings))


def _evaluate_cover(plan: ReleasePlan, cover: AssetFact, findings: list[Finding]) -> None:
    assert cover.width is not None
    assert cover.height is not None
    minimum = plan.requirements.minimum_cover_pixels
    if cover.width < minimum or cover.height < minimum:
        findings.append(
            Finding(
                code="cover_below_declared_minimum",
                severity="blocker",
                evidence_category="blocker",
                subject="cover",
                message=(
                    f"Verified cover geometry is {cover.width}×{cover.height}; "
                    f"the declared workflow minimum is {minimum}×{minimum}."
                ),
            )
        )
    if plan.requirements.require_square_cover and cover.width != cover.height:
        findings.append(
            Finding(
                code="cover_not_square",
                severity="blocker",
                evidence_category="blocker",
                subject="cover",
                message=(
                    f"Verified cover geometry is {cover.width}×{cover.height}; "
                    "a square cover is required."
                ),
            )
        )


def _evaluate_tracks(plan: ReleasePlan, inspection: Inspection, findings: list[Finding]) -> None:
    for track in plan.tracks:
        fact = inspection.by_role(f"track:{track.number}")
        subject = f"track:{track.number}"
        if fact.extension not in plan.requirements.allowed_audio_extensions:
            allowed = ", ".join(plan.requirements.allowed_audio_extensions)
            findings.append(
                Finding(
                    code="track_extension_not_allowed",
                    severity="blocker",
                    evidence_category="blocker",
                    subject=subject,
                    message=(
                        f"Track {track.number} has verified extension {fact.extension!r}. "
                        f"Declared allowed extensions: {allowed}."
                    ),
                )
            )
        if track.declared_master_status != "declared_final":
            findings.append(
                Finding(
                    code="track_master_needs_evidence",
                    severity="needs_evidence",
                    evidence_category="needs_evidence",
                    subject=subject,
                    message=(
                        f"Track {track.number} master status is declared as "
                        f"{track.declared_master_status!r}. "
                        "External review evidence is still needed."
                    ),
                )
            )


def _evaluate_declarations(declarations: DeclarationPlan, findings: list[Finding]) -> None:
    for field, status in (
        ("rights_review", declarations.rights_review),
        ("metadata_review", declarations.metadata_review),
        ("artwork_approval", declarations.artwork_approval),
    ):
        if status != "declared_current":
            findings.append(
                Finding(
                    code=f"{field}_needs_evidence",
                    severity="needs_evidence",
                    evidence_category="needs_evidence",
                    subject=f"declaration:{field}",
                    message=(
                        f"{field.replace('_', ' ')} is declared as {status!r}; "
                        "external review evidence is still needed."
                    ),
                )
            )
