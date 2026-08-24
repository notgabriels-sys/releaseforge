# Releaseforge companion handoff design

## Decision

Releaseforge will gain one local-only `handoff` command. It will create a
portable review dossier from:

- one validated Releaseforge proof packet (required);
- an optional Releaseledger `manifest.json` produced by `releaseledger build`.

At least one companion manifest is required. The feature deliberately does not
read audio, artwork, source TOML, or any live service. It does not import
Sleeveproof or Coverforge in this first version: Sleeveproof currently records
an absolute `input_dir`, and Coverforge has no compatible portable manifest.

## Product boundary

The point is a single human-review surface for a release handoff already being
checked with local tools. It must never turn independent local captures into an
approval, a signature, a proof of ownership, a distributor-compliance claim, or
a claim that each capture came from the same folder at the same time.

The handoff can make only these limited statements:

- the Releaseforge proof packet passed its existing content-ID validation;
- the supplied companion JSON matched a known, strict version-1 schema and its
  bytes were fingerprinted in the handoff packet;
- shared fields in Releaseforge and Releaseledger declarations either match or
  do not match.

All other facts remain inside their original evidence boundary. A matching hash
is a match between two recorded values; it is not a fresh media read, a
signature, or a release verdict.

## Command and outputs

```bash
releaseforge handoff PROOF_PACKET \
  --releaseledger RELEASELEDGER_MANIFEST \
  --output HANDOFF_DIRECTORY
```

`PROOF_PACKET` accepts the same directory-or-`RELEASE_PROOF.json` input as
`compare`. `--releaseledger` is optional at the parser level, but must be
supplied when no other supported companion is selected. Each companion option accepts a direct
`manifest.json` path only. The command returns `0` when all available
cross-checks align, `1` when it creates a dossier containing discrepancies or
pending evidence, and `2` for invalid/missing manifests or unsafe output.

`--output` is required. It must name a new directory outside the Releaseforge
proof-packet directory and outside each companion manifest's parent directory.
The command creates exactly:

- `RELEASE_HANDOFF.md`
- `RELEASE_HANDOFF.json`
- `RELEASE_HANDOFF.html`

The packet will retain proof/manifest content IDs and computed hashes, but no
absolute input paths, input-directory names, source filenames, source media, or
source TOML paths. Output values are escaped in Markdown and HTML.

## Data model and reconciliation

The new `releaseforge.handoff` module owns strict parsing, reconciliation,
rendering, and writes. It will have a focused immutable model for the external
schema rather than importing that package as a runtime dependency.

The parser accepts only documented version-1 schema-compatible manifest captures:

- Releaseledger must have the exact expected release, tracks, source, and files
  structure from its build output.
- Unknown fields, malformed types, unsupported schema versions, unsafe
  filenames, or direct/relative path fields outside the known portable shapes
  cause a normal `HandoffError`, not partial output.

Schema recognition and a SHA-256 identify only the local manifest bytes
supplied to the command. They do not authenticate the producing program or
prove an upstream build ran.

The dossier evaluates one declared-metadata link:

1. **Declared Releaseledger alignment.** It compares shared declared fields
   (`artist`, `title`, and `catalogue_number`), compares dates only when
   Releaseledger declares one, and compares only numbered-track coverage.
   Releaseforge proof-packet version 1 does not capture track titles, so the
   handoff must not claim a title comparison. Differences become
   `needs_evidence`; matching values remain visibly declared, not independently
   verified.

The JSON root has `schema_version: 2`, a deterministic `handoff_id`, the
validated Releaseforge `proof_id`, hashes of each selected companion manifest,
the limited reconciliation record, and structured findings. The
`handoff_id` hashes canonical JSON excluding itself. The Markdown and HTML are
views of that one payload.

## Failure handling

No source directory or existing packet is modified. The writer refuses an
existing output directory and rejects a nested output before creating files. A
write failure may leave only a newly-created output directory; it never alters
input packets. Invalid JSON, a mismatched Releaseforge proof ID, an unsupported
companion manifest, and nonportable fields exit through the CLI's normal error
path with status `2`.

## Test strategy

Tests use only synthetic JSON and the existing synthetic Releaseforge fixture.
They will prove:

- a known Releaseledger manifest loads without importing the upstream package;
- matching shared declarations produce an aligned
  dossier whose output contains no temporary absolute input path;
- a mismatched shared release declaration creates an explicit `needs_evidence`
  finding and exit status `1`, rather than failing
  silently or asserting external failure;
- unknown fields, invalid release proof IDs, unsafe/nested outputs, and output
  collisions refuse to create or alter an input tree;
- HTML escapes companion-supplied strings and JSON remains deterministic;
- CLI output and exit statuses match the documented contract.

No dependency, account, upload, analytics, network call, credential, or payment
feature is in scope. Adoption evidence from genuine privacy-minimal pilots is
still required before any hosted, account, billing, or retained-history layer is
considered.
