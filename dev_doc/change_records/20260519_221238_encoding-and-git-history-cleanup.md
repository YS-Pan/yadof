# 2026-05-19 22:12 - Encoding And Git History Cleanup

## Context
- Some reference documents contain Chinese text and can display as mojibake when read
  through a Windows default code page instead of UTF-8.
- The Git object database had grown because historical commits contained generated
  optimization results.

## Change
- Added UTF-8 reading and writing guidance to `dev_doc/README.md`.
- Rewrote `master` history to remove generated result blobs from:
  - `project/recorded_data/rawData.npz`
  - `project/recorded_data/indMeta.jsonl`
  - `project/recorded_data/indMeta.jsonl.lock`
  - `project/recorded_data/optMeta/`
  - `project/tools/time_20260517_074041.png`
- Expired reflogs and ran Git garbage collection so the removed objects no longer
  occupy `.git/`.

## Rationale
- Explicit UTF-8 handling prevents AI agents and maintainers from editing documents
  based on garbled terminal output.
- Generated calculation results should stay out of Git history; they are runtime
  artifacts, not source documents.

## Impact
- `.git` shrank from about 140 MB of loose objects to a small packed repository.
- Commit hashes on `master` changed because history was rewritten.
- Existing uncommitted working-tree changes were preserved.

## Follow-Up
- Keep generated result paths covered by `.gitignore`.
- If a remote copy already has the old history, synchronize it carefully because this
  local branch no longer shares the same commit hashes.
