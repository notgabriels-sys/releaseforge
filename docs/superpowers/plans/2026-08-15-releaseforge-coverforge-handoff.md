# Releaseforge Coverforge Companion Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Releaseforge reconcile a validated Coverforge v1 visual-build manifest with a Releaseforge proof packet and include the bounded result in a portable local handoff dossier.

**Architecture:** A new `releaseforge.coverforge` module owns strict parsing and canonical capture-ID validation for Coverforge v1 JSON, returning only immutable path-free facts. The existing `releaseforge.handoff` module imports that safe model, reconciles it with the verified `cover` asset in a validated Releaseforge proof packet, and extends the existing JSON/Markdown/HTML packet. The CLI only wires a direct manifest path into these units and protects it as an output-exclusion root.

**Tech Stack:** Python 3.11+, standard library `dataclasses`/`hashlib`/`json`/`re`, existing `argparse`, `pytest`, `ruff`, `setuptools` build.

## Global Constraints

- Support only Coverforge portable manifest `schema_version == 1` and `generated_by == "coverforge"`.
- Read companion JSON locally only; never install or import Coverforge, read source media, upload, copy, rename, or delete assets.
- Validate `capture_id` with the exact canonical JSON form Coverforge v1 uses: UTF-8, `ensure_ascii=False`, sorted keys, compact separators, with `capture_id` excluded.
- Retain no Coverforge manifest path, slug, source/output filename, source media, output directory, or arbitrary finding/reason text in Releaseforge models or packets.
- Treat all companion relationships as `captured_companion_manifest` evidence. Never claim ownership, rights, approval, external delivery, distributor acceptance, platform compliance, or release readiness.
- Handoff output remains a new directory outside the proof packet and every selected companion manifest parent.
- Keep existing Releaseledger input/output behavior unchanged.
- Use generated synthetic images and manifests only for tests; do not read, stage, change, or package user artwork.

---

### Task 1: Add a strict, path-free Coverforge v1 schema adapter

**Files:**

- Create: `src/releaseforge/coverforge.py`
- Create: `tests/test_coverforge.py`

**Interfaces:**

- Produces `CoverforgeError(ValueError)` for any malformed or unsupported capture.
- Produces immutable models:

```python
@dataclass(frozen=True)
class CoverforgeSource:
    sha256: str
    byte_size: int
    width: int
    height: int
    mode: str
    file_format: str

@dataclass(frozen=True)
class CoverforgeOutput:
    target_key: str
    width: int
    height: int
    file_format: str
    byte_size: int
    sha256: str
    over_size_cap: bool

@dataclass(frozen=True)
class CoverforgeManifest:
    manifest_sha256: str
    capture_id: str
    source: CoverforgeSource
    outputs: tuple[CoverforgeOutput, ...]
    skipped_target_keys: tuple[str, ...]
    preflight_finding_count: int

def load_coverforge_manifest(path: Path | str) -> CoverforgeManifest: ...
```

- Consumed by Task 2: `CoverforgeManifest` contains only fields safe to embed in a Releaseforge handoff packet.

- [ ] **Step 1: Write failing parser and boundary tests**

Create `tests/test_coverforge.py` with a synthetic Coverforge v1 writer that computes the canonical capture ID independently:

```python
def _capture_id(payload: dict[str, object]) -> str:
    canonical = {key: value for key, value in payload.items() if key != "capture_id"}
    encoded = json.dumps(
        canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return f"cfp_{hashlib.sha256(encoded).hexdigest()[:20]}"


def test_load_coverforge_manifest_keeps_only_safe_capture_facts(tmp_path: Path):
    path = _write_coverforge_manifest(tmp_path / "coverforge" / "manifest.json")

    manifest = load_coverforge_manifest(path)

    assert manifest.manifest_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert manifest.capture_id.startswith("cfp_")
    assert manifest.source.sha256 == "a" * 64
    assert manifest.source.width == 3000
    assert manifest.outputs[0].target_key == "bandcamp"
    assert not hasattr(manifest, "slug")
    assert not hasattr(manifest.outputs[0], "filename")


@pytest.mark.parametrize("mutation, message", [
    (lambda value: value.update({"machine_path": "/private/source"}), "unexpected field"),
    (lambda value: value["outputs"][0].update({"file": "../cover.jpg"}), "bare filename"),
])
def test_load_coverforge_manifest_rejects_nonportable_values(
    tmp_path: Path, mutation, message: str
):
    path = _write_coverforge_manifest(
        tmp_path / "manifest.json", mutate=mutation, recompute_capture_id=True
    )

    with pytest.raises(CoverforgeError, match=message):
        load_coverforge_manifest(path)


def test_load_coverforge_manifest_rejects_capture_id_mismatch(tmp_path: Path):
    path = _write_coverforge_manifest(
        tmp_path / "manifest.json",
        mutate=lambda value: value.update({"capture_id": "cfp_" + "0" * 20}),
        recompute_capture_id=False,
    )

    with pytest.raises(CoverforgeError, match="capture_id"):
        load_coverforge_manifest(path)
```

