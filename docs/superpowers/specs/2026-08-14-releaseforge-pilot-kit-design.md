# Releaseforge Pilot Kit Design

## Goal

Turn the product hypothesis into a small, privacy-minimal experiment before
building a hosted or paid layer.

## Product question

For someone responsible for a release handoff, does a local evidence packet:

1. surface a real omission or mismatch; or
2. make the handoff materially clearer?

If neither outcome occurs in real use, the project should improve or stop the
local workflow rather than add billing, accounts, uploads, or collaboration.

## Public artifacts

- `docs/PILOT.md`: a 15–30 minute local trial protocol, safety boundaries, and
  decision rule;
- `.github/ISSUE_TEMPLATE/pilot-feedback.md`: an opt-in, privacy-minimal route
  for broad outcome feedback;
- a small README link so someone evaluating the repository can find the pilot
  without searching implementation notes.

## Data boundary

No uploaded raw assets, hashes, proof packets, release metadata, distribution
destinations, rights information, credentials, contracts, URLs, screenshots, or
payment data are requested. A participant can report a generic outcome, such
as a mismatch between a declared workflow profile and a cover dimension.

## Non-goals

- no outreach, invitations, mailing lists, analytics, tracking, or account
  creation;
- no pilot participant records outside GitHub’s normal issue system;
- no customer, conversion, or income claim;
- no expansion into a paid/hosted product before pilot evidence exists.
