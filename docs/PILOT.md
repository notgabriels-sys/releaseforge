# Releaseforge pilot

Releaseforge is useful only if it makes a real pre-upload handoff clearer or
helps someone catch an actual omission. This short pilot is designed to test
that claim without collecting anyone’s music, artwork, delivery credentials, or
release metadata.

## Who this is for

Try this if you are one of the people responsible for an upcoming handoff:

- an independent artist managing a release folder;
- a label or release manager;
- a mastering engineer or designer preparing delivery material.

You need a folder you are allowed to inspect and around 15–30 minutes. The
pilot does not require you to submit, publish, or change any source asset.

## Safety and privacy first

Do **not** attach or paste any of the following into a GitHub issue, public
discussion, chat, or email:

- audio, artwork, project files, screenshots, or cloud links;
- `RELEASE_PROOF.*` packets, SHA-256 hashes, release titles, catalogue numbers,
  planned dates, artist names, or distributor destinations;
- contracts, rights information, credits, identifiers, login details, or
  payment information.

The feedback route asks only for broad outcomes. You can stop at any point and
you should use a copy of the folder if that is more comfortable. A
`PROFILE CHECKED` result is never permission to publish or proof of rights,
approval, platform acceptance, or legal compliance.

## Pilot workflow

1. Optional: run `releaseforge demo ./releaseforge-demo` first to see the
   synthetic workflow and comparison behavior.
2. In a local release folder you are allowed to inspect, run
   `releaseforge init RELEASE_DIR` only if no `release.toml` exists. Review all
   starter values against the real delivery destination; do not treat them as
   platform requirements.
3. Run `releaseforge check RELEASE_DIR`. Note privately whether it surfaced an
   actual missing, mismatched, or unclear item.
4. Build a first packet outside the release folder:

   ```bash
   releaseforge build RELEASE_DIR --output PROOF_V1
   ```

5. Make one legitimate local revision that you would make anyway, then build a
   second packet to a new directory:

   ```bash
   releaseforge build RELEASE_DIR --output PROOF_V2
   releaseforge compare PROOF_V1 PROOF_V2
   ```

   A comparison exit status of `1` means the packets differ; it is an expected
   result for a changed handoff, not an application failure.
6. Use the [pilot feedback template](../.github/ISSUE_TEMPLATE/pilot-feedback.md)
   to report only the broad outcome. A pilot with no detected omission is still
   valuable feedback.

## What to report

The useful signals are deliberately small:

- your general workflow role;
- whether you completed the flow;
- whether it surfaced a real omission or clarified a handoff;
- approximate time spent;
- the most confusing part, if any;
- whether you would use it again for a similar handoff.

Please describe examples generically, such as “an artwork dimension did not
match our declared workflow profile,” rather than naming a release or sharing a
file.

## Decision rule for the project

This pilot is not a sales funnel. The current product decision is to earn
evidence before adding accounts, uploads, billing, or a hosted team product.

The maintainer should continue only if real pilots show that the packet catches
an omission, makes a handoff materially clearer, or both. If it does neither,
the next step is to improve the local workflow or stop the direction—not invent
a paid layer around unproven value.