The helper must produce the exact documented v1 root and nested key sets. It
must build the normal payload, apply `mutate` when supplied, and recompute
`capture_id` only when `recompute_capture_id=True`; this keeps the malformed
shape tests bound to valid canonical JSON while reserving the stale ID for the
dedicated capture-integrity test:

```python
{
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
    "outputs": [{
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
    }],
    "skipped": [],
    "findings": [],
}
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run:

```bash
python3 -m pytest tests/test_coverforge.py -q
```

Expected: FAIL during collection because `releaseforge.coverforge` does not exist.

- [ ] **Step 3: Implement the minimal strict adapter**

Create `src/releaseforge/coverforge.py`. Use a private raw loader and private validators, not the broader `handoff.py` helpers:

```python
_ROOT_FIELDS = frozenset({
    "schema_version", "generated_by", "boundary", "slug", "source", "outputs",
    "skipped", "findings", "capture_id",
})

def load_coverforge_manifest(path: Path | str) -> CoverforgeManifest:
    payload, manifest_sha256 = _load_json_object(path)
    _expect_exact_keys(payload, _ROOT_FIELDS, "Coverforge manifest")
    if payload["schema_version"] != 1 or payload["generated_by"] != "coverforge":
        raise CoverforgeError("unsupported Coverforge manifest")
    _validate_capture_id(payload)
    _safe_slug(payload["slug"])
    source = _parse_source(payload["source"])
    outputs = _parse_outputs(payload["outputs"])
    skipped_target_keys = _parse_skipped(payload["skipped"])
    _validate_findings(payload["findings"])
    return CoverforgeManifest(
        manifest_sha256=manifest_sha256,
        capture_id=_capture_id(payload),
        source=source,
        outputs=outputs,
        skipped_target_keys=skipped_target_keys,
        preflight_finding_count=len(payload["findings"]),
    )
```

Implement `_canonical_capture_id`, `_validate_capture_id`, `_sha256`,
`_positive_int`, `_dimensions`, `_safe_identifier`, and `_bare_filename` so
that all retained strings are path-free, nonblank, and control-character-free.
Require unique output and skipped target keys. Validate every current Coverforge
v1 nested key exactly, including output `quality`, display `size`, `name`,
`over_size_cap`, skipped `reason`, and finding `level`/`code`/`message`/`target`,
but do not store those unneeded values.

- [ ] **Step 4: Run the focused parser tests to verify they pass**

Run:

```bash
python3 -m pytest tests/test_coverforge.py -q
```

Expected: PASS. The loader accepts the synthetic v1 capture and rejects the
unknown root field, path-bearing filename, and mismatched capture ID before any
handoff output can be considered.

- [ ] **Step 5: Commit the adapter and parser tests**

```bash
git add src/releaseforge/coverforge.py tests/test_coverforge.py
git commit -m "feat: validate Coverforge companion manifests"
```

### Task 2: Reconcile safe Coverforge facts with the Releaseforge cover

**Files:**

- Modify: `src/releaseforge/handoff.py:17-115`
- Modify: `src/releaseforge/handoff.py:227-285`
- Modify: `src/releaseforge/handoff.py:460-570`
- Modify: `src/releaseforge/handoff.py:574-796`
- Modify: `tests/test_handoff.py`

**Interfaces:**

- Consumes `CoverforgeManifest` from `releaseforge.coverforge` and existing validated `Packet` from `releaseforge.compare`.
- Extends:

```python
@dataclass(frozen=True)
class CoverforgeLinkage:
    state: str
    matching_source_fields: tuple[str, ...]
    mismatched_source_fields: tuple[str, ...]
    skipped_target_keys: tuple[str, ...]
    over_size_cap_target_keys: tuple[str, ...]

