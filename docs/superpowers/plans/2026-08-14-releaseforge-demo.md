# Releaseforge One-Command Demo Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a safe synthetic demo command that proves the normal proof and
comparison workflow without using a real release folder.

**Architecture:** A small `demo.py` module writes two synthetic release folders
to a new user-selected destination, runs the existing parser/inspector/
evaluator/report path for each, and exposes the paths through an immutable
result object. The CLI only routes arguments and prints a concise next step.

**Tech Stack:** Python 3.11+, Pillow, standard-library `wave`, existing
Releaseforge layers, pytest, Ruff.

## Task 1: Define the safety contract in tests

- [x] Add failing module tests for a two-version synthetic demo, its proof
  comparison, packet privacy, and refusal to overwrite an existing destination.
- [x] Add a failing CLI test for `releaseforge demo DESTINATION`.
- [x] Run the focused tests and verify they fail because the command/module is
  not implemented.

## Task 2: Build the synthetic demo workflow

- [x] Add `demo.py` with a new-destination guard, two deterministic synthetic
  release folders, generated media, proof packet generation, and a concise
  start guide.
- [x] Add the `demo` CLI route without changing the semantics of `check`,
  `build`, or `compare`.
- [x] Run focused tests and confirm the comparison distinguishes the changed
  cover as a verified asset fact.

## Task 3: Document and validate public evaluation

- [x] Document the demo command and its synthetic/evidence boundaries in the
  README and MVP design.
- [x] Run the complete test, lint, formatting, compile, package-build, and
  fresh-wheel workflow.
- [ ] Commit, push, and update the existing draft PR description.
