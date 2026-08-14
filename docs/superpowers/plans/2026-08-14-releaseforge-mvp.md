# Releaseforge MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an offline Python application that turns a declared local music-release folder into a deterministic release-proof packet without changing or uploading the source assets.

**Architecture:** A strict TOML parser creates immutable release-domain objects. Inspection reads local asset facts and hashes, evaluation turns declared workflow rules into severity-tagged findings, and report rendering emits one shared model as Markdown, JSON, and a self-contained HTML review. The CLI keeps `check` read-only and lets `build` create a fresh packet only.

**Tech Stack:** Python 3.11+, standard library (`tomllib`, `wave`, `hashlib`, `json`, `html`, `pathlib`), Pillow, pytest, Ruff, build, setuptools.

## Global Constraints

- Source assets and `release.toml` are read-only for `check` and `build`.
- All asset paths are relative to the release directory, resolve inside it, and name regular files.
- No network requests, subprocess execution, analytics, credentials, cloud storage, or destructive file operations.
- Absolute source paths must not appear in a generated packet.
- A passing result means only that local facts and declarations meet the selected profile; it is not a rights, approval, distributor, or platform-compliance determination.
- `build` refuses to overwrite an existing output directory.
- Reports must distinguish `verified_file_fact`, `declared`, `needs_evidence`, and `blocker`.

---

### Task 1: Package skeleton and strict release plan parser

**Files:**
- Create: `.gitignore`
- Create: `pyproject.toml`
- Create: `src/releaseforge/__init__.py`
- Create: `src/releaseforge/config.py`
- Create: `tests/__init__.py`
- Create: `tests/helpers.py`
- Create: `tests/test_config.py`
- Create: `examples/release.toml`

**Interfaces:**
- Consumes: a release directory and its `release.toml` file.
- Produces: `ReleasePlan`, `TrackPlan`, `RequirementPlan`, and `ConfigError` from `releaseforge.config`.

- [ ] **Step 1: Write failing parser tests**

```python
def test_load_plan_accepts_complete_relative_release(tmp_path):
    plan = load_plan(write_plan(tmp_path))
    assert plan.release.title == "Synthetic Release"
    assert plan.tracks[0].relative_path.as_posix() == "audio/01-track.wav"


def test_load_plan_rejects_path_escape(tmp_path):
    with pytest.raises(ConfigError, match="must stay inside"):
        load_plan(write_plan(tmp_path, cover_path="../cover.jpg"))
```

- [ ] **Step 2: Run the parser tests to verify they fail**

Run: `python -m pytest tests/test_config.py -v`

Expected: FAIL because `releaseforge.config` is not implemented.

- [ ] **Step 3: Implement immutable plan models and strict TOML validation**

```python
@dataclass(frozen=True)
class ReleasePlan:
    root: Path
    release: ReleaseMeta
    requirements: RequirementPlan
    cover_relative_path: PurePosixPath
    tracks: tuple[TrackPlan, ...]
    declarations: DeclarationPlan


def load_plan(release_dir: Path) -> ReleasePlan:
    """Load release_dir / 'release.toml' and reject unknown or unsafe structure."""
```

Validate required sections, nonblank strings, ISO dates, extension values,
declared status enums, paths, duplicate paths, and contiguous track numbers.

- [ ] **Step 4: Run parser tests and the full suite**

Run: `python -m pytest tests/test_config.py -v && python -m pytest -q`

Expected: PASS.

- [ ] **Step 5: Commit the parser foundation**

```bash
git add .gitignore pyproject.toml src/releaseforge tests examples/release.toml
git commit -m "feat: add strict release plan parser"
```

### Task 2: Read-only asset inspection

**Files:**
- Create: `src/releaseforge/inspect.py`
- Create: `tests/test_inspect.py`
- Modify: `tests/helpers.py`

**Interfaces:**
- Consumes: `ReleasePlan` from `releaseforge.config`.
- Produces: `AssetFact`, `inspect_release(plan)`, and `InspectionError` from `releaseforge.inspect`.

- [ ] **Step 1: Write failing inspection tests**

```python
def test_inspect_release_records_hash_and_image_geometry(synthetic_release):
    facts = inspect_release(load_plan(synthetic_release))
    cover = facts.by_role("cover")
    assert cover.sha256
    assert (cover.width, cover.height, cover.mode) == (3000, 3000, "RGB")


def test_inspect_release_records_pcm_wav_duration(synthetic_release):
    track = inspect_release(load_plan(synthetic_release)).by_role("track:1")
    assert track.duration_seconds == pytest.approx(1.0)
```

- [ ] **Step 2: Run the inspection tests to verify they fail**

Run: `python -m pytest tests/test_inspect.py -v`

Expected: FAIL because `releaseforge.inspect` is not implemented.

- [ ] **Step 3: Implement file facts without writing source files**

