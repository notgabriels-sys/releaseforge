from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from releaseforge.cli import main
from releaseforge.compare import Packet
from releaseforge.config import load_plan
from releaseforge.coverforge import load_coverforge_manifest
from releaseforge.evaluate import evaluate_release
from releaseforge.handoff import (
    HandoffError,
    build_handoff,
    handoff_exit_code,
    handoff_payload,
    load_mastergate_manifest,
    load_releaseledger_manifest,
    render_handoff_html,
    render_handoff_markdown,
    write_handoff_packet,
)
from releaseforge.inspect import inspect_release
from releaseforge.report import make_report, packet_proof_id, report_payload, write_packet


def test_load_mastergate_manifest_keeps_only_safe_captured_fields(tmp_path: Path):
    manifest_path = _write_mastergate_manifest(tmp_path / "mastergate.json")

    manifest = load_mastergate_manifest(manifest_path)

    assert manifest.manifest_sha256 == _sha256_file(manifest_path)
    assert manifest.measurements[0].sha256 == "a" * 64
    assert manifest.measurements[0].filename == "01-track.wav"
    assert not hasattr(manifest, "input_directory")
    assert not hasattr(manifest, "contract_source")


def test_load_releaseledger_manifest_rejects_an_unknown_field(tmp_path: Path):
    manifest_path = _write_releaseledger_manifest(
        tmp_path / "releaseledger.json", extra_root={"path": "/private/source"}
    )

    with pytest.raises(HandoffError, match="unexpected field"):
        load_releaseledger_manifest(manifest_path)


def test_build_handoff_records_matching_captured_wav_hashes_and_declarations(
    synthetic_release: Path, tmp_path: Path
):
    proof = _proof_packet(synthetic_release)
    handoff = build_handoff(
        proof,
        mastergate=load_mastergate_manifest(
            _write_mastergate_manifest(tmp_path / "mastergate.json", sha256=_proof_track_sha(proof))
        ),
        releaseledger=load_releaseledger_manifest(
            _write_releaseledger_manifest(tmp_path / "releaseledger.json")
        ),
    )

    assert handoff.is_aligned is True
    assert handoff.findings == ()
    assert handoff.mastergate_linkage is not None
    assert handoff.mastergate_linkage.matched_releaseforge_wav_roles == ("track:1",)
    assert handoff_exit_code(handoff) == 0


def test_build_handoff_reconciles_matching_coverforge_source(
    synthetic_release: Path, tmp_path: Path
):
    proof = _proof_packet(synthetic_release)
    cover = _proof_cover_asset(proof)
    coverforge = load_coverforge_manifest(
        _write_coverforge_manifest(
            tmp_path / "coverforge" / "manifest.json",
            source_sha256=cover["sha256"],
            source_bytes=cover["byte_size"],
            source_dimensions=f"{cover['width']}x{cover['height']}",
            source_mode=cover["image_mode"],
        )
    )

    handoff = build_handoff(proof, coverforge=coverforge)
    payload = handoff_payload(handoff)

    assert handoff.is_aligned is True
    assert handoff.coverforge_linkage is not None
    assert handoff.coverforge_linkage.matching_source_fields == (
        "sha256",
        "byte_size",
        "dimensions",
        "mode",
    )
    assert payload["coverforge"]["capture_id"] == coverforge.capture_id
    assert payload["coverforge"]["captured_output_count"] == 1
    assert "slug" not in payload["coverforge"]
    assert "synthetic-release--bandcamp--3000x3000.jpg" not in json.dumps(payload["coverforge"])


