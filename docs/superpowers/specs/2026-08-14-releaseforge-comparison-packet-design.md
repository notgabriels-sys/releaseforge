# Releaseforge Portable Comparison Packet Design

## Goal

Let a nontechnical reviewer inspect a captured release revision without running
Python or being given a source release folder.

## Command contract

```text
releaseforge compare BEFORE AFTER
releaseforge compare BEFORE AFTER --json
releaseforge compare BEFORE AFTER --output CHANGE_DIR
```

The first two forms remain read-only. `--output` is an explicit write mode that
creates a new comparison packet only when `CHANGE_DIR` does not already exist.
It must sit outside both input proof packet directories, preserving the two
input captures as immutable evidence.

## Output contract

`--output` writes exactly these files:

- `RELEASE_COMPARISON.md` — portable human review record;
- `RELEASE_COMPARISON.json` — deterministic machine-readable change record;
- `RELEASE_COMPARISON.html` — self-contained offline review surface.

The JSON model includes `comparison_id`, a deterministic identifier derived
from the comparison content excluding its own ID. It is a content identifier,
not a signature, approval, authorship claim, or proof of which packet is
correct.

## Evidence and privacy boundary

- Each record names the before/after proof IDs and lists captured differences
  by existing evidence category.
- It does not read source media, copy input packets, modify input packets, or
  infer why a change happened.
- The output never includes the input paths or an absolute source path.
- All HTML-visible values are escaped and the HTML has no external assets or
  network JavaScript.
- An equal comparison may still be written intentionally; its exit status stays
  `0`. A changed comparison still exits `1` after writing the packet.

## Acceptance criteria

- Default `compare` does not create files.
- An explicit output creates all three files in a new, protected directory.
- Existing output and output inside either input packet directory are rejected
  without changing either input packet.
- Markdown, JSON, and HTML contain the stable comparison ID, no machine path,
  and no unescaped declared text.
- CLI status remains `0` for equal captures, `1` for captured changes, and `2`
  for invalid input or an unsafe output request.