```python
@dataclass(frozen=True)
class AssetFact:
    role: str
    relative_path: PurePosixPath
    byte_size: int
    sha256: str
    extension: str
    width: int | None = None
    height: int | None = None
    image_mode: str | None = None
    duration_seconds: float | None = None
```

Use Pillow only for the declared cover and `wave` only for `.wav` tracks. Hash
bytes with SHA-256 and propagate a clear read error for missing/unreadable
assets. Do not follow a path outside the plan root.

- [ ] **Step 4: Run inspection tests and the full suite**

Run: `python -m pytest tests/test_inspect.py -v && python -m pytest -q`

Expected: PASS.

- [ ] **Step 5: Commit read-only inspection**

```bash
git add src/releaseforge/inspect.py tests/test_inspect.py tests/helpers.py
git commit -m "feat: inspect local release assets"
```

### Task 3: Deterministic evidence-aware evaluation

**Files:**
- Create: `src/releaseforge/evaluate.py`
- Create: `tests/test_evaluate.py`

**Interfaces:**
- Consumes: `ReleasePlan` and inspection output.
- Produces: `Finding`, `Evaluation`, and `evaluate_release(plan, facts)` from `releaseforge.evaluate`.

- [ ] **Step 1: Write failing evaluation tests**

```python
def test_evaluation_passes_when_facts_match_declared_profile(synthetic_release):
    evaluation = evaluate_release_plan(synthetic_release)
    assert evaluation.blocker_count == 0
    assert evaluation.needs_evidence_count == 0


def test_evaluation_blocks_undersized_cover_and_pending_rights(synthetic_release):
    evaluation = evaluate_release_plan(synthetic_release, cover_size=(1200, 1200), rights="pending")
    assert {finding.code for finding in evaluation.findings} >= {
        "cover_below_declared_minimum",
        "rights_review_needs_evidence",
    }
```

- [ ] **Step 2: Run evaluation tests to verify they fail**

Run: `python -m pytest tests/test_evaluate.py -v`

Expected: FAIL because `releaseforge.evaluate` is not implemented.

- [ ] **Step 3: Implement evaluation and explicit evidence categories**

```python
@dataclass(frozen=True)
class Finding:
    code: str
    severity: Literal["blocker", "warning", "needs_evidence", "info"]
    evidence_category: Literal["verified_file_fact", "declared", "needs_evidence", "blocker"]
    message: str
    subject: str


def evaluate_release(plan: ReleasePlan, facts: Inspection) -> Evaluation:
    """Evaluate only the plan's declared workflow requirements."""
```

Evaluate cover geometry, allowed audio extensions, track facts, and required
declaration status without importing any platform policy. Generate stable
finding codes and source-independent messages.

- [ ] **Step 4: Run evaluation tests and the full suite**

Run: `python -m pytest tests/test_evaluate.py -v && python -m pytest -q`

Expected: PASS.

- [ ] **Step 5: Commit the evaluator**

```bash
git add src/releaseforge/evaluate.py tests/test_evaluate.py
git commit -m "feat: evaluate release evidence and workflow gates"
```

### Task 4: Portable proof report renderers

**Files:**
- Create: `src/releaseforge/report.py`
- Create: `tests/test_report.py`

**Interfaces:**
- Consumes: `ReleasePlan`, inspection data, and `Evaluation`.
- Produces: `report_payload`, `render_markdown`, `render_html`, and `write_packet` from `releaseforge.report`.

- [ ] **Step 1: Write failing report tests**

```python
def test_write_packet_creates_three_portable_outputs(synthetic_release, tmp_path):
    packet = write_packet(make_report(synthetic_release), tmp_path / "proof")
    assert {path.name for path in packet.iterdir()} == {
        "RELEASE_PROOF.md", "RELEASE_PROOF.json", "RELEASE_READINESS.html"
    }
    assert str(synthetic_release) not in (packet / "RELEASE_PROOF.md").read_text()


def test_html_escapes_declared_text(synthetic_release, tmp_path):
    html = render_html(make_report(synthetic_release, title="<unsafe>"))
    assert "&lt;unsafe&gt;" in html
```

- [ ] **Step 2: Run report tests to verify they fail**

Run: `python -m pytest tests/test_report.py -v`

Expected: FAIL because `releaseforge.report` is not implemented.

- [ ] **Step 3: Implement deterministic Markdown, JSON, and offline HTML**

```python
def write_packet(report: Report, output_dir: Path) -> Path:
    """Create output_dir once and write exactly the three documented files."""
```

Use `json.dumps(..., sort_keys=True, indent=2)`, `html.escape`, inline CSS,
and no external URLs. Show the decision state first, followed by blockers,
boundaries, declared release metadata, verified asset facts, and findings.

- [ ] **Step 4: Run report tests and the full suite**

Run: `python -m pytest tests/test_report.py -v && python -m pytest -q`

Expected: PASS.

- [ ] **Step 5: Commit the proof packet**