def test_build_handoff_records_coverforge_source_and_delivery_discrepancies(
    synthetic_release: Path, tmp_path: Path
):
    proof = _proof_packet(synthetic_release)
    cover = _proof_cover_asset(proof)
    coverforge = load_coverforge_manifest(
        _write_coverforge_manifest(
            tmp_path / "coverforge" / "manifest.json",
            source_sha256="f" * 64,
            source_bytes=cover["byte_size"],
            source_dimensions=f"{cover['width']}x{cover['height']}",
            source_mode=cover["image_mode"],
            skipped_target_keys=("soundcloud",),
            over_size_cap=True,
        )
    )

    handoff = build_handoff(proof, coverforge=coverforge)

    assert handoff.is_aligned is False
    assert handoff.coverforge_linkage is not None
    assert handoff.coverforge_linkage.mismatched_source_fields == ("sha256",)
    assert handoff.coverforge_linkage.skipped_target_keys == ("soundcloud",)
    assert handoff.coverforge_linkage.over_size_cap_target_keys == ("bandcamp",)
    assert {finding.code for finding in handoff.findings} == {
        "coverforge_source_sha256_mismatch",
        "coverforge_target_skipped",
        "coverforge_output_over_size_cap",
    }
    assert {finding.severity for finding in handoff.findings} == {"needs_evidence"}
    assert handoff_exit_code(handoff) == 1


def test_build_handoff_emits_needs_evidence_for_mismatched_companion_values(
    synthetic_release: Path, tmp_path: Path
):
    proof = _proof_packet(synthetic_release)
    handoff = build_handoff(
        proof,
        mastergate=load_mastergate_manifest(
            _write_mastergate_manifest(tmp_path / "mastergate.json", sha256="b" * 64)
        ),
        releaseledger=load_releaseledger_manifest(
            _write_releaseledger_manifest(
                tmp_path / "releaseledger.json", release_title="Different title"
            )
        ),
    )

    assert handoff.is_aligned is False
    assert {finding.code for finding in handoff.findings} == {
        "mastergate_wav_hash_unmatched",
        "releaseledger_title_mismatch",
    }
    assert {finding.severity for finding in handoff.findings} == {"needs_evidence"}
    assert handoff_exit_code(handoff) == 1


def test_write_handoff_packet_omits_input_paths_and_escapes_html(
    synthetic_release: Path, tmp_path: Path
):
    proof = _proof_packet(synthetic_release)
    proof.payload["release"]["title"] = "<script>alert(1)</script>"
    handoff = build_handoff(
        proof,
        mastergate=load_mastergate_manifest(
            _write_mastergate_manifest(tmp_path / "mastergate.json", sha256=_proof_track_sha(proof))
        ),
    )
    destination = tmp_path / "handoff-output"

    write_handoff_packet(handoff, destination, protected_roots=(tmp_path / "proof",))

    html = (destination / "RELEASE_HANDOFF.html").read_text(encoding="utf-8")
    payload = json.loads((destination / "RELEASE_HANDOFF.json").read_text(encoding="utf-8"))
    assert sorted(path.name for path in destination.iterdir()) == [
        "RELEASE_HANDOFF.html",
        "RELEASE_HANDOFF.json",
        "RELEASE_HANDOFF.md",
    ]
    assert str(tmp_path) not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)</script>" not in html
    assert payload["handoff_id"].startswith("rfh_")
    assert payload["handoff_id"] == handoff_payload(handoff)["handoff_id"]


def test_write_handoff_packet_renders_path_free_coverforge_capture(
    synthetic_release: Path, tmp_path: Path
):
    proof = _proof_packet(synthetic_release)
    cover = _proof_cover_asset(proof)
    coverforge = load_coverforge_manifest(
        _write_coverforge_manifest(
            tmp_path / "coverforge-input" / "manifest.json",
            source_sha256=cover["sha256"],
            source_bytes=cover["byte_size"],
            source_dimensions=f"{cover['width']}x{cover['height']}",
            source_mode=cover["image_mode"],
        )
    )
    handoff = build_handoff(proof, coverforge=coverforge)
    destination = tmp_path / "handoff-output"

    write_handoff_packet(handoff, destination, protected_roots=(tmp_path / "proof",))

    rendered = [
        (destination / "RELEASE_HANDOFF.json").read_text(encoding="utf-8"),
        (destination / "RELEASE_HANDOFF.md").read_text(encoding="utf-8"),
        (destination / "RELEASE_HANDOFF.html").read_text(encoding="utf-8"),
    ]
    for document in rendered:
        assert str(tmp_path) not in document
        assert "synthetic-release--bandcamp--3000x3000.jpg" not in document
    assert "Coverforge-compatible v1 manifest capture" in rendered[1]
    assert "Coverforge-compatible v1 manifest capture" in rendered[2]


