# Releaseforge CI and Installed-Artifact Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing Releaseforge proof workflow reproducibly testable on GitHub and prove that both built distributions expose a working synthetic demo.

**Architecture:** Commit the existing project's uv resolution as `uv.lock`, then use a least-privilege GitHub Actions workflow for a compact OS/Python test matrix and a separate lint/build/artifact-smoke job. The smoke job invokes only the packaged `releaseforge` command against new temporary synthetic-demo directories, proving packaging and runtime dependencies without touching real release files.

**Tech Stack:** Python 3.11/3.13, uv 0.11.14, pytest, Ruff, setuptools distributions, GitHub Actions.

## Global Constraints

- Build on `codex/releaseforge-ci`, with `codex/initial-implementation` as the draft-PR base.
- Preserve the existing Python requirement floor: `>=3.11`.
- Keep runtime dependencies unchanged; `uv.lock` records the existing Pillow and dev-tool resolution only.
- Pin third-party Actions to full commit SHAs and set workflow permissions to `contents: read`.
- The workflow must not publish packages, create releases, upload media, access release/client/distributor systems, or make readiness/compliance claims.
- Use only new temporary synthetic-demo destinations in local or CI smoke verification.
- Do not merge or mark any existing draft PR ready.

---

## File structure

| File | Responsibility |
| --- | --- |
| `uv.lock` | Exact dependency resolution for the existing project and `dev` extra. |
| `.github/workflows/ci.yml` | Read-only GitHub CI matrix, lint/build, and installed-artifact smoke contract. |
| `README.md` | Visible CI status link and a narrow explanation of what CI does and does not verify. |

### Task 1: Commit a reproducible existing environment

**Files:**
- Add: `uv.lock`

**Interfaces:**
- Consumes: existing `pyproject.toml`, including `Pillow>=10.0` and the `dev` extra.
- Produces: a committed lock compatible with `uv sync --locked --extra dev`.

- [ ] **Step 1: Regenerate the lock from the declared project dependencies**

Run:

```bash
uv lock
```

Expected: `uv.lock` exists at the repository root and contains the existing
runtime `Pillow` requirement plus the declared development tooling.

- [ ] **Step 2: Prove the lock can create the development environment without re-resolution**

Run:

```bash
uv sync --locked --extra dev
uv run --frozen pytest -q
```

Expected: all 64 current tests pass. This verifies the committed lock rather
than an ambient Python environment.

- [ ] **Step 3: Inspect lock scope before commit**

Run:

```bash
git diff --check
git diff --stat -- uv.lock
```

Expected: only deterministic dependency-resolution metadata is added; no source,
media, credential, or local-environment paths appear.

- [ ] **Step 4: Commit the lock**

```bash
git add uv.lock
git commit -m "build: lock Releaseforge dependencies"
```

### Task 2: Add least-privilege CI and artifact smoke coverage

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `uv.lock`, `pyproject.toml`, the `releaseforge` console entry point,
  and the existing synthetic `releaseforge demo DESTINATION` command.
- Produces: GitHub checks named `test` and `lint-build-and-smoke`; no workflow
  outputs, releases, artifacts, or external product actions.

- [ ] **Step 1: Create the workflow with exact triggers, permissions, and concurrency**

Write `.github/workflows/ci.yml` beginning with:

```yaml
name: CI

on:
  push:
  pull_request:

permissions:
  contents: read

concurrency:
  group: ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

Expected: the workflow can only read repository contents and newer pushes cancel
redundant in-progress checks for the same ref.

- [ ] **Step 2: Add the three-entry test matrix**

Use a `test` job with `fail-fast: false` and these exact matrix entries:

```yaml
include:
  - os: ubuntu-latest
    python-version: "3.11"
  - os: ubuntu-latest
    python-version: "3.13"
  - os: macos-latest
    python-version: "3.13"
```

Each matrix job must pin the following Actions exactly as shown, install the
locked `dev` environment, and run tests:

```yaml
- uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
- uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0
  with:
    python-version: ${{ matrix.python-version }}
- uses: astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d # v10.0.1
  with:
    version: "0.11.14"
    enable-cache: true
- run: uv sync --locked --extra dev
- run: uv run --frozen pytest -q
```

Expected: the 3.11 floor, current Linux, and current macOS paths all run the
same existing test suite.

- [ ] **Step 3: Add the Ubuntu lint/build/install-smoke job**

Create `lint-build-and-smoke` on `ubuntu-latest` with Python 3.11 and the same
pinned checkout/setup-python/setup-uv steps. After `uv sync --locked --extra dev`,
run:

```yaml
- run: uv run --frozen ruff check src tests
- run: uv run --frozen ruff format --check src tests
- run: uv build --no-sources
```

Then add one Bash smoke step with this exact behavior:

```bash
set -euo pipefail
wheel_path="$(find dist -maxdepth 1 -type f -name '*.whl' -print -quit)"
sdist_path="$(find dist -maxdepth 1 -type f -name '*.tar.gz' -print -quit)"
test -n "$wheel_path"
test -n "$sdist_path"

