# Releaseforge companion handoff implementation plan

> Historical implementation plan, revised to describe the supported companion surface.

**Goal:** Build a local-only Releaseforge `handoff` command that reconciles a
validated Releaseforge proof packet with a Releaseledger-compatible manifest
capture and writes a portable, evidence-bounded dossier.

**Architecture:** Add one focused `releaseforge.handoff` module with immutable
companion models, a strict version-1 parser, deterministic payload construction,
escaped renderers, and a new-directory-only writer. Extend the argparse CLI with
a required-output `handoff` subcommand. The module imports Releaseforge's
existing packet validator but does not import Releaseledger as a dependency.

## Boundaries

- Accept a proof packet directory or direct `RELEASE_PROOF.json` path.
- Accept a direct Releaseledger `manifest.json` path through `--releaseledger`.
- Strictly accept only the documented Releaseledger version-1 schema; reject
  malformed or unknown fields and unsupported versions before output.
- Retain only portable, schema-validated values and a SHA-256 fingerprint of
  the supplied manifest bytes.
- Treat schema recognition and captured hashes as local evidence, not producer
  authentication, ownership proof, approval, or distributor acceptance.
- Write only to a new output directory outside every input packet tree.
- Make no network request and modify no source media or existing packet.

## Implementation tasks

### 1. Parse the Releaseledger capture

- Add frozen models for the release and numbered tracks.
- Validate the exact root, release, source, and track fields.
- Require contiguous track numbers beginning at one.
- Exclude source paths and other nonportable data from the returned model.
- Cover invalid JSON, unsupported versions, unknown fields, invalid hashes,
  unsafe filenames, and malformed values with normal `HandoffError` failures.

### 2. Reconcile declared metadata

- Compare artist, title, and catalogue number with the validated Releaseforge
  proof packet.
- Compare release date only when the Releaseledger capture declares one.
- Compare numbered-track coverage without claiming track-title verification,
  because the Releaseforge proof schema does not retain track titles.
- Emit structured `needs_evidence` findings for mismatches or missing coverage.
- Keep matching values visibly categorized as declarations.

### 3. Render and write the handoff packet

- Build one deterministic JSON payload with `schema_version`, `handoff_id`, the
  Releaseforge proof ID, the companion manifest fingerprint, alignment data,
  findings, and the evidence boundary.
- Derive `handoff_id` from canonical JSON excluding the ID itself.
- Render escaped Markdown and a self-contained offline HTML view from the same
  payload.
- Write exactly `RELEASE_HANDOFF.md`, `RELEASE_HANDOFF.json`, and
  `RELEASE_HANDOFF.html` into a new directory.
- Reject output collisions and paths nested beneath an input packet.

### 4. Expose the CLI

```bash
releaseforge handoff PROOF_PACKET \
  --releaseledger RELEASELEDGER_MANIFEST \
  --output HANDOFF_DIRECTORY
```

- Exit `0` when captured declarations align.
- Exit `1` after writing a dossier with review findings.
- Exit `2` for invalid input, unsafe output, or write failure.
- Print only bounded status and output-directory information.

### 5. Verify

- Unit-test strict parsing and path-free retained data.
- Unit-test aligned and mismatched declarations.
- Unit-test deterministic JSON plus Markdown and HTML escaping.
- Unit-test output collision and protected-tree rejection.
- Exercise the CLI success, review-finding, and input-error exit paths.
- Run the full test suite, lint, build, and `git diff --check` before commit.

No account, upload, analytics, credential, payment, hosted service, or retained
history feature is part of this plan.