def test_write_handoff_packet_refuses_output_inside_an_input_tree(
    synthetic_release: Path, tmp_path: Path
):
    proof = _proof_packet(synthetic_release)
    handoff = build_handoff(
        proof,
        mastergate=load_mastergate_manifest(
            _write_mastergate_manifest(tmp_path / "mastergate.json", sha256=_proof_track_sha(proof))
        ),
    )
    protected_root = tmp_path / "proof"
    protected_root.mkdir()

    with pytest.raises(HandoffError, match="outside input packet directories"):
        write_handoff_packet(handoff, protected_root / "handoff", protected_roots=(protected_root,))


def test_handoff_cli_writes_an_aligned_packet(
    synthetic_release: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    proof = _proof_packet(synthetic_release)
    proof_dir = _write_proof_packet(synthetic_release, tmp_path / "proof")
    mastergate_path = _write_mastergate_manifest(
        tmp_path / "mastergate-input" / "manifest.json", sha256=_proof_track_sha(proof)
    )
    output_dir = tmp_path / "handoff"

    result = main(
        [
            "handoff",
            str(proof_dir),
            "--mastergate",
            str(mastergate_path),
            "--output",
            str(output_dir),
        ]
    )

    assert result == 0
    assert (output_dir / "RELEASE_HANDOFF.json").is_file()
    assert "Wrote release handoff packet" in capsys.readouterr().out


def test_handoff_cli_requires_a_companion_manifest(
    synthetic_release: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    proof_dir = _write_proof_packet(synthetic_release, tmp_path / "proof")

    assert main(["handoff", str(proof_dir), "--output", str(tmp_path / "handoff")]) == 2
    assert "at least one companion" in capsys.readouterr().err


def test_handoff_cli_escapes_active_markdown_from_a_valid_proof_packet(
    synthetic_release: Path, tmp_path: Path
):
    proof_dir = _write_proof_packet(synthetic_release, tmp_path / "proof")
    proof_path = proof_dir / "RELEASE_PROOF.json"
    proof_payload = json.loads(proof_path.read_text(encoding="utf-8"))
    hostile_title = "![tracking](https://example.invalid/pixel.png) `literal`"
    proof_payload["release"]["title"] = hostile_title
    proof_payload["proof_id"] = packet_proof_id(proof_payload)
    proof_path.write_text(
        json.dumps(proof_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    mastergate_path = _write_mastergate_manifest(
        tmp_path / "mastergate" / "manifest.json",
        sha256=next(
            asset["sha256"] for asset in proof_payload["assets"] if asset["role"] == "track:1"
        ),
    )
    output_dir = tmp_path / "handoff"

    assert (
        main(
            [
                "handoff",
                str(proof_dir),
                "--mastergate",
                str(mastergate_path),
                "--output",
                str(output_dir),
            ]
        )
        == 0
    )

    markdown = (output_dir / "RELEASE_HANDOFF.md").read_text(encoding="utf-8")
    assert hostile_title not in markdown
    assert r"\!\[tracking\]\(https://example.invalid/pixel.png\) \`literal\`" in markdown


def test_handoff_packet_states_compatible_manifest_provenance_boundary(
    synthetic_release: Path, tmp_path: Path
):
    proof = _proof_packet(synthetic_release)
    handoff = build_handoff(
        proof,
        mastergate=load_mastergate_manifest(
            _write_mastergate_manifest(tmp_path / "mastergate.json", sha256=_proof_track_sha(proof))
        ),
    )

    payload = handoff_payload(handoff)
    markdown = render_handoff_markdown(handoff)
    html = render_handoff_html(handoff)

    for rendered in (payload["boundary"], markdown, html):
        assert "do not authenticate the producer" in rendered
    assert "Mastergate-compatible v1 manifest capture" in html


def _write_proof_packet(release_dir: Path, output_dir: Path) -> Path:
    plan = load_plan(release_dir)
    inspection = inspect_release(plan)
    report = make_report(plan, inspection, evaluate_release(plan, inspection))
    return write_packet(report, output_dir)


def _write_mastergate_manifest(path: Path, *, sha256: str = "a" * 64) -> Path:
    return _write_json(
        path,
        {
            "contract": {
                "assets": {"expected_files": ["01-track.wav"]},
                "delivery": {
                    "requirements_basis": "Local delivery contract",
                    "title": "Synthetic delivery",
                },
                "format": {"bit_depth": 24, "channels": 2, "sample_rate_hz": 48_000},
                "limits": {"max_sample_peak_dbfs": None, "reject_full_scale_samples": False},
            },
            "contract_source": {"filename": "delivery.toml", "sha256": "b" * 64},
            "declared_file_checks_passed": True,
            "errors": [],
            "input": {"directory_name": "masters"},
            "measurements": [
                {
                    "bit_depth": 24,
                    "byte_size": 1234,
                    "channels": 2,
                    "duration_seconds": 1.0,
                    "filename": "01-track.wav",
                    "frame_count": 48_000,
                    "full_scale_sample_count": 0,
                    "sample_peak_dbfs": -1.0,
                    "sample_rate_hz": 48_000,
                    "sha256": sha256,
                }
            ],
            "overall_delivery_verdict": "RENDERED - QC INCOMPLETE",
            "schema_version": 1,
        },
    )


def _write_releaseledger_manifest(
    path: Path,
    *,
    extra_root: dict[str, object] | None = None,
    release_title: str = "Synthetic Release",
    track_title: str = "Synthetic Track",
) -> Path:
    payload: dict[str, object] = {
        "files": ["PLATFORM_CHECKLIST.md", "RELEASE.md", "manifest.json", "tracks.csv"],
        "release": {
            "artist": "Synthetic Artist",
            "catalog_number": "SYN-001",
            "kind": "EP",
            "label": "Synthetic Label",
            "release_date": "2026-09-01",
            "title": release_title,
        },
        "schema_version": 1,
        "source": {"filename": "release.toml", "sha256": "c" * 64},
        "tracks": [{"duration": "01:00", "isrc": None, "number": 1, "title": track_title}],
    }
    if extra_root:
        payload.update(extra_root)
    return _write_json(path, payload)


def _write_coverforge_manifest(
    path: Path,
    *,
    source_sha256: str = "a" * 64,
    source_bytes: int = 1234,
    source_dimensions: str = "3000x3000",
    source_mode: str = "RGB",
    skipped_target_keys: tuple[str, ...] = (),
    over_size_cap: bool = False,
) -> Path:
    payload: dict[str, object] = {
        "schema_version": 1,
        "generated_by": "coverforge",
        "boundary": "Synthetic local boundary.",
        "slug": "synthetic-release",
        "source": {
            "sha256": source_sha256,
            "bytes": source_bytes,
            "dimensions": source_dimensions,
            "mode": source_mode,
            "format": "jpeg",
        },
        "outputs": [
            {
                "target": "bandcamp",
                "name": "Bandcamp",
                "file": "synthetic-release--bandcamp--3000x3000.jpg",
                "dimensions": "3000x3000",
                "format": "jpeg",
                "quality": 92,
                "bytes": 1111,
                "size": "1 KB",
                "over_size_cap": over_size_cap,
                "sha256": "b" * 64,
            }
        ],
        "skipped": [
            {"target": target_key, "reason": "Synthetic target was not produced."}
            for target_key in skipped_target_keys
        ],
        "findings": [],
    }
    payload["capture_id"] = _coverforge_capture_id(payload)
    return _write_json(path, payload)


def _write_json(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _proof_packet(release_dir: Path) -> Packet:
    plan = load_plan(release_dir)
    inspection = inspect_release(plan)
    report = make_report(plan, inspection, evaluate_release(plan, inspection))
    payload = report_payload(report)
    return Packet(proof_id=payload["proof_id"], payload=payload)


def _proof_track_sha(proof: Packet) -> str:
    return next(asset["sha256"] for asset in proof.payload["assets"] if asset["role"] == "track:1")


def _proof_cover_asset(proof: Packet) -> dict:
    return next(asset for asset in proof.payload["assets"] if asset["role"] == "cover")


def _coverforge_capture_id(payload: dict[str, object]) -> str:
    canonical = {key: value for key, value in payload.items() if key != "capture_id"}
    encoded = json.dumps(
        canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return f"cfp_{hashlib.sha256(encoded).hexdigest()[:20]}"
