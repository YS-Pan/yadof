# 2026-09-02 19:11 - Prepare Yadof 0.5.1 Release

## Context

The author explicitly asked Codex to review today's Codex sessions and yadof
change records, set the package version to 0.5.1, and publish a GitHub Release.
The author also explicitly required the release to state that Codex published it
with the author's authorization.

## Change

- Set the single runtime version source and installed-package version assertion
  to 0.5.1; synchronize current installation examples and the foundation blueprint.
- Correct the root README's stale 0.4.2 version, static init/check dependency
  description, and removed benchmark snapshot/resume workflow. Use relative
  workspace examples and link the existing 0.5 migration guide.
- Keep the detected development environment as historical evidence while making
  its acceptance instruction refer to the current wheel.
- Prepare release notes from the seven 2026-09-02 change records and the related
  Codex sessions. The release includes smoke-history isolation, headless surrogate
  case inspection, authoritative fast/local worker caps, and documentation updates.
- Distinguish the independent yadof-benchmark 0.5.0 changes and earlier formal
  benchmark evidence from the yadof 0.5.1 artifact. Separate perfect-GPSAF research
  is not used to establish a release performance claim.

## Rationale And Scope

The source version was still 0.5.0 after these changes, while GitHub's latest
published non-prerelease was v0.2.0. A new tagged release gives users one named
artifact and a concise account of both the recent fixes and the intervening
package evolution. Existing migration history and independent benchmark version
identities are preserved.

The pre-existing untracked GPSAF paper is a local research reference, unrelated
to the release. Preserve it locally and exclude it from the commit and release
artifacts. No runtime evidence or user workspace is modified.

## Release Authority And Validation

This release is prepared and published by OpenAI Codex on behalf of @YS-Pan,
with @YS-Pan's explicit authorization in the release request dated 2026-09-02.
The GitHub Release must carry that attribution in English and Chinese.

Acceptance uses the repository's wheel build, force-reinstall, import-origin,
full installed-yadof test workflow, and an installed benchmark compatibility
suite. Release artifacts also receive metadata/content checks and SHA-256 hashes;
the final test results and artifact checksums are recorded with the GitHub Release.
This packaging task does not rerun a real simulator or establish new scientific
performance evidence.
