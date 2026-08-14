from __future__ import annotations

from releaseforge.config import load_plan
from releaseforge.evaluate import evaluate_release
from releaseforge.inspect import inspect_release
from tests.helpers import write_synthetic_release


def test_evaluation_passes_when_facts_match_declared_profile(synthetic_release):
    plan = load_plan(synthetic_release)
    evaluation = evaluate_release(plan, inspect_release(plan))

    assert evaluation.blocker_count == 0
    assert evaluation.needs_evidence_count == 0
    assert evaluation.is_ready


def test_evaluation_blocks_undersized_cover_and_marks_pending_rights(tmp_path):
    root = write_synthetic_release(
        tmp_path / "undersized",
        cover_size=(1200, 1200),
        rights_review="declared_pending",
    )
    plan = load_plan(root)
    evaluation = evaluate_release(plan, inspect_release(plan))

    findings = {finding.code: finding for finding in evaluation.findings}
    assert findings["cover_below_declared_minimum"].severity == "blocker"
    assert findings["rights_review_needs_evidence"].severity == "needs_evidence"
    assert not evaluation.is_ready


def test_evaluation_blocks_a_track_outside_the_declared_extensions(tmp_path):
    root = write_synthetic_release(tmp_path / "extension")
    plan_path = root / "release.toml"
    plan_path.write_text(
        plan_path.read_text(encoding="utf-8").replace(
            'allowed_audio_extensions = [".wav", ".flac", ".aiff"]',
            'allowed_audio_extensions = [".flac"]',
        ),
        encoding="utf-8",
    )
    plan = load_plan(root)

    evaluation = evaluate_release(plan, inspect_release(plan))

    assert {finding.code for finding in evaluation.findings} == {"track_extension_not_allowed"}
