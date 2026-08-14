# Releaseforge Coverforge companion handoff design

## Purpose

Releaseforge already turns a declared local release folder into a portable proof
packet and can combine that packet with selected audio and metadata companion
captures. Coverforge now has a version-1 portable manifest for a visual delivery
build. This feature connects those two evidence surfaces without importing either
tool as a library or reading source media again.

The useful question is deliberately narrow:

> Does the visual source captured by a selected Coverforge manifest align with
> the cover bytes and basic image facts captured by this Releaseforge proof, and
> did the selected visual build record any unproduced or over-cap outputs?

The answer is a local review fact, not an approval, rights, delivery, or
platform-compliance claim.

## Scope

Releaseforge gains one optional `--coverforge PATH` argument on the existing
`handoff` command. `PATH` must name a direct Coverforge `manifest.json` file.
At least one of `--mastergate`, `--releaseledger`, and `--coverforge` remains
required.

The feature:

- accepts only the documented Coverforge portable version-1 JSON shape;
- validates the manifest's deterministic `capture_id` against its canonical JSON
  payload;
- retains only the fields needed for reconciliation and the local manifest
  SHA-256, never the Coverforge slug, output filename, source path, output
  directory, or source media;
- compares the captured Coverforge source SHA-256, byte count, dimensions, and
  mode to the Releaseforge proof packet's captured `cover` asset;
- records the count of captured outputs and treats captured skipped targets or
  outputs marked `over_size_cap` as `needs_evidence` items;
- writes those limited facts into the existing Markdown, JSON, and offline HTML
  handoff packet; and
- protects the Coverforge manifest parent directory as an input tree, so the
  handoff output cannot be written inside it.

The feature does not:

- open, hash, copy, rename, upload, or change artwork or delivery files;
- install or import Coverforge;
- verify that the manifest was produced by a particular binary, person, or
  version of Coverforge;
- validate whether a Coverforge target still matches a live platform policy;
- compare a Releaseforge cover to a rendered delivery output, because the
  Releaseforge proof records the declared cover source, not every delivery
  derivative; or
- establish artwork ownership, licensing, approval, distributor acceptance, or
  release readiness.

## Input contract

`load_coverforge_manifest(path)` will be a strict local parser in
`releaseforge.handoff`.

It reads UTF-8 JSON and its raw SHA-256 once. The root must contain exactly:

```text
schema_version, generated_by, boundary, slug, source, outputs, skipped,
findings, capture_id
```

Required version and provenance-adjacent checks:

- `schema_version` is integer `1`;
- `generated_by` is exactly `coverforge`;
- `capture_id` is `cfp_` plus the first 20 lowercase hexadecimal characters of
  SHA-256 over the canonical root object excluding `capture_id`, using Coverforge
  v1's UTF-8, `ensure_ascii=False`, sorted-key, compact JSON form;
- `slug` is a nonblank, path-free value but is not retained;
- `source` has exactly `sha256`, `bytes`, `dimensions`, `mode`, and `format`;
- every `outputs` item has exactly Coverforge v1's output keys and a safe bare
  filename, but the filename and human display name are not retained;
- `skipped` and `findings` accept only the current documented item shapes, with
  their reason/message text validated but not retained; and
- unknown, missing, path-bearing, malformed, non-finite, duplicate-target, or
  capture-ID-mismatched values fail the command with exit status `2` before any
  output directory is made.

The resulting immutable model contains only:

- raw manifest SHA-256 and validated capture ID;
- source SHA-256, byte count, integer width/height, image mode, and format;
- each output's safe target key, dimensions, format, byte count, SHA-256, and
  `over_size_cap` flag;
- skipped target keys; and
- the preflight-finding count.

This is intentionally stricter than accepting arbitrary JSON from another
tool. It makes the supported v1 contract explicit and prevents a manifest
recipient from smuggling path-bearing or unrecognized data into a Releaseforge
handoff packet.

## Reconciliation

`Handoff` gains optional `coverforge` and `coverforge_linkage` fields.

When a Coverforge capture is supplied, Releaseforge obtains the validated
`cover` asset from the selected proof packet. It compares these facts:

| Coverforge source fact | Releaseforge proof fact | Result |
| --- | --- | --- |
| SHA-256 | cover SHA-256 | identical source bytes when equal |
| byte count | cover byte size | captured size alignment |
| width × height | cover width × height | captured geometry alignment |
| image mode | cover image mode | captured mode alignment |

Each mismatch creates one `needs_evidence` finding with a stable
`coverforge_*` code. If all four source facts match, the source linkage is
`aligned`.

Each target recorded in `skipped` creates a `needs_evidence` finding. Each
captured output whose `over_size_cap` flag is true also creates one. Those
findings say only that the selected capture recorded a missing or over-cap
visual output and asks the reviewer to inspect the intended handoff; they do
not call any delivery invalid or claim a platform rejected it.

The Coverforge linkage state is `aligned` only when all source facts align and
the capture records neither skipped targets nor over-cap outputs. Otherwise it
is `needs_evidence`.

## Output contract

The existing `RELEASE_HANDOFF.json` gets a top-level `coverforge` member beside
`mastergate` and `releaseledger`:

```json
{
  "manifest_sha256": "...",
  "capture_id": "cfp_...",
  "captured_output_count": 2,
  "captured_preflight_finding_count": 1,
  "linkage": {
    "state": "aligned",
    "matching_source_fields": ["sha256", "byte_size", "dimensions", "mode"],
    "mismatched_source_fields": [],
    "skipped_target_keys": [],
    "over_size_cap_target_keys": []
  }
}
```

The exact field names are deterministic. `handoff_id` continues to be computed
over canonical JSON excluding itself, so a Coverforge capture changes the ID.

Markdown and offline HTML add one clearly labelled
“Coverforge-compatible v1 manifest capture” row/section. Values are rendered
through the existing Markdown and HTML escaping helpers. Neither format writes
or reveals the Coverforge manifest path, slug, output filenames, source
filenames, media bytes, or machine paths.

The existing boundary statement will name Coverforge alongside the existing
companion capture types and retain its explicit non-attestation wording.

## CLI and output safety

The parser adds:

```text
--coverforge direct Coverforge-compatible version-1 manifest.json path
```

`_handoff()` loads the existing Releaseforge proof first, loads any selected
companions, and adds each selected manifest parent to `protected_roots`. The
new handoff directory must still be new and outside every proof or companion
input tree. Exit statuses remain:

- `0` for aligned captured relationships;
- `1` for a written packet with one or more `needs_evidence` discrepancies;
- `2` for invalid input or unsafe output location.

## Tests and acceptance

The test suite will add coverage for:

1. a valid Coverforge v1 manifest retaining only safe facts and its raw
   manifest SHA-256;
2. rejection of an unknown root field, a path-bearing output filename, and a
   capture-ID mismatch;
3. an aligned proof/manifest source relationship with a deterministic
   path-free handoff payload;
4. source mismatch, skipped-target, and over-cap-output findings and exit
   status `1`;
5. CLI use with `--coverforge` and protection against output inside the
   manifest parent directory;
6. Markdown/HTML escaping and absence of synthetic temp paths and Coverforge
   source/output names; and
7. the existing full test, lint, formatting, build, and installed-wheel smoke
   paths.

## Product boundary

This makes the public repositories more coherent: Coverforge supplies visual
delivery evidence and Releaseforge supplies the cross-domain handoff surface.
It is useful to a solo artist, label, engineer, designer, or release manager
without requiring a hosted service. It remains an open-core proof of a real
workflow, not a claim that paid collaboration, approval, profile-maintenance,
or history services already exist.
