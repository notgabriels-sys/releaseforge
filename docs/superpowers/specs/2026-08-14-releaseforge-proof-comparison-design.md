# Releaseforge Proof Comparison Design

## Decision

Releaseforge v0.1 produces useful static proof packets, but a release handoff
often changes after the first review. The next feature is a local comparison
workflow that makes those changes explicit instead of relying on filenames such
as `final-v4`.

## User job

Given two Releaseforge proof packets, a user needs to answer:

> Did the verified source bytes, the supplied release declaration, the chosen
> workflow profile, or the outstanding review state change?

The result is a comparison record, not an approval decision. It must never
claim that the later packet is correct, licensed, accepted, or ready to publish.

## Scope

1. Every generated `RELEASE_PROOF.json` gains a deterministic `proof_id`.
   It is derived from a canonical JSON representation of the whole packet
   except the `proof_id` field itself. Identical packet content always has the
   same ID; any captured packet-content change produces a different ID.
2. `releaseforge compare BEFORE AFTER` accepts either two packet directories
   or two `RELEASE_PROOF.json` files. It is read-only by default; explicit
   `--output CHANGE_DIR` writes a new comparison packet outside both inputs.
3. It validates JSON shape and checks that each stored proof ID matches the
   packet content before comparing it.
4. It reports a stable list of categorized changes:
   - verified asset additions/removals, byte/hash changes, paths, and measured
     facts;
   - supplied release metadata and workflow-profile changes;
   - supplied declaration-state changes;
   - decision and finding changes.
5. Human output is concise by default; `--json` prints a machine-readable
   comparison. `--output` writes Markdown, JSON, and offline HTML from the
   same model. Exit code `0` means packets are equivalent, `1` means one or
   more captured changes exist, and `2` means input, integrity, or unsafe-output
   failure.

## Non-goals

- no source media is read, copied, or changed during comparison;
- no three-way merge, approval signing, collaboration account, cloud history,
  audit assertion, or legal/rightsholder inference;
- no attempt to declare one packet newer or better based on its filename,
  filesystem timestamp, or path.

## Architecture

- `report.py` gains a canonical-payload helper and embeds the proof ID in each
  generated packet.
- `compare.py` loads and validates local JSON packets, creates immutable
  `Change` and `Comparison` models, and renders stable human/JSON/HTML results.
- `cli.py` gains a read-only-by-default `compare` command with an explicit,
  protected comparison-packet output mode. Existing `init`, `check`, and
  `build` behavior stays unchanged.

## Acceptance criteria

- Repeated packet generation from the same source produces the same proof ID.
- A changed cover byte stream is reported as a verified-asset change.
- A changed supplied declaration is reported as a declaration change, not a
  verified fact.
- Identical packets compare cleanly with exit code 0; changed packets return 1;
  malformed, missing, or integrity-mismatched packets return 2.
- The compare code has no network, subprocess, source-write, or destructive
  capability; tests keep all source asset and packet inputs unchanged.
