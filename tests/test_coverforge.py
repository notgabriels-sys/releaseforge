from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from releaseforge.coverforge import CoverforgeError, load_coverforge_manifest


def test_load_coverforge_manifest_retains_only_portable_capture_facts(tmp_path: Path):
    path = _write_coverforge_manifest(tmp_path / "coverforge" / "manifest.json")

    manifest = load_coverforge_manifest(path)

    assert manifest.manifest_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert manifest.capture_id == "cfp_3ffcd862a206f2539227"
    assert manifest.source.sha256 == "a" * 64
    assert manifest.source.byte_size == 1234
    assert (manifest.source.width, manifest.source.height) == (3000, 3000)
    assert manifest.source.mode == "RGB"
    assert manifest.outputs[0].target_key == "bandcamp"
    assert manifest.outputs[0].sha256 == "b" * 64
    assert manifest.skipped_target_keys == ()
    assert manifest.preflight_finding_count == 0
    assert not hasattr(manifest, "slug")
    assert not hasattr(manifest.outputs[0], "filename")


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda payload: payload.update({"machine_path": "/private/source"}),
            "unexpected field",
        ),
        (
            lambda payload: payload["outputs"][0].update({"file": "../cover.jpg"}),
            "bare filename",
        ),
    ],
)
def test_load_coverforge_manifest_rejects_nonportable_values(
    tmp_path: Path,
    mutate: Callable[[dict], None],
    message: str,
):
    path = _write_coverforge_manifest(
        tmp_path / "manifest.json", mutate=mutate, recompute_capture_id=True
    )

    with pytest.raises(CoverforgeError, match=message):
        load_coverforge_manifest(path)


def test_load_coverforge_manifest_rejects_capture_id_mismatch(tmp_path: Path):
    path = _write_coverforge_manifest(
        tmp_path / "manifest.json",
        mutate=lambda payload: payload.update({"capture_id": "cfp_" + "0" * 20}),
        recompute_capture_id=False,
    )

    with pytest.raises(CoverforgeError, match="capture_id"):
        load_coverforge_manifest(path)


def test_load_coverforge_manifest_accepts_high_depth_source_mode(tmp_path: Path):
    path = _write_coverforge_manifest(
        tmp_path / "manifest.json",
        mutate=lambda payload: payload["source"].update({"mode": "I;16"}),
        recompute_capture_id=True,
    )

    manifest = load_coverforge_manifest(path)

    assert manifest.source.mode == "I;16"


def test_load_coverforge_manifest_accepts_path_free_custom_target_key(tmp_path: Path):
    path = _write_coverforge_manifest(
        tmp_path / "manifest.json",
        mutate=lambda payload: payload["outputs"][0].update({"target": "instagram 4:5"}),
        recompute_capture_id=True,
    )

    manifest = load_coverforge_manifest(path)

    assert manifest.outputs[0].target_key == "instagram 4:5"


def _write_coverforge_manifest(
    path: Path,
    *,
    mutate: Callable[[dict], None] | None = None,
    recompute_capture_id: bool = True,
) -> Path:
    payload = {
        "schema_version": 1,
        "generated_by": "coverforge",
        "boundary": "Synthetic local boundary.",
        "slug": "synthetic-release",
        "source": {
            "sha256": "a" * 64,
            "bytes": 1234,
            "dimensions": "3000x3000",
            "mode": "RGB",
            "format": "png",
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
                "over_size_cap": False,
                "sha256": "b" * 64,
            }
        ],
        "skipped": [],
        "findings": [],
    }
    if mutate is not None:
        mutate(payload)
    if recompute_capture_id:
        payload["capture_id"] = _capture_id(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def _capture_id(payload: dict) -> str:
    canonical = {key: value for key, value in payload.items() if key != "capture_id"}
    encoded = json.dumps(
        canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return f"cfp_{hashlib.sha256(encoded).hexdigest()[:20]}"
