# 2026-09-01 15:23 - Close The yadof Benchmark Autonomous Goal

## Context

- The independent benchmark package required users to author its workflow and
  strategy files before it could run. Its safe `cNNNN` cell directories were also
  the only public identity, and the foreground progress parser did not recognize
  the evaluation lines emitted by the installed yadof release.
- A read-only measured complete campaign used population 200 and 50 generations.
  Fifteen cells completed, while the three synthetic-antenna GPSAF/PCA-SVD cells
  continued making progress until their fixed 7200-second timeouts near generation
  34. The closure therefore had to reduce the explicit complete budget without
  weakening timeout behavior or manufacturing algorithm-quality acceptance.
- Cell-level parallelism required measured evidence and a separate safety decision
  because every baseline already has its own simulator-worker layer.

## Change

- Released `yadof-benchmark 0.4.0` with wheel-contained `portable`, `complete`, and
  explicit `blank` presets. No-argument `init` now selects portable; complete must
  be requested explicitly. Preset materialization validates canonical relative
  paths, rejects destination collisions, and records catalog, workflow, and
  strategy SHA-256 provenance.
- Defined complete as three packaged baselines by two canonical strategies by
  seeds 101/102/103, with population 200, generations 25, timeout 7200 seconds,
  `fail_fast=False`, and `cell_concurrency=1`. Added a declared/smoke budget
  profile whose smoke transformation changes only generations to 1.
- Preserved `cNNNN` as the filesystem-safe key while carrying a full baseline,
  strategy, and seed display label through specs, state, lifecycle events,
  terminal output, inspect output, errors, JSON/CSV results, and Markdown reports.
  Duplicate cell identities and display-label collisions now fail planning.
- Recognized installed yadof population/evaluation progress snapshots and inferred
  batch boundaries only from observed resets. TTY output remains live; non-TTY
  output is append-only, has no ANSI control sequences, and emits elapsed-time
  heartbeats even between evaluation-percentage buckets.
- Strengthened timeout cleanup to terminate the complete descendant process tree
  on Windows and the process group on POSIX. A timed-out cell is failed,
  independent cells continue, and the final workspace is non-successful.
- Documented `yadof.optimize.program/v1` as an executable protocol discriminator:
  exact v1 is accepted while unsupported protocol versions are rejected. It is a
  narrow fixed-format exception to incidental release-marker cleanup, not a
  package edition label.

## Rationale

- Portable initialization must produce a runnable, simulator-free integration
  path. Complete is deliberately visible and explicit because its 18-cell measured
  matrix consumes real simulator time and can run for many hours.
- A mechanically derived smoke profile provides structural coverage of the exact
  identities, digests, policies, and population used by complete without silently
  becoming a second scientific workflow.
- Semantic identities belong in evidence and operator surfaces, while short fixed
  keys remain the correct defense against special characters and long filesystem
  paths.
- Faster synthetic scheduling is insufficient to establish real-simulator memory,
  licensing, and nested-worker safety. The serial default therefore remains the
  conservative shipped policy even when users may opt in explicitly.

## Impact And Evidence

- The final built and force-reinstalled benchmark wheel has SHA-256
  `436ADFC49BA1191E6C2B0493A3C33156CAF58056A7CA5400C6C4A2FA68D1B72F` and
  imported from the outer environment's `site-packages`. Its installed suite
  passed 41 tests, including packaged resources, provenance, legacy reads,
  labels, collision rejection, executable protocol discrimination, TTY/non-TTY
  rendering, real progress, timeout descendant cleanup, and
  continue-after-timeout behavior.
- Canonical installed strategy files retained SHA-256
  `8149258DB44B9FE877323E7066677EEBA9FD0AA6B857DA65C4776588DF5F3FB0`
  and `4F5F876226A6076F7EA530DBC65BB927B30A80DF217CFF4A0FF2C7880676876B`,
  matching the read-only measured inputs.
- The default portable smoke completed 2/2 collected and valid cells in 24.131
  seconds without anomalies or timeouts. The complete-derived smoke completed
  18/18 collected and valid cells in 757.059 seconds, also without anomalies,
  timeouts, command failures, report failures, or postprocessor failures.
