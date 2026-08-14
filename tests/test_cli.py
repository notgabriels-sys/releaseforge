from __future__ import annotations

import json

from releaseforge.cli import main
from releaseforge.config import load_plan
from releaseforge.evaluate import evaluate_release
from releaseforge.inspect import inspect_release
from releaseforge.report import make_report, write_packet
from tests.helpers import tree_digest, write_synthetic_release


def _packet(release_dir, output_dir):
    plan = load_plan(release_dir)
    inspection = inspect_release(plan)
    report = make_report(plan, inspection, evaluate_release(plan, inspection))
    return write_packet(report, output_dir)


def test_init_creates_a_template_only_once(tmp_path, capsys):
    release_dir = tmp_path / "new-release"

    assert main(["init", str(release_dir)]) == 0
    assert "Created release.toml" in capsys.readouterr().out
    assert (release_dir / "release.toml").is_file()

    assert main(["init", str(release_dir)]) == 2
    assert "already exists" in capsys.readouterr().err


def test_check_is_read_only_and_reports_a_decision(synthetic_release, capsys):
    before = tree_digest(synthetic_release)

    assert main(["check", str(synthetic_release)]) == 0

    assert tree_digest(synthetic_release) == before
    output = capsys.readouterr().out
    assert "LOCAL RELEASE PROOF" in output
    assert "PROFILE CHECKED" in output
    assert "No packet was written." in output


def test_build_writes_a_packet_without_changing_source(synthetic_release, tmp_path, capsys):
    before = tree_digest(synthetic_release)
    output_dir = tmp_path / "proof"

    assert main(["build", str(synthetic_release), "--output", str(output_dir)]) == 0

    assert tree_digest(synthetic_release) == before
    assert {path.name for path in output_dir.iterdir()} == {
        "RELEASE_PROOF.md",
        "RELEASE_PROOF.json",
        "RELEASE_READINESS.html",
    }
    assert "Wrote release proof packet" in capsys.readouterr().out


def test_build_refuses_an_existing_output(synthetic_release, tmp_path, capsys):
    output_dir = tmp_path / "proof"
    output_dir.mkdir()

    assert main(["build", str(synthetic_release), "--output", str(output_dir)]) == 2
    assert "already exists" in capsys.readouterr().err


def test_check_returns_one_when_a_configured_condition_is_blocked(tmp_path, capsys):
    release_dir = write_synthetic_release(tmp_path / "blocked", cover_size=(1200, 1200))

    assert main(["check", str(release_dir)]) == 1

    assert "BLOCKED" in capsys.readouterr().out


def test_compare_returns_one_for_captured_changes_without_writing(tmp_path, capsys):
    before = _packet(write_synthetic_release(tmp_path / "before"), tmp_path / "before-packet")
    after = _packet(
        write_synthetic_release(tmp_path / "after", cover_size=(2800, 2800)),
        tmp_path / "after-packet",
    )
    before_digest = tree_digest(before)
    after_digest = tree_digest(after)

    assert main(["compare", str(before), str(after)]) == 1

    output = capsys.readouterr().out
    assert "RELEASE PROOF COMPARISON" in output
    assert "VERIFIED_ASSET" in output
    assert str(tmp_path) not in output
    assert tree_digest(before) == before_digest
    assert tree_digest(after) == after_digest


def test_compare_accepts_a_direct_json_path_and_can_emit_json(tmp_path, capsys):
    packet = _packet(write_synthetic_release(tmp_path / "release"), tmp_path / "packet")

    assert main(["compare", str(packet / "RELEASE_PROOF.json"), str(packet), "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["equivalent"] is True
    assert payload["change_count"] == 0
