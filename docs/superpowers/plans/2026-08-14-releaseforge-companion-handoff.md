# Releaseforge Companion Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local-only Releaseforge `handoff` command that reconciles a validated Releaseforge proof packet with selected Mastergate and/or Releaseledger build manifests and writes a portable, evidence-bounded dossier.

**Architecture:** Add one focused `releaseforge.handoff` module with immutable companion models, strict version-1 parsers, reconciliation, deterministic payload construction, escaped renderers, and a new-directory-only writer. Extend the existing argparse CLI with a required-output `handoff` subcommand. The module imports Releaseforge's existing packet validator but never imports Mastergate or Releaseledger as dependencies.

**Tech Stack:** Python 3.11+, standard library, existing Releaseforge package, pytest, ruff.

## Global Constraints

- No runtime dependency additions, network requests, subprocesses, accounts, uploads, analytics, credentials, payment flow, or source-media reads.
- The command accepts a validated Releaseforge proof packet plus at least one direct companion `manifest.json` path.
- Strictly accept only documented Mastergate and Releaseledger version-1 build manifests; reject malformed/unknown schema fields and unsupported versions before output.
- Never write inside the Releaseforge proof-packet directory or a companion manifest parent directory; never overwrite an existing output path.
- Output exactly `RELEASE_HANDOFF.md`, `RELEASE_HANDOFF.json`, and `RELEASE_HANDOFF.html` without absolute input paths, directory names, source filenames, source media, or source TOML paths.
- A SHA-256 match is a match between captured values only. Never claim current-file verification, approval, ownership, external delivery, platform acceptance, or release readiness.
- All companion-controlled output must be escaped in Markdown and HTML.
- Follow red-green-refactor: every production behavior begins with a focused failing pytest assertion and is verified before code is added.

---

### Task 1: Strict companion-manifest models and parser boundaries

**Files:**
- Create: `src/releaseforge/handoff.py`
- Modify: `tests/helpers.py`
- Create: `tests/test_handoff.py`

**Interfaces:**
- Consumes: `pathlib.Path`, `json`, `hashlib`.
- Produces: `HandoffError`, `MastergateManifest`, `ReleaseledgerManifest`, `load_mastergate_manifest(path)`, and `load_releaseledger_manifest(path)`.
- Contract: each loader returns a frozen model containing only safe, schema-validated fields plus the SHA-256 of the manifest bytes. It rejects non-object JSON, unexpected/missing fields, unsupported schema versions, invalid types, unsafe filename values, and Mastergate manifests that do not represent a passing build.

- [ ] **Step 1: Write the failing parser tests**

```python
def test_load_mastergate_manifest_keeps_only_safe_captured_fields(tmp_path):
    manifest_path = write_mastergate_manifest(tmp_path / "mastergate.json")

    manifest = load_mastergate_manifest(manifest_path)

    assert manifest.manifest_sha256 == sha256_file(manifest_path)
    assert manifest.measurements[0].sha256 == "a" * 64
    assert not hasattr(manifest, "input_directory")


def test_load_releaseledger_manifest_rejects_an_unknown_field(tmp_path):
    manifest_path = write_releaseledger_manifest(tmp_path / "ledger.json", extra_root={"path": "/private"})

    with pytest.raises(HandoffError, match="unexpected field"):
        load_releaseledger_manifest(manifest_path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_handoff.py -q`

Expected: FAIL because `releaseforge.handoff` and its loaders do not exist.

- [ ] **Step 3: Implement the smallest strict loaders**

```python
def load_mastergate_manifest(path: Path | str) -> MastergateManifest:
    payload, manifest_sha256 = _load_json_object(path, "Mastergate manifest")
    _expect_exact_keys(payload, _MASTERGATE_FIELDS, "Mastergate manifest")
    if payload["schema_version"] != 1 or payload["declared_file_checks_passed"] is not True:
        raise HandoffError("Mastergate manifest is not a passing version-1 build manifest")
    return _parse_mastergate(payload, manifest_sha256)
```

Parse release metadata/tracks and measurements into frozen dataclasses. Permit only bare filenames for mastergate measurements, require 64-character lowercase SHA-256 text, and do not retain `contract_source`, `input`, or Releaseledger `source` values in returned models.

- [ ] **Step 4: Run parser tests to verify they pass**

Run: `python -m pytest tests/test_handoff.py -q`

Expected: PASS for accepted safe manifests and expected `HandoffError` cases.

- [ ] **Step 5: Commit the parser boundary**

```bash
git add src/releaseforge/handoff.py tests/helpers.py tests/test_handoff.py
git commit -m "feat: validate companion build manifests"
```