- A second complete-derived smoke against the final installed candidate completed
  18/18 collected and valid cells in 756.307 seconds. All 72 command records
  returned zero without timeout, all 18 result/report/visualization sets passed
  their structural gates, and no residual process remained.
- Three interleaved repetitions per cell-concurrency setting produced median
  durations of 13.231 seconds at concurrency 1 and 8.128 seconds at concurrency 2,
  a 38.568% synthetic improvement. Parallel peak process-tree memory rose from
  about 0.96 GB to 1.36 GB and process count from 12 to 22. Because PyChrono and
  ngspice safety was not exercised, the package retained concurrency 1.
- Formal complete run 1 reached terminal `completed` status after 20,771.407
  seconds with 18/18 cells collected and valid. All 72 commands returned zero
  without timeout; all cell, pairing, final-hypervolume/AUC, cross-seed aggregate,
  surrogate-training, report, and postprocessor gates passed. No residual run
  process remained after the retained wrapper was closed. The first-run success
  rule therefore suppressed run 2, using one of the two permitted complete runs.
- The final read-only review found that lifecycle output had the semantic label,
  but the active live row did not repeat it or show timeout, simulator-worker,
  running, and queued state. A source-only follow-up now covers emitted execution
  capacity, wide and narrow active identity, multiple active cells,
  timeout/cancellation presentation, and inspect metadata. It remained
  uninstalled until the detached campaign reached a terminal state, so the
  running package was not mutated underneath later cells.
- The first formal heartbeat caught the execution-to-collection boundary in
  `view-cost`: the cell was still working with state `succeeded`, while inspection
  reported no active cell. The final source candidate now treats `succeeded` as
  active during collection and parameterizes the inspect test over both running
  and collection states.
- The same heartbeat exposed noisy transient anomaly reporting for every planned
  cell. Running inspection now suppresses expected incompleteness for planned and
  active cells, while terminal inspection retains complete failure diagnostics.
- Windows timeout cleanup now treats `psutil` access/race errors as a signal to
  use recursive `taskkill /T /F`, kills enumerated descendants before their
  parent, and waits after the second kill. A permission-denial test locks the
  fallback behavior.
- `init --help` now names complete as the explicit long-running preset, matching
  the preset catalog and user documentation.
- A launch-provenance audit found that the original record did not persist a
  canonical pre-launch Git patch digest. A separately hashed addendum records the
  exact spec/runtime/receipt, commands, process, environment, installed wheel,
  post-launch source digest, and this limitation without claiming retroactive
  evidence. The installed wheel and materialized input hashes still bind every
  executable byte used by the formal campaign.
- A separately hashed, explicitly after-launch reconstruction maps all 39
  launch-time modified/untracked files to canonical content using the installed
  runtime and reversed known post-launch-only edits. It improves byte-level
  traceability while remaining clearly distinct from a pre-launch observation or
  Git patch digest.
- Portability review replaced eight drive-letter examples across benchmark and
  synchronized yadof user documentation with relative paths. The corrected scan
  has no machine drive, account, host name, or outer-workspace identity match in
  the changed distributable surfaces.
- The synchronized code-identical `yadof 0.5.0` acceptance wheel imported from
  the outer environment's `site-packages` and exposed the updated benchmark
  contract through `yadof docs`. Its full installed suite passed 450/450 tests;
  the benchmark suite then passed 41/41 again against that wheel. After this
  packaged change record and terminal ledger were frozen, a final doc-only wheel
  was rebuilt/reinstalled and received focused document acceptance; its
  non-self-referential hash is recorded in the task completion transcript.

## Automatic TODO Check

- The fixed `program/v1` token remains because parsing actively distinguishes the
  supported protocol from unsupported versions. The related cleanup TODO now
  records that narrow allow-list explicitly.
- The implementation centralizes preset catalog validation, display-label
  construction, budget derivation, and process-tree cleanup rather than adding
  competing workflow or lifecycle sources of truth.
- No user-created runtime evidence or read-only historical campaign was modified.

## Follow-Up

- Revisit default cell concurrency only with repeated complete-workflow evidence
  that covers simulator licensing, nested workers, memory, and oversubscription.