```bash
git add src/releaseforge/report.py tests/test_report.py
git commit -m "feat: generate portable release proof packets"
```

### Task 5: Safe command-line workflow and documentation

**Files:**
- Create: `src/releaseforge/cli.py`
- Create: `tests/test_cli.py`
- Create: `README.md`
- Create: `LICENSE`
- Modify: `src/releaseforge/__init__.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: parser, inspection, evaluation, and report interfaces from Tasks 1–4.
- Produces: `releaseforge init`, `releaseforge check`, and `releaseforge build` commands.

- [ ] **Step 1: Write failing CLI tests**

```python
def test_check_is_read_only_and_reports_a_decision(synthetic_release, capsys):
    before = tree_digest(synthetic_release)
    assert main(["check", str(synthetic_release)]) == 0
    assert tree_digest(synthetic_release) == before
    assert "LOCAL RELEASE PROOF" in capsys.readouterr().out


def test_build_refuses_an_existing_output(synthetic_release, tmp_path, capsys):
    output = tmp_path / "proof"
    output.mkdir()
    assert main(["build", str(synthetic_release), "--output", str(output)]) == 2
    assert "already exists" in capsys.readouterr().err
```

- [ ] **Step 2: Run CLI tests to verify they fail**

Run: `python -m pytest tests/test_cli.py -v`

Expected: FAIL because `releaseforge.cli` is not implemented.

- [ ] **Step 3: Implement commands and package entry point**

```python
def main(argv: Sequence[str] | None = None) -> int:
    """Return 0 for no blockers, 1 for blockers, and 2 for usage or I/O errors."""
```

`init` writes only a nonexistent `release.toml`; `check` never writes; `build`
requires a nonexistent output directory. Document the exact boundaries and a
copy-paste quick start in the README. Use the MIT license for the open core.

- [ ] **Step 4: Run all unit tests and static checks**

Run: `python -m pytest -q && python -m ruff check src tests && python -m ruff format --check src tests`

Expected: PASS.

- [ ] **Step 5: Commit the public command workflow**

```bash
git add README.md LICENSE pyproject.toml src/releaseforge/cli.py src/releaseforge/__init__.py tests/test_cli.py
git commit -m "feat: add releaseforge command workflow"
```

### Task 6: Packaging, fresh-install integration, and security-boundary verification

**Files:**
- Modify: `README.md`
- Modify: `tests/test_cli.py`
- Create: `tests/test_security_boundaries.py`

**Interfaces:**
- Consumes: the published package wheel and CLI.
- Produces: reproducible validation evidence for the draft PR.

- [ ] **Step 1: Write failing boundary tests**

```python
def test_generated_reports_state_the_evidence_boundary(synthetic_release, tmp_path):
    packet = build_packet(synthetic_release, tmp_path)
    assert "does not establish" in (packet / "RELEASE_PROOF.md").read_text()


def test_source_tree_is_unchanged_after_build(synthetic_release, tmp_path):
    before = tree_digest(synthetic_release)
    build_packet(synthetic_release, tmp_path)
    assert tree_digest(synthetic_release) == before
```

- [ ] **Step 2: Run boundary tests to verify they fail**

Run: `python -m pytest tests/test_security_boundaries.py -v`

Expected: FAIL until the final report copy and integration helpers are complete.

- [ ] **Step 3: Complete packaging and integration coverage**

Build a wheel, install it into a fresh temporary virtual environment, generate
a synthetic release proof packet with the installed CLI, and assert the output
names, boundary text, deterministic JSON, and source immutability.

- [ ] **Step 4: Run the final validation matrix**

Run:

```bash
python -m pytest -q
python -m ruff check src tests
python -m ruff format --check src tests
python -m compileall -q src
python -m build --no-isolation
rg -n --glob '*.py' 'subprocess|socket|requests|urllib|http\\.client|ftplib|webbrowser|os\\.remove|shutil\\.rmtree|\\.unlink\\(' src tests && exit 1 || true
rg -n -i --glob '!*.egg-info/**' --glob '!build/**' '(api[_-]?key|secret|password|token)\\s*=' . && exit 1 || true
```

Expected: all commands pass and both capability scans produce no matches.

- [ ] **Step 5: Commit final documentation and verification coverage**

```bash
git add README.md tests/test_cli.py tests/test_security_boundaries.py
git commit -m "test: verify release proof boundaries"
```

## Self-review

- Spec coverage: Tasks 1–5 implement the input contract, evidence model,
  offline reports, and safe CLI workflow. Task 6 verifies source immutability,
  package installability, and the no-network/no-subprocess boundary.
- Placeholder scan: no implementation-critical placeholders, generic test
  instructions, or undefined interfaces remain.
- Type consistency: `ReleasePlan` flows from config to inspection/evaluation;
  the resulting report flows from report rendering to CLI. All names used by
  later tasks are defined in the prior task interfaces.