for artifact in "$wheel_path" "$sdist_path"; do
  artifact_name="$(basename "$artifact")"
  demo_root="${RUNNER_TEMP}/releaseforge-${artifact_name}-demo"
  uv run --isolated --no-project --python 3.11 --with "$artifact" \
    releaseforge demo "$demo_root"
  test -f "$demo_root/START_HERE.md"
  test -f "$demo_root/proof-v1/RELEASE_READINESS.html"
done
```

Expected: the wheel and sdist are each installed outside the checkout, their
console command creates only a fresh synthetic demo, and both expected proof
surfaces exist. The filename lookup avoids a hard-coded package version.

- [ ] **Step 4: Review workflow contents locally before relying on GitHub**

Run:

```bash
rg -n "permissions:|contents: read|publish|release|upload|actions/checkout@|actions/setup-python@|astral-sh/setup-uv@|uv sync --locked --extra dev|releaseforge demo" .github/workflows/ci.yml
git diff --check
```

Expected: only the intended read-only actions and commands are present; no
publish/upload/release operation appears.

- [ ] **Step 5: Commit the workflow**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: verify Releaseforge distributions"
```

### Task 3: Make the trust boundary visible and reproduce the CI build locally

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: the checked-in workflow path `.github/workflows/ci.yml`.
- Produces: one clickable GitHub Actions status badge and narrow CI-boundary copy.

- [ ] **Step 1: Add the CI badge under the Releaseforge title**

Insert directly after the title and tagline:

```markdown
[![CI](https://github.com/notgabriels-sys/releaseforge/actions/workflows/ci.yml/badge.svg)](https://github.com/notgabriels-sys/releaseforge/actions/workflows/ci.yml)
```

- [ ] **Step 2: Add an explicit CI boundary after the existing evidence boundary section**

Add this paragraph:

```markdown
The CI workflow verifies the checked-in source, tests, package distributions,
and synthetic demo on its declared Python/OS matrix. It does not inspect real
release material or certify distributor acceptance, rights, approvals, or any
public release state.
```

- [ ] **Step 3: Reproduce the lint, build, and installed-artifact smoke path locally**

Run:

```bash
uv sync --locked --extra dev
uv run --frozen pytest -q
uv run --frozen ruff check src tests
uv run --frozen ruff format --check src tests
TASK_DIST="$(mktemp -d /private/tmp/releaseforge-ci-dist.XXXXXX)"
uv build --no-sources --out-dir "$TASK_DIST"
```

Then run this exact installed-artifact smoke loop:

```bash
set -euo pipefail
TASK_SMOKE="$(mktemp -d /private/tmp/releaseforge-ci-smoke.XXXXXX)"
wheel_path="$(find "$TASK_DIST" -maxdepth 1 -type f -name '*.whl' -print -quit)"
sdist_path="$(find "$TASK_DIST" -maxdepth 1 -type f -name '*.tar.gz' -print -quit)"
test -n "$wheel_path"
test -n "$sdist_path"

for artifact in "$wheel_path" "$sdist_path"; do
  artifact_name="$(basename "$artifact")"
  demo_root="$TASK_SMOKE/${artifact_name}-demo"
  uv run --isolated --no-project --python 3.11 --with "$artifact" \
    releaseforge demo "$demo_root"
  test -f "$demo_root/START_HERE.md"
  test -f "$demo_root/proof-v1/RELEASE_READINESS.html"
done
```

Expected: both distributions run the installed console command and create only
new synthetic-demo directories; no source-release directory is passed to the
command.

- [ ] **Step 4: Commit the documentation and final verification change**

```bash
git add README.md
git commit -m "docs: explain Releaseforge CI boundary"
git status --short --branch
```

### Task 4: Publish a cautious stacked draft PR

**Files:**
- Verify: `uv.lock`, `.github/workflows/ci.yml`, `README.md`, existing tests,
  built wheel, and built sdist.

**Interfaces:**
- Consumes: clean local branch `codex/releaseforge-ci` and base
  `codex/initial-implementation`.
- Produces: a normal pushed branch and a draft PR stacked on Releaseforge PR #1.

- [ ] **Step 1: Check the base branch before publishing**

```bash
git fetch origin --prune
git rev-parse origin/codex/initial-implementation
git rev-list --left-right --count origin/codex/initial-implementation...HEAD
```

Expected: the branch is ahead of the current draft base and does not require a
force push.

- [ ] **Step 2: Push normally and open the draft stack**

```bash
git push --set-upstream origin codex/releaseforge-ci
gh pr create --repo notgabriels-sys/releaseforge \
  --head codex/releaseforge-ci \
  --base codex/initial-implementation \
  --draft \
  --title "ci: verify Releaseforge distributions"
```

The PR body must state the stacked base, the test matrix, wheel/sdist synthetic
demo verification, and the absence of publishing or real-release actions.

- [ ] **Step 3: Confirm the literal remote state**

```bash
gh pr view --repo notgabriels-sys/releaseforge codex/releaseforge-ci \
  --json number,url,state,isDraft,baseRefName,headRefName,mergeStateStatus,statusCheckRollup
```

Expected: open, draft, base `codex/initial-implementation`, and no merge/ready
action taken by this plan.
