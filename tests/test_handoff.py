from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from releaseforge.handoff import HandoffError, load_mastergate_manifest, load_releaseledger_manifest


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


def _write_mastergate_manifest(path: Path) -> Path:
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
                    "sha256": "a" * 64,
                }
            ],
            "overall_delivery_verdict": "RENDERED - QC INCOMPLETE",
            "schema_version": 1,
        },
    )


def _write_releaseledger_manifest(
    path: Path, *, extra_root: dict[str, object] | None = None
) -> Path:
    payload: dict[str, object] = {
        "files": ["PLATFORM_CHECKLIST.md", "RELEASE.md", "manifest.json", "tracks.csv"],
        "release": {
            "artist": "Synthetic Artist",
            "catalog_number": "SYN-001",
            "kind": "EP",
            "label": "Synthetic Label",
            "release_date": "2026-09-01",
            "title": "Synthetic Release",
        },
        "schema_version": 1,
        "source": {"filename": "release.toml", "sha256": "c" * 64},
        "tracks": [{"duration": "01:00", "isrc": None, "number": 1, "title": "Synthetic Track"}],
    }
    if extra_root:
        payload.update(extra_root)
    return _write_json(path, payload)


def _write_json(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