def build_handoff(
    proof: Packet,
    *,
    releaseledger: ReleaseledgerManifest | None = None,
    coverforge: CoverforgeManifest | None = None,
) -> Handoff: ...
```

- Produces a `coverforge` JSON member through `handoff_payload()` and rendered Coverforge rows through the existing renderers.

- [ ] **Step 1: Write failing reconciliation, privacy, and rendering tests**

Extend `tests/test_handoff.py` with a local `_write_coverforge_manifest` helper
that imports no Coverforge production code. Add an aligned case:

```python
def test_build_handoff_reconciles_matching_coverforge_source(
    synthetic_release: Path, tmp_path: Path
):
    proof = _proof_packet(synthetic_release)
    cover = next(asset for asset in proof.payload["assets"] if asset["role"] == "cover")
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
    assert handoff.coverforge_linkage.matching_source_fields == (
        "sha256", "byte_size", "dimensions", "mode"
    )
    assert payload["coverforge"]["capture_id"] == coverforge.capture_id
    assert "slug" not in payload["coverforge"]
    assert "synthetic-release--bandcamp--3000x3000.jpg" not in json.dumps(
        payload["coverforge"]
    )
```

Add a discrepant case with a different source hash, one skipped target, and one
over-cap output. Assert exactly the stable finding codes
`coverforge_source_sha256_mismatch`, `coverforge_target_skipped`, and
`coverforge_output_over_size_cap`, every severity is `needs_evidence`, and
`handoff_exit_code(handoff) == 1`.

Extend the existing output test to assert synthetic temporary roots, the
Coverforge `slug`, and the Coverforge output filename do not appear in the
written JSON, Markdown, or HTML. Also assert
`"Coverforge-compatible v1 manifest capture"` appears in the HTML.

- [ ] **Step 2: Run the handoff tests to verify they fail**

Run:

```bash
python3 -m pytest tests/test_handoff.py -q
```

Expected: FAIL because `build_handoff()` has no `coverforge` keyword and the
payload has no `coverforge` member.

- [ ] **Step 3: Implement only the Coverforge handoff integration**

Import the safe model at the top of `handoff.py`:

```python
from releaseforge.coverforge import CoverforgeManifest
```

Add `CoverforgeLinkage`; add optional `coverforge` and `coverforge_linkage`
fields to `Handoff`; and extend the constructor path:

```python
def build_handoff(..., coverforge: CoverforgeManifest | None = None) -> Handoff:
    if releaseledger is None and coverforge is None:
        raise HandoffError("handoff requires at least one companion manifest")
    releaseledger_alignment, releaseledger_findings = _reconcile_releaseledger(
        proof, releaseledger
    )
    coverforge_linkage, coverforge_findings = _reconcile_coverforge(proof, coverforge)
    return Handoff(
        proof=proof,
        releaseledger=releaseledger,
        coverforge=coverforge,
        releaseledger_alignment=releaseledger_alignment,
        coverforge_linkage=coverforge_linkage,
        findings=tuple(releaseledger_findings + coverforge_findings),
    )