### Task 2: Reconcile captured audio hashes and declared metadata

**Files:**
- Modify: `src/releaseforge/handoff.py`
- Modify: `tests/test_handoff.py`

**Interfaces:**
- Consumes: `releaseforge.compare.Packet`, `MastergateManifest | None`, `ReleaseledgerManifest | None`.
- Produces: `Handoff`, `HandoffFinding`, `build_handoff(proof, *, mastergate=None, releaseledger=None)`, and `handoff_exit_code(handoff)`.
- Contract: `build_handoff` requires at least one companion. It maps Releaseforge `.wav` assets to Mastergate measurements only by equal captured SHA-256. It compares Releaseledger's shared declared fields and numbered-track coverage without treating either declaration as verified; Releaseforge proof-packet version 1 does not retain track titles.

- [ ] **Step 1: Write the failing reconciliation tests**

```python
def test_build_handoff_records_matching_captured_wav_hashes_and_declarations(proof_packet, tmp_path):
    handoff = build_handoff(
        proof_packet,
        mastergate=load_mastergate_manifest(write_mastergate_manifest(tmp_path / "mastergate.json", sha256=proof_track_sha(proof_packet))),
        releaseledger=load_releaseledger_manifest(write_releaseledger_manifest(tmp_path / "ledger.json", matching_proof=proof_packet)),
    )

    assert handoff.is_aligned is True
    assert handoff.findings == ()
    assert handoff.mastergate_linkage.matched_releaseforge_wav_roles == ("track:1",)


def test_build_handoff_emits_needs_evidence_for_mismatched_companion_values(proof_packet, tmp_path):
    handoff = build_handoff(
        proof_packet,
        mastergate=load_mastergate_manifest(write_mastergate_manifest(tmp_path / "mastergate.json", sha256="b" * 64)),
        releaseledger=load_releaseledger_manifest(write_releaseledger_manifest(tmp_path / "ledger.json", release_title="Different title")),
    )

    assert handoff.is_aligned is False
    assert {finding.code for finding in handoff.findings} == {"mastergate_wav_hash_unmatched", "releaseledger_title_mismatch"}
    assert handoff_exit_code(handoff) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_handoff.py -q`

Expected: FAIL because reconciliation models and `build_handoff` do not exist.

- [ ] **Step 3: Implement the smallest deterministic reconciliation**

```python
def build_handoff(
    proof: Packet,
    *,
    mastergate: MastergateManifest | None = None,
    releaseledger: ReleaseledgerManifest | None = None,
) -> Handoff:
    if mastergate is None and releaseledger is None:
        raise HandoffError("handoff requires at least one companion manifest")
    findings = _mastergate_findings(proof, mastergate) + _releaseledger_findings(proof, releaseledger)
    return Handoff(proof=proof, mastergate=mastergate, releaseledger=releaseledger, findings=tuple(findings))
```

Use only canonicalized dictionaries/lists and stable ordering. Emit `needs_evidence` findings for discrepancies, not `blocker` findings and not an external-status verdict.

- [ ] **Step 4: Run reconciliation tests to verify they pass**

Run: `python -m pytest tests/test_handoff.py -q`

Expected: PASS with matched and mismatched synthetic companion manifests.

- [ ] **Step 5: Commit reconciliation behavior**

```bash
git add src/releaseforge/handoff.py tests/test_handoff.py
git commit -m "feat: reconcile companion release evidence"
```

### Task 3: Render a deterministic, path-free handoff packet

**Files:**
- Modify: `src/releaseforge/handoff.py`
- Modify: `tests/test_handoff.py`

**Interfaces:**
- Consumes: `Handoff`, output `Path`, and protected input roots.
- Produces: `handoff_payload(handoff)`, `render_handoff_markdown(handoff)`, `render_handoff_html(handoff)`, `write_handoff_packet(handoff, output_dir, *, protected_roots)`.
- Contract: payload contains `schema_version`, `handoff_id`, `proof_id`, companion manifest hashes, limited linkage/alignment records, and structured findings. The writer creates exactly three files in one new safe directory.

- [ ] **Step 1: Write the failing output safety and rendering tests**

