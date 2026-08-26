# 2026-08-26 10:47 - Remove Obsolete Trebuchet Path-Regression Baseline

## Context

- Codex task `修复benchmark进度条并整理输出`
  (`01a0365b-beab-7281-b6b5-c7fbbba824eb`) changed benchmark baselines from
  immutable identities to editable semantic templates with immutable run-local
  snapshots. During that task, the former selected
  `trebuchet-42e80c54ebb5` directory was retained under the semantic name
  `chrono/trebuchet-path-regression`, while the path-safe
  `trebuchet-462d1201a592` replacement became `chrono/trebuchet`.
- The retained template had originally preserved the pre-fix Chrono adapter under
  the old frozen-baseline policy. The current runner, configuration, and tests do
  not select or reference it.
- The user requested an evidence-based comparison and authorized removal if the
  retained baseline was obsolete.

## Change

- Removed the unselected
  `benchmark_automation/baselines/chrono/trebuchet-path-regression` template.
- Updated the baseline guide to describe only the current selected Trebuchet
  template and the general completed-run evidence contract.

## Rationale

- The removed and selected workspaces had identical scientific task, cost,
  optimization, rawData, postprocessing, and visualization files. Their only
  executable difference was the copied `chrono_com.py`: the removed template
  lacked the Windows short-junction launch fix carried by the selected template.
- The path-length behavior has direct package regression coverage in
  `test_windows_long_candidate_scratch_uses_short_launch_alias` and retained real
  PyChrono smoke evidence with approximately 298/311-character scratch/request
  paths. Keeping a complete obsolete task copy added no independent automated
  coverage.
- Run-local baseline snapshots now preserve the exact input identity of completed
  and resumable runs. The source tree no longer needs a superseded baseline solely
  to retain historical evidence.

## Impact

- `benchmark.toml` remains unchanged and continues to select
  `baselines/chrono/trebuchet`.
- The benchmark unit suite passed all 50 tests with a fresh external pytest base.
- The complete `performance` plan remains 18 measured cells and 36,000 attempted
  evaluations, and preflight passed all 13 checks without launching a simulator.
- Installed yadof package code and behavior did not change. The documentation-only
  validation exception applies to this change record, and the current task does
  not require rebuilding the wheel merely to expose it immediately through
  `yadof docs`.

## Follow-Up

No follow-up baseline migration is required. Historical Git commits and immutable
run evidence retain the deleted template's provenance.
