from __future__ import annotations

import json

import pytest

from releaseforge.config import load_plan
from releaseforge.evaluate import evaluate_release
from releaseforge.inspect import inspect_release
from releaseforge.report import ReportError, make_report, render_html, report_payload, write_packet


def _report(release_dir):
    plan = load_plan(release_dir)
    return make_report(plan, inspect_release(plan), evaluate_release(plan, inspect_release(plan)))


def test_write_packet_creates_three_portable_outputs(synthetic_release, tmp_path):
    report = _report(synthetic_release)
    packet = write_packet(report, tmp_path / "proof")

    assert {path.name for path in packet.iterdir()} == {
        "RELEASE_PROOF.md",
        "RELEASE_PROOF.json",
        "RELEASE_READINESS.html",
    }
    markdown = (packet / "RELEASE_PROOF.md").read_text(encoding="utf-8")
    assert "does not establish" in markdown
    assert str(synthetic_release) not in markdown
    assert str(synthetic_release) not in (packet / "RELEASE_PROOF.json").read_text(encoding="utf-8")
    assert str(synthetic_release) not in (packet / "RELEASE_READINESS.html").read_text(
        encoding="utf-8"
    )


def test_html_escapes_declared_text(synthetic_release):
    plan_path = synthetic_release / "release.toml"
    plan_path.write_text(
        plan_path.read_text(encoding="utf-8").replace(
            'title = "Synthetic Release"', 'title = "<unsafe>"'
        ),
        encoding="utf-8",
    )

    html = render_html(_report(synthetic_release))

    assert "&lt;unsafe&gt;" in html
    assert "<unsafe>" not in html
    assert "https://" not in html


def test_packet_refuses_existing_output(synthetic_release, tmp_path):
    packet = tmp_path / "proof"
    packet.mkdir()

    with pytest.raises(ReportError, match="already exists"):
        write_packet(_report(synthetic_release), packet)


def test_payload_keeps_evidence_categories_explicit(synthetic_release):
    payload = report_payload(_report(synthetic_release))

    assert payload["assets"][0]["evidence_category"] == "verified_file_fact"
    assert payload["declarations"]["rights_review"]["evidence_category"] == "declared"
    assert json.loads(json.dumps(payload, sort_keys=True)) == payload


def test_payload_has_a_stable_proof_id(synthetic_release):
    first = report_payload(_report(synthetic_release))
    second = report_payload(_report(synthetic_release))

    assert first["proof_id"] == second["proof_id"]
    assert first["proof_id"].startswith("rfp_")
