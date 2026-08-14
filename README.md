# Releaseforge

**Local release proof before distributor upload.**

Releaseforge turns one local release folder into a clear, portable decision
record. It reads the files you declare, verifies what can be measured directly,
keeps supplied information visibly separate from file facts, and writes an
offline packet for a label, artist, engineer, designer, or release manager to
review together.

It is intentionally not a distributor, cloud catalogue, rights authority, or
automatic platform-compliance tool.

## What it does now

- reads a strict `release.toml` beside your local assets;
- records SHA-256, byte size, cover geometry/mode, and PCM WAV header facts;
- applies the workflow requirements **you choose** for that handoff;
- marks configured failures as blockers and incomplete declarations as needing
  evidence;
- builds `RELEASE_PROOF.md`, `RELEASE_PROOF.json`, and a self-contained
  `RELEASE_READINESS.html` document;
- assigns each packet a deterministic content ID and compares two packets by
  verified facts, declarations, workflow profile, decision, and findings;
- never uploads, copies, renames, deletes, or modifies a declared source asset.

The generated packet contains relative paths and local file facts, never
machine-specific source paths or source media files. Its `proof_id` is a
deterministic content identifier, not a cryptographic signature, proof of
authorship, or approval.

## The evidence boundary

Releaseforge uses four distinct categories:

| Category | Meaning |
| --- | --- |
| `verified_file_fact` | Read directly from local bytes or a container header. |
| `declared` | Supplied in `release.toml`; presence and consistency can be checked, not truth. |
| `needs_evidence` | A declaration remains pending/unknown and needs human review outside the tool. |
| `blocker` | A configured workflow condition is not met. |

A `PROFILE CHECKED` outcome means only that the local files and declarations
meet the selected workflow profile. It **does not establish** ownership,
licensing, approvals, distributor acceptance, platform compliance, or public
release readiness.

## Install

Requires Python 3.11+.

```bash
git clone https://github.com/notgabriels-sys/releaseforge.git
cd releaseforge
python3 -m pip install .
```

## Use

Create a commented declaration in a new or existing release folder:

```bash
releaseforge init /path/to/release
```

Edit `/path/to/release/release.toml`. The supplied workflow values are starter
values only; confirm the actual requirements with the distributor, pressing
plant, or delivery destination you will use.

Read the release without writing anything:

```bash
releaseforge check /path/to/release
```

Create a proof packet in a **new directory outside** the source release folder:

```bash
releaseforge build /path/to/release --output /path/to/release-proof
```

`check` and `build` return `0` when there are no configured blockers, `1` when
there is at least one blocker, and `2` for invalid declarations, unreadable
assets, or unsafe/output errors. A `needs evidence` item remains visible even
when it is not a configured blocker.

Compare two existing proof packets after a revision or handoff. Each argument
may be a packet directory or a direct `RELEASE_PROOF.json` path:

```bash
releaseforge compare /path/to/proof-before /path/to/proof-after
releaseforge compare /path/to/proof-before /path/to/proof-after --json
```

`compare` reads only the packet JSON, validates the packet content ID and
source-path boundary, then reports captured changes. It returns `0` for
equivalent captured content, `1` when there are differences, and `2` for an
invalid packet or a mismatching content ID. It does not read source media,
choose which packet is correct, or establish approval.

## `release.toml`

```toml
[release]
title = "Release Title"
artist = "Primary Artist"
catalogue_number = "LABEL-001"
planned_release_date = "2026-09-01"

[requirements]
minimum_cover_pixels = 3000
require_square_cover = true
allowed_audio_extensions = [".wav", ".flac", ".aiff"]

[assets]
cover = "artwork/final-cover.jpg"

[declarations]
rights_review = "declared_pending"
metadata_review = "declared_pending"
artwork_approval = "declared_pending"

[[tracks]]
number = 1
title = "Track Title"
file = "audio/01-track-title.wav"
declared_master_status = "declared_pending"
```

All paths must be relative to the directory containing `release.toml`, remain
inside it after resolution, and name regular files. The parser rejects unknown
fields, duplicate paths, non-contiguous track numbers, and unsafe paths.

## Why this is an open core

The product direction is an evidence-first release layer that can sit before
any distributor. The open core proves the local workflow first. If a real pilot
shows that the packet prevents omissions or makes client handoffs materially
clearer, future paid work can focus on team approvals, maintained delivery
profiles, branded client packets, and retained history—without making raw
source-media upload a prerequisite.

That is a product hypothesis, not a claim that those services are available
today.

## Development

```bash
python3 -m pip install -e '.[dev]'
python3 -m pytest -q
python3 -m ruff check src tests
python3 -m ruff format --check src tests
python3 -m build --no-isolation
```

## License

MIT. See [LICENSE](LICENSE).
