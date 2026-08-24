# Releaseforge

**Local release proof before distributor upload.**

[![CI](https://github.com/notgabriels-sys/releaseforge/actions/workflows/ci.yml/badge.svg)](https://github.com/notgabriels-sys/releaseforge/actions/workflows/ci.yml)

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
- optionally writes a separate Markdown, JSON, and offline HTML comparison
  packet for a reviewer, while default comparison remains read-only;
- can reconcile one validated Releaseforge proof packet with selected
  Releaseledger- and/or Coverforge-compatible version-1 manifest
  captures, then write a separate local companion-handoff packet;
- creates an optional two-version synthetic demo that exercises the same local
  proof and comparison path without touching a real release folder;
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

The CI workflow verifies the checked-in source, tests, package distributions,
and synthetic demo on its declared Python/OS matrix. It does not inspect real
release material or certify distributor acceptance, rights, approvals, or any
public release state.

## Install

Requires Python 3.11+.

```bash
git clone https://github.com/notgabriels-sys/releaseforge.git
cd releaseforge
python3 -m pip install .
```

## Use

Try the full workflow safely before pointing it at real media:

```bash
releaseforge demo ./releaseforge-demo
cd ./releaseforge-demo
releaseforge compare proof-v1 proof-v2
```

The demo creates two synthetic release folders, two standard packets, and a
`START_HERE.md` guide. It intentionally reports a changed cover as a verified
asset difference. Its media and declarations are illustrative only, not rights,
approval, or delivery evidence. `demo` refuses an existing destination.

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
releaseforge compare /path/to/proof-before /path/to/proof-after --output /path/to/comparison
```

`compare` reads only the packet JSON, validates the packet content ID and
source-path boundary, then reports captured changes. It returns `0` for
equivalent captured content, `1` when there are differences, and `2` for an
invalid packet or a mismatching content ID. It does not read source media,
choose which packet is correct, or establish approval.

Without `--output`, `compare` creates no files. With `--output`, it creates a
new directory outside both input packet directories containing
`RELEASE_COMPARISON.md`, `RELEASE_COMPARISON.json`, and
`RELEASE_COMPARISON.html`. The comparison record has a deterministic
`comparison_id`; it is a content identifier, not a cryptographic signature,
proof of authorship, approval, or a verdict about which revision is correct.
When `--json` and `--output` are used together, stdout remains valid JSON and
the write confirmation goes to stderr.

## Companion handoff

If a handoff already has a Releaseforge proof packet and one or more compatible
Releaseledger or Coverforge captures, create one separate review
dossier:

```bash
releaseforge handoff /path/to/release-proof \
  --releaseledger /path/to/releaseledger-dossier/manifest.json \
  --coverforge /path/to/coverforge-delivery/manifest.json \
  --output /path/to/release-handoff
```

`--releaseledger` and `--coverforge` are individually optional, but at least one
is required. They accept only the known, portable
version-1 `manifest.json` schema shapes used by the companion tools.
Releaseforge hashes the supplied manifest bytes and validates that shape; this
identifies only the local bytes selected for the handoff, not the source
program or whether an upstream build ran. For Coverforge, it also validates the
manifest's deterministic capture ID. The handoff does not install, import, or
call any companion tool; it reads the existing JSON captures locally.

The output directory must be new and must sit outside the Releaseforge proof
packet directory and every selected companion-manifest directory. It contains:

- `RELEASE_HANDOFF.md`
- `RELEASE_HANDOFF.json`
- `RELEASE_HANDOFF.html`

The handoff checks only limited relationships that are present in the captures:

- shared declared release fields align only when Releaseforge and Releaseledger
  record the same artist, title, catalogue number, and, when supplied by
  Releaseledger, date;
- Coverforge's captured source cover aligns only when its SHA-256, byte size,
  dimensions, and image mode all match the Releaseforge proof cover; selected
  targets that Coverforge recorded as skipped, and outputs it recorded as over
  its configured size cap, remain explicit `needs_evidence` items;
- version-1 Releaseforge proof packets do not include track titles, so the
  handoff compares numbered-track coverage only and never claims title
  alignment.

An exit status of `0` means every selected captured relationship aligned. A
status of `1` means the dossier was written with a `needs_evidence`
discrepancy. A status of `2` means an input manifest, proof packet, or output
location was invalid. None of these outcomes establishes current-file
verification, ownership, approval, rights, external delivery, distributor
acceptance, or release readiness. The generated packet contains no absolute
input paths, source filenames, source media, or source TOML paths. Its
companion-manifest SHA-256 values are capture identifiers, not signatures or
producer authentication.

## Pilot

If you use Releaseforge on a genuine local handoff, follow the
[privacy-minimal pilot protocol](docs/PILOT.md). It asks for broad outcome
feedback only—never source media, proof packets, hashes, release metadata,
rights material, URLs, or credentials—and it makes no claim that a paid service
is available.

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
python3 -m build
```

## License

MIT. See [LICENSE](LICENSE).

---

---

<!-- funnel-footer -->
Part of the Gabriel Tools + Code catalog — [browse all tools, products, repositories, and services](https://gabriel-tools-and-code.notgabriels960914.chatgpt.site/).

Free and open source: [theme-contrast](https://github.com/notgabriels-sys/theme-contrast) (WCAG contrast checking for colour themes) · [htmlshot](https://github.com/notgabriels-sys/htmlshot) (HTML → exact-size PNG/PDF) · [50 dark themes for Claude Code](https://github.com/notgabriels-sys/claude-code-50-dark-themes).

Hologram People soundware and Gabriel audio/product work are linked from the master catalog above.

Mixing and mastering enquiries — [public preview](https://gabriel-mixing-and-mastering-d1dmyt.v2.appdeploy.ai/).
