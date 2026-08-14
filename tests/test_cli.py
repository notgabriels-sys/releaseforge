from __future__ import annotations

from releaseforge.cli import main
from tests.helpers import tree_digest, write_synthetic_release


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
