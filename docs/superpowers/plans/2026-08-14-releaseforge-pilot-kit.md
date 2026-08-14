# Releaseforge Pilot Kit Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a privacy-minimal, self-serve pilot protocol and feedback route
without sending outreach or collecting release material.

**Architecture:** A public Markdown protocol gives the exact local workflow and
data boundary. A Markdown GitHub issue template captures only broad outcomes.
The README links to the protocol; no application code, accounts, telemetry, or
external services are added.

## Task 1: Define the privacy and value boundary

- [x] State the concrete product question and the rule against inventing a paid
  layer before real evidence.
- [x] List sensitive artifacts that participants must not share.
- [x] Specify only broad, qualitative feedback fields.

## Task 2: Publish the self-serve pilot route

- [x] Add the pilot protocol with a real local `check → build → compare` flow.
- [x] Add a GitHub issue template that repeats the privacy warning and asks for
  role, outcome, time/friction, repeat-use intent, and optional quote consent.
- [x] Link the protocol from the public README.

## Task 3: Verify and publish

- [x] Read the protocol and issue template back for prohibited upload requests,
  accidental delivery claims, and valid Markdown front matter.
- [x] Run the established code/package checks to ensure documentation changes
  do not disturb the product.
- [ ] Commit, push, and update the existing draft PR description.
