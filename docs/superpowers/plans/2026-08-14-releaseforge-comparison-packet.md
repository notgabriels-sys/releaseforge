# Releaseforge Portable Comparison Packet Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow explicit creation of an offline comparison packet while keeping
plain packet comparison read-only.

**Architecture:** Extend the existing immutable comparison model with a
deterministic comparison ID and three renderers. A packet writer owns
non-overwrite and protected-input-directory checks. The CLI routes an optional
`--output` argument without changing its existing comparison semantics or exit
codes.

**Tech Stack:** Python 3.11+, standard-library `hashlib`, `json`, `html`, and
`pathlib`, existing Releaseforge comparison data, pytest, Ruff.

## Task 1: Specify portable comparison output in tests

- [x] Add failing comparison-rendering tests for a stable comparison ID,
  Markdown/JSON/HTML output, HTML escaping, and source-path-free payloads.
- [x] Add failing writer tests for new output, collision refusal, and
  input-packet-directory protection.
- [x] Add a failing CLI test for `compare BEFORE AFTER --output CHANGE_DIR`
  with the existing changed-comparison exit code.

## Task 2: Implement the comparison packet

- [x] Add a deterministic `comparison_id` and portable Markdown/HTML renderers
  from the existing semantic comparison model.
- [x] Add a non-overwriting writer that creates exactly the three documented
  comparison files and refuses protected input packet trees.
- [x] Add `--output` to the CLI while leaving no-output comparison read-only.
- [x] Run focused tests and test packet/path safety behavior.

## Task 3: Document, validate, and publish

- [x] Document explicit comparison output and its non-signature boundary in the
  README and MVP design.
- [x] Run full tests, lint, formatting, compile, package build, safety scans,
  and a fresh-wheel output smoke test.
- [x] Commit, push, update the live draft PR description, and verify the remote
  head/status.
