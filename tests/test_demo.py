from __future__ import annotations

import json

import pytest

from releaseforge.compare import compare_packets, comparison_payload, load_packet
from releaseforge.demo import DemoError, create_demo


def test_create_demo_builds_two_packets_with_one_clear_asset_difference(tmp_path):
    demo = create_demo(tmp_path / "demo")

    assert demo.guide.is_file()
    assert {path.name for path in demo.proof_v1.iterdir()} == {
        "RELEASE_PROOF.md",
        "RELEASE_PROOF.json",
        "RELEASE_READINESS.html",
    }
    assert {path.name for path in demo.proof_v2.iterdir()} == {
        "RELEASE_PROOF.md",
        "RELEASE_PROOF.json",
        "RELEASE_READINESS.html",
    }
    assert "synthetic" in demo.guide.read_text(encoding="utf-8").lower()
    assert str(tmp_path) not in (demo.proof_v1 / "RELEASE_PROOF.json").read_text(encoding="utf-8")

    comparison = compare_packets(load_packet(demo.proof_v1), load_packet(demo.proof_v2))
    changes = {(change.category, change.subject, change.code) for change in comparison.changes}

    assert ("verified_asset", "cover", "asset_bytes_changed") in changes
    assert str(tmp_path) not in json.dumps(comparison_payload(comparison), sort_keys=True)


def test_create_demo_refuses_to_overwrite_a_destination(tmp_path):
    destination = tmp_path / "existing-demo"
    destination.mkdir()
    marker = destination / "keep.txt"
    marker.write_text("keep", encoding="utf-8")

    with pytest.raises(DemoError, match="already exists"):
        create_demo(destination)

    assert marker.read_text(encoding="utf-8") == "keep"
