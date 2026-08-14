from __future__ import annotations

import json

import pytest

from releaseforge.compare import ComparisonError, compare_packets, comparison_payload, load_packet
from releaseforge.config import load_plan
from releaseforge.evaluate import evaluate_release
from releaseforge.inspect import inspect_release
from releaseforge.report import make_report, packet_proof_id, write_packet
from tests.helpers import write_synthetic_release


def _packet(release_dir, output_dir):
    plan = load_plan(release_dir)
    inspection = inspect_release(plan)
    report = make_report(plan, inspection, evaluate_release(plan, inspection))
    return write_packet(report, output_dir)


def test_compare_identical_packets_has_no_changes(tmp_path):
    packet = _packet(write_synthetic_release(tmp_path / "release"), tmp_path / "packet")

    comparison = compare_packets(load_packet(packet), load_packet(packet))

    assert comparison.is_equal
    assert comparison.changes == ()


def test_compare_reports_verified_asset_bytes_changed(tmp_path):
    before = _packet(write_synthetic_release(tmp_path / "before"), tmp_path / "before-packet")
    after = _packet(
        write_synthetic_release(tmp_path / "after", cover_size=(2800, 2800)),
        tmp_path / "after-packet",
    )

    comparison = compare_packets(load_packet(before), load_packet(after))

    changes = {change.code: change for change in comparison.changes}
    assert changes["asset_bytes_changed"].category == "verified_asset"
    assert changes["asset_bytes_changed"].subject == "cover"
    assert not comparison.is_equal


def test_compare_keeps_a_declared_review_change_distinct_from_file_facts(tmp_path):
    before = _packet(write_synthetic_release(tmp_path / "before"), tmp_path / "before-packet")
    after = _packet(
        write_synthetic_release(tmp_path / "after", rights_review="declared_pending"),
        tmp_path / "after-packet",
    )

    comparison = compare_packets(load_packet(before), load_packet(after))

    change = next(
        change for change in comparison.changes if change.code == "declaration_value_changed"
    )
    assert change.category == "declaration"
    assert change.subject == "rights_review"


def test_load_packet_rejects_a_proof_id_that_does_not_match_contents(tmp_path):
    packet = _packet(write_synthetic_release(tmp_path / "release"), tmp_path / "packet")
    proof_path = packet / "RELEASE_PROOF.json"
    payload = json.loads(proof_path.read_text(encoding="utf-8"))
    payload["proof_id"] = "rfp_invalid"
    proof_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ComparisonError, match="does not match"):
        load_packet(packet)


def test_load_packet_rejects_an_absolute_asset_path_even_with_a_matching_proof_id(tmp_path):
    packet = _packet(write_synthetic_release(tmp_path / "release"), tmp_path / "packet")
    proof_path = packet / "RELEASE_PROOF.json"
    payload = json.loads(proof_path.read_text(encoding="utf-8"))
    payload["assets"][0]["relative_path"] = str(tmp_path / "source-cover.jpg")
    payload["proof_id"] = packet_proof_id(payload)
    proof_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ComparisonError, match="relative asset path"):
        load_packet(packet)


def test_load_packet_rejects_unexpected_packet_fields_even_with_a_matching_proof_id(tmp_path):
    packet = _packet(write_synthetic_release(tmp_path / "release"), tmp_path / "packet")
    proof_path = packet / "RELEASE_PROOF.json"
    payload = json.loads(proof_path.read_text(encoding="utf-8"))
    payload["release"]["source_path"] = str(tmp_path / "source")
    payload["proof_id"] = packet_proof_id(payload)
    proof_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ComparisonError, match="unexpected field"):
        load_packet(packet)


def test_comparison_payload_omits_packet_source_paths(tmp_path):
    before = _packet(write_synthetic_release(tmp_path / "before"), tmp_path / "before-packet")
    after = _packet(
        write_synthetic_release(tmp_path / "after", rights_review="declared_pending"),
        tmp_path / "after-packet",
    )

    payload = comparison_payload(compare_packets(load_packet(before), load_packet(after)))

    assert str(tmp_path) not in json.dumps(payload, sort_keys=True)
