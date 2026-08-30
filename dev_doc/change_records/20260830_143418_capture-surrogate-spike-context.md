# 2026-08-30 14:34 - Capture surrogate spike comparison context

## Context

The user compared surrogate-viewer results from Chrono and SAW. The Chrono arm
stress display contained isolated real peaks and much denser surrogate spike
chatter, while the SAW `s21_db` display was comparatively smooth. The screenshots
and the user's event-discontinuity hypothesis needed to remain discoverable across
future agent sessions without being promoted to a verified mechanism conclusion.

## Change

- Copied the two original PNG attachments into `dev_doc/context/` under descriptive,
  time-named filenames.
- Added `20260830_143418_surrogate-spikes-chrono-vs-saw.md` with image links,
  attachment hashes, visible viewer metadata, direct observations, the user's
  hypothesis, and explicit attribution limits.

## Rationale

The material is cross-session experimental evidence rather than a current system
contract, completed technical decision, or instruction for future work, so the
context tree is its intended home. Semantic filenames make both the contrast and
the individual screenshots discoverable during the required filename-only context
pass.

## Impact

This is a documentation-and-evidence addition only. It changes no package code,
checkpoint, task workspace, model behavior, viewer behavior, user workflow, or
documentation discovery mechanism. No claim is made that discontinuous physical
events caused the surrogate spikes or that a particular surrogate component
produced them.

## Validation

- Preserved the original PNG bytes and recorded their SHA-256 identities.
- Checked the new Markdown image targets, filenames, UTF-8 text, and Git whitespace.
- Applied the documentation-only validation exception; no wheel build, reinstall,
  pytest run, viewer launch, simulator execution, or benchmark was needed.
