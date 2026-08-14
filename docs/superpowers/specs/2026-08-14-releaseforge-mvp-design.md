# Releaseforge MVP Design

## Decision

Releaseforge is a local-first release-proof workspace for independent labels,
artists, mastering engineers, and release managers. It answers one narrow
question before a release is submitted to a distributor:

> What exactly was reviewed, what is only declared, and what still blocks the
> handoff?

It is deliberately not a distributor, a royalty platform, a cloud catalogue,
or an automatic legal/compliance authority.

## Why this is the first product

The existing repository portfolio already contains useful specialist checks for
artwork, audio, metadata, press assets, and handoff documents. The missing
product layer is a single, portable decision record that keeps those checks
connected to the exact local files that were reviewed.

Commercial hypothesis, not a market claim:

- A free local core can earn trust because it does not require uploads or a
  new catalogue system.
- A future paid layer can offer team approvals, reusable delivery profiles,
  branded client packets, and retained release history.
- The first validation target is not a subscription metric. It is whether a
  small label or delivery engineer can use one generated packet to catch a
  real pre-upload omission or to make a handoff materially clearer.

## Primary user and job

The first user is the person who owns a release folder immediately before a
distributor upload or a client/label handoff. They need a fast answer without
retyping their release into another hosted service.

Releaseforge accepts a folder plus a small `release.toml` declaration. It reads
local assets, evaluates explicit workflow requirements, and creates a proof
packet that another person can review without being given a machine-specific
path.

## MVP user flow

1. `releaseforge init RELEASE_DIR` creates a strict, commented `release.toml`
   only when the file does not already exist.
2. The user records release metadata, relative paths to the cover and tracks,
   and the delivery requirements they have chosen for this handoff.
3. `releaseforge check RELEASE_DIR` reads the plan and assets without writing
   anything. It reports blockers, warnings, verified file facts, and declared
   items that still need evidence.
4. `releaseforge build RELEASE_DIR --output PROOF_DIR` writes a new proof
   directory. It never modifies the release folder and refuses to overwrite an
   existing output directory.
5. The recipient opens `RELEASE_READINESS.html` or `RELEASE_PROOF.md` and can
   see the same deterministic findings, asset hashes, and declared boundaries.

## Input contract

`release.toml` is the source of declared release information. Its paths are
relative to the release directory, must resolve inside that directory, and must
refer to regular files.

The MVP supports:

- release title, primary artist, catalogue number, and planned release date;
- one cover asset;
- one or more ordered track entries;
- a small, explicit requirement profile chosen by the user;
- declaration states for rights review, metadata review, and artwork approval.

The requirement profile is a workflow declaration, not a current statement of
any distributor's policy. The starter template calls this out and exposes the
minimum cover size, square-cover rule, and accepted audio extensions as values
the user must verify against their actual delivery destination.

## Evidence model

Every report item has an evidence category:

| Category | Meaning |
| --- | --- |
| `verified_file_fact` | Read directly from local bytes, such as SHA-256, byte size, image geometry, image mode, or PCM WAV duration. |
| `declared` | Supplied in `release.toml`; Releaseforge checks its presence and consistency but does not establish that it is true. |
| `needs_evidence` | A declaration is pending, unknown, or otherwise requires review outside the tool. |
| `blocker` | A configured workflow requirement is not met, an expected file is absent, or the plan is structurally invalid. |

A green deterministic summary means only that the local files and declarations
meet the configured profile. It never proves ownership, rights clearance,
approval, store acceptance, platform compliance, safety, commercial readiness,
or public release status.

## Output contract

`build` writes exactly these files inside a newly created output directory:

- `RELEASE_PROOF.md` — human-readable decision record and boundary statement;
- `RELEASE_PROOF.json` — machine-readable deterministic report;
- `RELEASE_READINESS.html` — offline, self-contained visual review surface.

Reports include relative asset paths, SHA-256 hashes, byte sizes, image facts,
available WAV facts, requirements, and findings. They omit absolute source
paths. No source file is copied, altered, uploaded, deleted, or renamed.

The HTML report is a document rather than a hosted application: no JavaScript
network requests, no analytics, no embedded credentials, and no external
assets. Its visual hierarchy prioritizes the release decision, blockers,
evidence boundaries, track/asset facts, and next review actions.

## Deliberate non-goals for v0.1

- no audio transcoding, mastering, or DSP loudness claim;
- no image conversion, cropping, or platform-spec promise;
- no data upload, user account, cloud storage, collaboration, billing, or
  analytics;
- no legal/rightsholder/licensing verification;
- no automatic distributor submission or metadata export;
- no import or execution of the sibling tool repositories in this release.

The existing specialist tools remain possible future adapters. V0.1 first
proves that the evidence model and output packet are useful on their own.

## Architecture

The Python package is split into small pure layers:

1. `config.py` validates `release.toml` into immutable domain data.
2. `inspect.py` reads permitted local file facts and hashes.
3. `evaluate.py` applies the user-declared workflow profile and emits findings.
4. `report.py` serializes one report model as Markdown, JSON, and a static
   HTML document.
5. `cli.py` owns `init`, read-only `check`, and non-overwriting `build`.

Pillow provides image facts; the Python standard library handles TOML, WAV,
hashing, paths, JSON, HTML escaping, and reports. The product remains offline
by design.

## Acceptance criteria

- A valid synthetic release with a square cover, a WAV track, complete release
  metadata, and current declarations produces a deterministic passing report.
- Missing files, unsafe paths, duplicate/non-contiguous track numbers,
  undersized/non-square covers, disallowed extensions, incomplete required
  metadata, and pending declarations are visible with correct severity.
- The report distinguishes file facts from declarations and includes the
  explicit boundary statement in all human-facing outputs.
- `check` changes no files; `build` creates a new packet and refuses collision;
  reports contain no absolute source paths.
- Tests cover parser failures, file inspection, evaluation, every output
  format, CLI exit status, source immutability, fresh wheel installation, and
  a targeted no-network/no-subprocess/no-credential scan.

## Product follow-up, after a real pilot

Only after testing this core with actual release-folder workflows should the
project consider:

1. adapters for Coverforge, Mastergate, PressAssetbook, and Releaseledger;
2. version-to-version proof comparison and client approval capture;
3. maintained delivery profiles with dated source links and explicit update
   history;
4. a paid, hosted team layer that preserves the same evidence categories and
   leaves raw source assets under the owner's control.
