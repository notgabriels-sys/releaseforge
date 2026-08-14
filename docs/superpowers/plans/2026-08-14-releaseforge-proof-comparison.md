# Releaseforge Proof Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic proof IDs and a read-only local comparison command for two Releaseforge proof packets.

**Architecture:** Packet rendering computes a SHA-256-derived ID from canonical JSON excluding the ID field. A comparison module validates packet inputs and integrity, compares stable semantic sections, and returns categorized immutable changes. The CLI renders that one model as human text or JSON.

**Tech Stack:** Python 3.11+, standard library (`hashlib`, `json`, `pathlib`), existing Releaseforge package, pytest, Ruff.

## Global Constraints

- Comparison reads only packet JSON; it does not read or modify source media.
- A proof ID is deterministic and calculated over the full report payload excluding `proof_id`.
- Input paths may be packet directories or direct JSON files; no output is written by `compare`.
- Absolute paths must not appear in comparison output.
- A comparison shows captured differences only; it never establishes approval, rights, release readiness, or which packet is correct.

---

### Task 1: Deterministic packet proof IDs

**Files:**
- Modify: `src/releaseforge/report.py`
- Modify: `tests/test_report.py`

**Interfaces:**
- Consumes: the existing report model.
- Produces: `proof_id` in `report_payload(report)` and `packet_proof_id(payload)`.

- [ ] **Step 1: Write failing proof-ID tests**

```python
def test_payload_has_a_stable_proof_id(synthetic_release):
    first = report_payload(make_synthetic_report(synthetic_release))
    second = report_payload(make_synthetic_report(synthetic_release))
    assert first["proof_id"] == second["proof_id"]
    assert first["proof_id"].startswith("rfp_")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_report.py::test_payload_has_a_stable_proof_id -v`

Expected: FAIL because packet payloads have no proof ID.

- [ ] **Step 3: Implement canonical ID generation**

```python
def packet_proof_id(payload: Mapping[str, Any]) -> str:
    """Return rfp_ plus a SHA-256 prefix for payload content excluding proof_id."""
```

Canonicalize with sorted JSON keys and compact separators. Do not include
filesystem paths, timestamps, or the proof ID itself.

- [ ] **Step 4: Run report tests and commit**

Run: `python -m pytest tests/test_report.py -v`

Expected: PASS.

```bash
git add src/releaseforge/report.py tests/test_report.py
git commit -m "feat: add deterministic release proof IDs"
```

### Task 2: Read-only semantic packet comparison

**Files:**
- Create: `src/releaseforge/compare.py`
- Create: `tests/test_compare.py`

**Interfaces:**
- Consumes: `RELEASE_PROOF.json` packets and `packet_proof_id`.
- Produces: `Packet`, `Change`, `Comparison`, `load_packet`, and `compare_packets`.

- [ ] **Step 1: Write failing comparison tests**

```python
def test_compare_reports_verified_asset_bytes_changed(before_packet, after_packet):
    comparison = compare_packets(load_packet(before_packet), load_packet(after_packet))
    assert {change.code for change in comparison.changes} >= {"asset_bytes_changed"}


def test_compare_rejects_a_packet_with_an_invalid_proof_id(packet_path):
    with pytest.raises(ComparisonError, match="does not match"):
        load_packet(packet_path)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_compare.py -v`

Expected: FAIL because `releaseforge.compare` is not implemented.

- [ ] **Step 3: Implement packet loading, integrity validation, and categories**

```python
@dataclass(frozen=True)
class Change:
    code: str
    category: Literal["verified_asset", "declared_release", "declared_profile", "declaration", "decision", "finding"]
    subject: str
    before: object | None
    after: object | None
```

Compare asset roles by SHA-256, local facts, and relative paths; compare
declared sections and findings by stable values. Sort changes by category,
subject, and code before returning them.

- [ ] **Step 4: Run comparison tests and commit**

Run: `python -m pytest tests/test_compare.py -v && python -m pytest -q`

Expected: PASS.

```bash
git add src/releaseforge/compare.py tests/test_compare.py
git commit -m "feat: compare local release proof packets"
```

### Task 3: Compare command, docs, and final validation

**Files:**
- Modify: `src/releaseforge/cli.py`
- Modify: `tests/test_cli.py`
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-08-14-releaseforge-mvp-design.md`

**Interfaces:**
- Consumes: `compare_packets` and comparison renderers.
- Produces: `releaseforge compare BEFORE AFTER [--json]`.

- [ ] **Step 1: Write failing CLI tests**

```python
def test_compare_returns_one_for_captured_changes(before_packet, after_packet, capsys):
    assert main(["compare", str(before_packet), str(after_packet)]) == 1
    assert "RELEASE PROOF COMPARISON" in capsys.readouterr().out
```

- [ ] **Step 2: Run the CLI test to verify it fails**

Run: `python -m pytest tests/test_cli.py::test_compare_returns_one_for_captured_changes -v`

Expected: FAIL because the command does not exist.

- [ ] **Step 3: Implement safe rendering and command behavior**

Add a `compare` subcommand that reads either direct JSON files or packet
directories. Default output is concise human text; `--json` is deterministic
and contains no absolute paths. Return 0 for equal packets, 1 for differences,
and 2 for invalid input/integrity failures.

- [ ] **Step 4: Run final validation and commit**

Run:

```bash
python -m pytest -q
python -m ruff check src tests
python -m ruff format --check src tests
python -m compileall -q src
python -m build --no-isolation
```

```bash
git add README.md docs/superpowers src/releaseforge/cli.py tests/test_cli.py
git commit -m "feat: add release proof comparison command"
```