```

Implement `_proof_cover(proof)` to retrieve exactly one `role == "cover"`
asset and validate its SHA-256, positive byte size, positive image dimensions,
and nonblank image mode. Implement `_reconcile_coverforge()` to compare
`sha256`, `byte_size`, `dimensions`, and `mode` in that order. For each
mismatch, append a `HandoffFinding` with `severity="needs_evidence"`,
`evidence_category="captured_companion_manifest"`, and codes:

```text
coverforge_source_sha256_mismatch
coverforge_source_byte_size_mismatch
coverforge_source_dimensions_mismatch
coverforge_source_mode_mismatch
```

Then append one finding for each `skipped_target_keys` entry with code
`coverforge_target_skipped`, and one finding for each output where
`over_size_cap is True` with code `coverforge_output_over_size_cap`. Set linkage
state to `aligned` only if the combined Coverforge finding list is empty.

Add `_coverforge_payload(handoff)` that returns exactly:

```python
{
    "manifest_sha256": handoff.coverforge.manifest_sha256,
    "capture_id": handoff.coverforge.capture_id,
    "captured_output_count": len(handoff.coverforge.outputs),
    "captured_preflight_finding_count": handoff.coverforge.preflight_finding_count,
    "linkage": {
        "state": linkage.state,
        "matching_source_fields": list(linkage.matching_source_fields),
        "mismatched_source_fields": list(linkage.mismatched_source_fields),
        "skipped_target_keys": list(linkage.skipped_target_keys),
        "over_size_cap_target_keys": list(linkage.over_size_cap_target_keys),
    },
}
```

Extend `handoff_payload`, `_markdown_companion_lines`, and
`_html_companion_rows` to include this member. Pass every value through
`_markdown_value` or `_html_row`; do not add any raw string interpolation.
Update `_HANDOFF_BOUNDARY` to describe Coverforge-compatible captures using the
same explicit non-authentication/non-approval limits as the existing companion
boundary.

- [ ] **Step 4: Run the focused handoff tests to verify they pass**

Run:

```bash
python3 -m pytest tests/test_handoff.py tests/test_coverforge.py -q
```

Expected: PASS. The matching source produces an aligned handoff; every covered
discrepancy produces `needs_evidence`; and all rendered packets remain
path-free and escaped.

- [ ] **Step 5: Commit the reconciliation and renderer changes**

```bash
git add src/releaseforge/handoff.py tests/test_handoff.py
git commit -m "feat: reconcile Coverforge release evidence"
```

### Task 3: Expose the companion at the CLI and document its boundary

**Files:**

- Modify: `src/releaseforge/cli.py:20-29`
- Modify: `src/releaseforge/cli.py:144-156`
- Modify: `src/releaseforge/cli.py:226-263`
- Modify: `tests/test_handoff.py`
- Modify: `README.md`

**Interfaces:**

- Consumes `load_coverforge_manifest(path)` from `releaseforge.coverforge` and the Task 2 `build_handoff(..., coverforge=...)` signature.
- Exposes `releaseforge handoff PROOF_PACKET --coverforge COVERFORGE_MANIFEST --output OUTPUT`.

- [ ] **Step 1: Write failing CLI safety tests**

Add these tests to `tests/test_handoff.py`, and extend its `releaseforge.compare`
imports to include `load_packet`:

```python
def test_handoff_cli_writes_an_aligned_coverforge_packet(
    synthetic_release: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    proof_dir = _write_proof_packet(synthetic_release, tmp_path / "proof")
    proof = load_packet(proof_dir)
    cover = next(asset for asset in proof.payload["assets"] if asset["role"] == "cover")
    manifest = _write_coverforge_manifest(
        tmp_path / "coverforge-input" / "manifest.json",
        source_sha256=cover["sha256"],
        source_bytes=cover["byte_size"],
        source_dimensions=f"{cover['width']}x{cover['height']}",
        source_mode=cover["image_mode"],
    )

    assert main([
        "handoff", str(proof_dir), "--coverforge", str(manifest),
        "--output", str(tmp_path / "handoff"),
    ]) == 0
    assert (tmp_path / "handoff" / "RELEASE_HANDOFF.json").is_file()


def test_handoff_cli_refuses_output_inside_coverforge_manifest_parent(
    synthetic_release: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    proof_dir = _write_proof_packet(synthetic_release, tmp_path / "proof")
    manifest = _write_coverforge_manifest(tmp_path / "coverforge-input" / "manifest.json")

    assert main([
        "handoff", str(proof_dir), "--coverforge", str(manifest),
        "--output", str(manifest.parent / "handoff"),
    ]) == 2
    assert "outside input packet directories" in capsys.readouterr().err
```

- [ ] **Step 2: Run the CLI tests to verify they fail**

Run:

```bash
python3 -m pytest tests/test_handoff.py -q
```

Expected: FAIL because the parser does not recognize `--coverforge`.

- [ ] **Step 3: Wire the safe CLI path and update the user guide**

In `cli.py`, import `load_coverforge_manifest`, add this parser option, and
extend the existing `_handoff` path without duplicating output logic:

```python
handoff_parser.add_argument(
    "--coverforge", help="direct Coverforge-compatible version-1 manifest.json path"
)

coverforge = Path(args.coverforge) if args.coverforge else None

if releaseledger is None and coverforge is None:
    _error("handoff requires at least one companion manifest")
    return 2

handoff = build_handoff(
    proof,
    releaseledger=load_releaseledger_manifest(releaseledger) if releaseledger else None,
    coverforge=load_coverforge_manifest(coverforge) if coverforge else None,
)
if coverforge is not None:
    protected_roots += (coverforge.resolve().parent,)
```

Do not shadow the loaded `CoverforgeManifest` model with the path variable;
name the path `coverforge_path` and the parsed model `coverforge_manifest` in
the final implementation.

Update the README companion-handoff command, optional-flag description, output
facts, and explicit boundary. State that the Coverforge comparison only matches
the manifest's captured source facts to the Releaseforge proof cover and reports
captured skipped/over-cap targets. State that it does not prove delivery,
approval, rights, platform acceptance, or current target requirements.

- [ ] **Step 4: Run the targeted behavior and formatting checks**

Run:

```bash
python3 -m pytest tests/test_handoff.py tests/test_coverforge.py -q
python3 -m ruff check src tests
python3 -m ruff format --check src tests
```

Expected: PASS. The CLI creates an aligned Coverforge-only handoff and rejects
an output nested under the Coverforge manifest parent.

- [ ] **Step 5: Commit the CLI and documentation update**

```bash
git add src/releaseforge/cli.py tests/test_handoff.py README.md
git commit -m "feat: add Coverforge handoff input"
```

### Task 4: Verify the full package and update the existing draft PR

**Files:**

- Verify: `src/releaseforge/coverforge.py`
- Verify: `src/releaseforge/handoff.py`
- Verify: `src/releaseforge/cli.py`
- Verify: `tests/test_coverforge.py`
- Verify: `tests/test_handoff.py`
- Verify: `README.md`

**Interfaces:**

- Consumes all prior tasks on the active `codex/initial-implementation` branch.
- Produces a pushed update to existing Draft PR #1, not a merge or public-release claim.

- [ ] **Step 1: Run the full source quality suite**

Run:

```bash
python3 -m pytest -q
python3 -m ruff check src tests
python3 -m ruff format --check src tests
python3 -m build
git diff --check origin/main...HEAD
```

Expected: all tests/lint/format/build commands pass and `git diff --check`
produces no output.

- [ ] **Step 2: Smoke-test the installed wheel outside the checkout**

Run these exact actions in a new temporary directory, retaining it for audit:

```bash
python3 -m venv /tmp/releaseforge-coverforge-smoke/venv
/tmp/releaseforge-coverforge-smoke/venv/bin/python -m pip install dist/releaseforge-*.whl
/tmp/releaseforge-coverforge-smoke/venv/bin/releaseforge demo /tmp/releaseforge-coverforge-smoke/demo
```

Generate a synthetic Coverforge v1 `manifest.json` whose source facts match
the demo proof packet's cover. Run:

```bash
/tmp/releaseforge-coverforge-smoke/venv/bin/releaseforge handoff \
  /tmp/releaseforge-coverforge-smoke/demo/proof-v1 \
  --coverforge /tmp/releaseforge-coverforge-smoke/coverforge/manifest.json \
  --output /tmp/releaseforge-coverforge-smoke/handoff
```

Expected: exit `0`, exactly three `RELEASE_HANDOFF.*` files, and no absolute
temporary input path, Coverforge slug, or Coverforge output filename in the
written JSON/Markdown/HTML.

- [ ] **Step 3: Inspect the active branch and PR state before publishing**

Run:

```bash
git status --short --branch
git log --oneline origin/main..HEAD
gh pr view 1 --repo notgabriels-sys/releaseforge --json url,state,isDraft,mergeable,statusCheckRollup
```

Expected: only intentional tracked changes are committed, the active PR remains
Draft/open, and no claim is made that it was merged or released.

- [ ] **Step 4: Push the active non-main branch normally and re-read PR state**

Run:

```bash
git push origin codex/initial-implementation
gh pr view 1 --repo notgabriels-sys/releaseforge --json url,state,isDraft,mergeable,headRefOid,statusCheckRollup
```

Expected: the branch updates Draft PR #1. Do not force-push, mark the PR ready,
merge it, publish a package, or contact a pilot user.