```python
def test_write_handoff_packet_omits_input_paths_and_escapes_html(handoff, tmp_path):
    destination = tmp_path / "handoff-output"

    write_handoff_packet(handoff, destination, protected_roots=(tmp_path / "proof",))

    html = (destination / "RELEASE_HANDOFF.html").read_text(encoding="utf-8")
    payload = json.loads((destination / "RELEASE_HANDOFF.json").read_text(encoding="utf-8"))
    assert str(tmp_path) not in html
    assert "&lt;script&gt;" in html
    assert payload["handoff_id"].startswith("rfh_")


def test_write_handoff_packet_refuses_output_inside_an_input_tree(handoff, tmp_path):
    protected_root = tmp_path / "proof"
    protected_root.mkdir()

    with pytest.raises(HandoffError, match="outside input packet directories"):
        write_handoff_packet(handoff, protected_root / "handoff", protected_roots=(protected_root,))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_handoff.py -q`

Expected: FAIL because packet renderers and writer do not exist.

- [ ] **Step 3: Implement payload, renderers, and writer**

```python
def handoff_id(payload: Mapping[str, Any]) -> str:
    canonical = {key: value for key, value in payload.items() if key != "handoff_id"}
    encoded = json.dumps(canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return f"rfh_{hashlib.sha256(encoded).hexdigest()[:20]}"
```

Render every companion-derived value through a Markdown cell helper and `html.escape`. Before `mkdir`, resolve the destination, reject any protected-root nesting, and reject any existing directory. Write only `RELEASE_HANDOFF.md`, `RELEASE_HANDOFF.json`, and `RELEASE_HANDOFF.html`.

- [ ] **Step 4: Run output tests to verify they pass**

Run: `python -m pytest tests/test_handoff.py -q`

Expected: PASS with deterministic JSON, escaped HTML, no source paths, and protected-output rejection.

- [ ] **Step 5: Commit the portable packet writer**

```bash
git add src/releaseforge/handoff.py tests/test_handoff.py
git commit -m "feat: write portable companion handoff packets"
```

### Task 4: Expose and document the `handoff` command

**Files:**
- Modify: `src/releaseforge/cli.py`
- Modify: `README.md`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_handoff.py`

**Interfaces:**
- Consumes: `releaseforge handoff PROOF_PACKET --mastergate PATH --releaseledger PATH --output PATH`.
- Produces: human-readable summary to stdout on success/mismatch, normal errors on stderr, and statuses `0`, `1`, or `2` as described in the specification.
- Contract: CLI must call existing `load_packet` first, require at least one companion flag, and protect the proof root plus each supplied manifest parent as output roots.

- [ ] **Step 1: Write failing CLI tests**

```python
def test_handoff_cli_writes_an_aligned_packet(proof_dir, mastergate_manifest, capsys, tmp_path):
    result = main([
        "handoff", str(proof_dir), "--mastergate", str(mastergate_manifest),
        "--output", str(tmp_path / "handoff"),
    ])

    assert result == 0
    assert (tmp_path / "handoff" / "RELEASE_HANDOFF.json").exists()
    assert "Wrote release handoff packet" in capsys.readouterr().out


def test_handoff_cli_requires_a_companion_manifest(proof_dir, capsys, tmp_path):
    assert main(["handoff", str(proof_dir), "--output", str(tmp_path / "handoff")]) == 2
    assert "at least one companion" in capsys.readouterr().err
```

- [ ] **Step 2: Run CLI tests to verify they fail**

Run: `python -m pytest tests/test_cli.py tests/test_handoff.py -q`

Expected: FAIL because argparse has no `handoff` subcommand.

- [ ] **Step 3: Implement CLI routing and README guidance**

```python
handoff_parser = commands.add_parser("handoff", help="write a local companion-evidence handoff packet")
handoff_parser.add_argument("proof_packet")
handoff_parser.add_argument("--mastergate")
handoff_parser.add_argument("--releaseledger")
handoff_parser.add_argument("--output", "-o", required=True)
```

Route all loader/writer errors through `ComparisonError`/`HandoffError` handling and retain valid JSON/quiet input behavior. Document the exact supported upstream build outputs, the no-source-read/no-path-disclosure boundary, output filenames, exit statuses, and no external-approval claims.

- [ ] **Step 4: Run CLI and full project verification**

Run:

```bash
python -m pytest -q
python -m ruff check src tests
python -m ruff format --check src tests
python -m compileall -q src
git diff --check
python -m build
```

Expected: all tests, lint, format, compilation, whitespace, and isolated package build pass.

- [ ] **Step 5: Commit and push the complete feature**

```bash
git add src/releaseforge/handoff.py src/releaseforge/cli.py tests/test_handoff.py tests/test_cli.py tests/helpers.py README.md
git commit -m "feat: add companion evidence handoff"
git push origin codex/initial-implementation
gh pr checks 1 --repo notgabriels-sys/releaseforge --watch
```
