# Releaseforge CI and installed-artifact verification — design

**Date:** 2026-08-15
**Status:** Approved through Gabriel's standing instruction to choose useful work and keep building, with the existing Releaseforge draft as the base.

## Problem

Releaseforge already has a substantial local workflow: strict release declarations,
portable proof packets, offline HTML, comparison, companion-handoff reconciliation,
and a synthetic demo. The branch has a small Linux-only source-tree CI check, but
no committed dependency lock, pinned Actions, macOS coverage, or installed-artifact
smoke test. A contributor or evaluator therefore cannot see whether the declared
Python support and built command work reliably outside a developer checkout.

For a local-first tool used before a real delivery handoff, that reliability gap is
more important than adding another feature. Source-tree tests alone do not prove
that the wheel or source distribution exposes the `releaseforge` command with its
Pillow dependency or that the synthetic demo still works after installation.

## Decision

Enhance the existing CI on a child branch of `codex/initial-implementation`:

1. Commit a `uv.lock` generated from the existing project declaration, including
   the existing `dev` extra.
2. Add `.github/workflows/ci.yml` with least-privilege read-only permissions,
   pinned actions, concurrency cancellation, and no release/publish steps.
3. Run the test suite on Python 3.11 and 3.13 on Ubuntu, plus Python 3.13 on
   macOS. This covers the minimum supported interpreter, a current interpreter,
   and the principal local platform without making a speculative Windows promise.
4. Preserve the existing compile check and run lint, formatting, source-
   distribution build, wheel build, and installed-artifact smoke checks on
   Ubuntu 3.11.
5. Add a small README CI badge and a precise note that CI verifies the local
   tool only; it cannot certify distributor acceptance, rights, approvals, or a
   real release.

## Workflow design

### Dependency environment

Every job installs the exact lockfile environment with:

```text
uv sync --locked --extra dev
```

The project remains standard Python packaging. `uv` is used only to make the CI
environment repeatable; no new runtime dependency is introduced and the existing
`releaseforge` console-script entry point remains unchanged.

### Test matrix

The `test` job uses this three-entry matrix:

| Runner | Python | Reason |
| --- | --- | --- |
| Ubuntu | 3.11 | Lowest supported interpreter. |
| Ubuntu | 3.13 | Current supported interpreter coverage. |
| macOS | 3.13 | Validates the main local platform path. |

Each entry runs `uv run --frozen pytest -q`. The suite creates only synthetic
temporary media used by its fixtures; it does not inspect repository user assets
or make external product actions.

### Lint, build, and installed-artifact smoke

The separate Ubuntu 3.11 job runs:

1. `ruff check src tests` and `ruff format --check src tests`.
2. `uv build --no-sources` to produce an sdist and wheel.
3. An isolated wheel install that runs `releaseforge demo` into an empty
   temporary directory and checks for `START_HERE.md` and the generated proof
   HTML.
4. An isolated source-distribution install that runs `releaseforge --help` and
   the same synthetic demo contract.

The smoke commands resolve the generated distribution filenames instead of
hard-coding `0.1.0`, so a future version bump cannot make CI test the wrong
artifact. The synthetic demo is deliberately the smoke surface because it uses
the installed command and Pillow dependency without touching a real release
folder.

## Security and operating boundaries

- GitHub Actions permissions are limited to `contents: read`.
- Actions are pinned to full commit SHAs, matching the existing sampleproof CI
  convention in this GitHub organization.
- The workflow triggers on pull requests and pushes to `main`, avoiding a
  duplicate branch-push run when a pull request is opened. It does not publish
  a distribution, create a release, upload project assets, alter issues, or
  access release/distributor/client systems.
- Dependency retrieval during CI is ordinary package installation. It is not a
  workflow for raw music, artwork, proof packet, customer, or credential data.
- The README badge reports workflow status, not delivery compliance or a
  product-security certification.

## Acceptance criteria

1. `uv.lock` is committed and `uv sync --locked --extra dev` succeeds locally.
2. The workflow syntax has a reviewable, least-privilege shape with the stated
   matrix and pinned actions.
3. Local verification passes: 64 existing tests, Ruff lint/format, distribution
   build, and wheel/sdist synthetic-demo smoke checks.
4. README wording accurately frames the CI boundary.
5. The final PR is draft, stacked on Releaseforge PR #1, and does not merge,
   publish, or make revenue/adoption claims.
