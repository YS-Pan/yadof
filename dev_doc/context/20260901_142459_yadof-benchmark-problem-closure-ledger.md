# yadof benchmark problem-closure ledger

## Scope

This ledger tracks the autonomous closure authorized on 2026-09-01. Historical
runtime evidence remains read-only. Product changes belong to `yadof-benchmark`
and the synchronized yadof documentation/contracts.

## Fixed acceptance anchors

- `yadof-benchmark init PATH` selects the packaged `portable` preset by default.
- `complete` is explicit and expands to 18 cells: three packaged baselines, two
  canonical strategies, and seeds 101/102/103.
- Every complete cell uses population 200, generations 25, and timeout 7200 s.
- Formal smoke is mechanically derived from complete and changes only generations
  to 1; population, matrix, identities, digests, policies, and timeout remain fixed.
- Internal directories retain `cNNNN`; all public surfaces also carry the full
  baseline, strategy, and seed label.
- A timed-out cell is failed, its process tree is stopped, independent cells
  continue, and the workspace finishes non-successfully.
- At most two formal complete runs are allowed. A detached formal run is owned by
  a same-task 20-minute heartbeat until terminal evidence is collected.

## Issue ledger

| ID | User-visible issue | Root cause / evidence | Required closure | Status |
| --- | --- | --- | --- | --- |
| B01 | Users had to hand-write `benchmark.py` and strategy files. | The current no-argument initializer emits a commented blank template and no packaged strategy resources. | Package discoverable portable/complete presets and canonical strategies; make portable the no-argument default and blank explicit. | verified |
| B02 | `c0016`-style names are not interpretable. | Short IDs were used as both safe paths and the only lifecycle identity. | Preserve `cNNNN` paths while propagating a semantic label through specs, state, terminal, inspect, errors, reports, and evidence. | verified |
| B03 | `program/v1` appeared to contradict incidental-release-marker cleanup. | `yadof.optimize.program/v1` is a validated protocol discriminator; the cleanup contract explicitly excludes fixed protocol/version fields. | Add an executable behavioral distinction and document the narrow allow-list rationale without a repository token scan. | verified |
| B04 | The measured complete campaign ended 15/18 with three timeouts. | Read-only run `20260831_201545-complete-benchmark-measured` used 50 generations. Cells c0016-c0018 reached only about generation 34 before the fixed 7200 s deadline; logs show continuing evaluation rather than a hang. | Make complete explicitly 25 generations, retain 7200 s timeout, test process-tree cleanup/continuation/final failure, and validate 18/18 formally. | verified; formal run 1 completed 18/18 valid with no timeout |
| B05 | Host resources appeared underused and cell scheduling was serial. | The measured workflow configured `cell_concurrency=1`; simulator worker concurrency is a separate per-baseline setting. | Run at least three same-load A/B repetitions, record medians and safety observations, and change the default only for >=15% safe improvement. | verified; retained serial default |
| B06 | Foreground progress and lifecycle output were hard to follow. | Presentation exposes only the short cell id and treats progress as an evaluation percentage even when no real child snapshot is recognized. | Show global counts, semantic active-cell identity, elapsed/phase/states/timeout; keep TTY live and non-TTY append-only with no ANSI. | verified in the 41-case installed suite and final 18-cell smoke |
| B07 | Active cell progress stayed at 0. | The parser accepts `smoke` or `generation N`; version-matched yadof emits `evaluation (fast) ...`. Historical c0016 has 1,428 command heartbeats and zero `cell-progress` events despite real evaluation logs. | Recognize actual evaluation snapshots, infer only completed batch/generation boundaries, emit truthful structured progress, and test both TTY and non-TTY behavior. | verified |

## Cross-cutting gates

- Preset resources must be wheel-contained, digest-recorded, and independent of
  checkout, account, drive, or historical/temp paths.
- Tests must cover deterministic ordering, collision rejection, special-character
  display labels, long safe paths, and legacy artifact reads.
- Installed-wheel origin, focused/full tests, portable smoke, derived complete
  smoke, reports, and portability are required before a formal complete run.
- Formal success is 18/18 collected and valid with no command, storage,
  postprocessor, report, or timeout error. Algorithm quality is not a pass gate.

## Definition-of-Done gate ledger

| Gate | Required evidence | Current evidence | Status |
| --- | --- | --- | --- |
| D01 problem closure | B01-B07 have traceable root causes and implementation or measured no-change conclusions. | Issue ledger above, synchronized architecture/user docs, tests, A/B record, formal campaign, and final installed smoke. | verified |
| D02 preset entry paths | Three fresh installed-wheel workspaces prove default portable, explicit blank, and explicit 18-cell complete initialization/plan/check behavior. | Pre-formal installed-wheel workspaces passed; final installed catalog/origin checks reconfirmed portable as the sole default, complete as explicit, and blank as explicit. | verified |
| D03 benchmark package | Built wheel, force-reinstall, site-packages origin, and full installed suite. | Final wheel SHA-256 `436ADFC49BA1191E6C2B0493A3C33156CAF58056A7CA5400C6C4A2FA68D1B72F`; imported from outer `.venv` site-packages; 41/41 tests passed both before and after the final yadof reinstall. | verified |
| D04 portable smoke | Fresh default portable workspace is runnable and fully valid. | 2/2 collected and valid in 24.131 s. | verified |
| D05 complete-derived smoke | Fresh explicit complete workspace, same 18-cell matrix/hashes/policies/timeout/population, generations changed only to 1, all valid. | Final installed candidate completed 18/18 collected and valid in 756.307 s; all 72 commands succeeded without timeout and no process remained. | verified |
| D06 concurrency decision | At least three same-load repetitions per setting, >=15% speed threshold plus safety evidence. | Serial median 13.231 s, parallel median 8.128 s, +38.568%; nested simulator safety unproven, so default remains 1. | verified no-change decision |
| D07 formal campaign | At most two fresh complete runs; first successful run suppresses the second; full terminal analysis. | Run 1 in `temp/20260901_151852-formal-complete-run-1` completed 18/18 valid; all 72 commands returned zero without timeout, every metric/pairing/aggregate gate passed, and no residual process remained. | verified; run 2 suppressed by the first-run success rule |
| D08 yadof package | Required documentation wheel rebuild/reinstall, origin verification, and full installed tests. | Code-identical acceptance wheel imported from outer `.venv` site-packages; synchronized `package_foundation.md` read through `yadof docs`; 450/450 tests passed. After this terminal ledger was frozen, the final documentation wheel was rebuilt/reinstalled and received focused document acceptance; its non-self-referential hash is reported in the task completion transcript. | verified |
| D09 repository closure | Final diff audit, one verified commit, fetch, ahead/behind decision, and conditional non-force push. | Final diff, portability, credential-pattern, TODO-marker, installed-package, formal-run, and smoke gates passed. This committed ledger cannot contain its own commit hash; the hash, fetched ahead/behind counts, and push disposition are recorded in the terminal task completion transcript. | verified by terminal Git closure |

## Measurements and run records

### Installed-package and automated verification

- Built and force-reinstalled `yadof_benchmark-0.4.0-py3-none-any.whl`; the
  imported package resolves below the outer environment's `site-packages`.
- The installed wheel contains both canonical strategies. Their SHA-256 values
  are `8149258DB44B9FE877323E7066677EEBA9FD0AA6B857DA65C4776588DF5F3FB0`
  (real-only) and
  `4F5F876226A6076F7EA530DBC65BB927B30A80DF217CFF4A0FF2C7880676876B`
  (GPSAF/PCA-SVD), matching the read-only measured campaign inputs.
- Installed-package suite: 35 passed. Coverage includes presets and provenance,
  exact complete/smoke identity, deterministic ordering, collision rejection,
  special and long labels, legacy reads, executable `program/v1` discrimination,
  real evaluation parsing, TTY/non-TTY presentation, elapsed heartbeats, descendant
  process cleanup, timeout failure, and continuation to an independent cell.
- The distributable-path scan initially found five `D:` examples in benchmark
  public documentation and three in the synchronized yadof user document. They
  now use relative paths. A follow-up scan of changed distributable code,
  presets, public examples, and package documentation found zero drive-letter,
  account, host-name, or outer-workspace identity matches.
- The pre-formal read-only review found that the lifecycle line carried the full
  label but the live row did not yet repeat it or expose timeout, worker, running,
  and queued state. A source-only presentation follow-up now adds those fields and
  five focused tests (41 installed test cases after parameterization). The
  detached run's installed package remains unchanged; final wheel installation,
  installed-suite verification, and derived smoke are pending
  its terminal state.

### Smoke runs

- Default no-argument portable workspace completed 2/2 collected and valid in
  24.131 s, with no anomaly, timeout, or postprocessor failure. Its terminal
  output demonstrated semantic labels and real evaluation progress from 1 to 24.
- Complete-derived smoke changed only generations from 25 to 1. It preserved the
  18-cell matrix, population 200, timeout 7200 s, baseline/strategy/seed identities,
  digests, and execution policies. It completed 18/18 collected and valid in
  757.059 s, with no anomaly, timeout, command, report, or postprocessor failure.
  Six Chrono cells recorded tolerated per-evaluation simulation errors while still
  satisfying the declared result contracts.

### Cell-concurrency A/B decision

The same two-cell portable load ran in interleaved order `1,2,2,1,1,2`, giving
three independent repetitions per setting. All six runs completed with 2/2 valid
cells and identical input identities, digests, budgets, seeds, and simulator
worker configuration.

| Cell concurrency | Durations (s) | Median (s) | Peak process-tree memory | Observed process-tree size |
| --- | --- | --- | --- | --- |
| 1 | 13.214, 13.244, 13.231 | 13.231 | 0.956-0.966 GB | 12 |
| 2 | 8.106, 8.128, 8.534 | 8.128 | 1.350-1.365 GB | 22 |

The synthetic load improved by 38.568%, but it did not exercise the complete
workflow's PyChrono/ngspice license, memory, and nested-worker constraints
(`max_workers` 4/64/32 by baseline). The safety half of the acceptance rule is
therefore unproven. The shipped default remains `cell_concurrency=1`; users may
still opt in explicitly after evaluating their own host limits. Raw measurement
evidence is in `temp/20260901_yadof_benchmark_concurrency_ab_retry1.json` outside
the distributable checkout; its SHA-256 is
`385A9FFCEA2D313CA8ECA085D28B2B9B9557B8A227BE6D73FD6714B381780AC1`.

### Formal complete campaign

Formal run 1 was launched from the fresh outer-workspace directory
`temp/20260901_151852-formal-complete-run-1` with declared budgets and detached
PID 8400. Its immutable pre-launch provenance record has SHA-256
`8216B0F2BA373C02CD6F7A03E04AA361E677B6751EF15463FBA9D662B82FD164`.
The same-task 20-minute monitor tracked the run while it was detached. When its
scheduler presentation became overdue while this goal occupied the same task, it
was paused and equivalent 20-minute checks continued inside this task; no
standalone replacement task was created.

The original pre-launch record omitted the spec/command/environment fields and
did not persist a canonical working-tree patch digest. The non-running-workspace
addendum `temp/20260901_151852-formal-complete-run-1-provenance-addendum.json`
supplies the immutable spec/runtime/receipt hashes, exact commands, process and
environment summary, and an honest provenance limitation; its SHA-256 is
`C72578C6980F0EFC441B61A13C90E4E3964520D926A8261154EB3CED21D723D1`.
It does not retroactively invent the missing pre-launch Git patch digest. The
actual executable candidate remains exactly bound by the installed wheel and
materialized workflow/strategy hashes. A post-launch Git digest separately marks
the source-only active-progress follow-up that is absent from the running wheel.

Live inspection of run 1 also demonstrated that planned/active cells were being
listed as more than one hundred transient anomalies. The final source candidate
now suppresses those expected running-state incompleteness diagnostics while
preserving actual state errors, completed-cell validity errors, and all terminal
incompleteness evidence.

The timeout cleanup review also found that a Windows `psutil.AccessDenied` during
tree enumeration would not reach the recursive `taskkill /T /F` fallback. The
final source candidate now catches `psutil.Error`, terminates descendants before
the parent when enumeration succeeds, waits for survivors after the second kill,
and has a focused permission-denial fallback test.

To strengthen traceability without rewriting that limitation, the after-launch
reconstruction record
`temp/20260901_151852-formal-complete-run-1-prelaunch-reconstruction.json`
(SHA-256
`B3DDE6E0993AB62F4BB68256E9B3C310F4A6B7D1CDCDC54D64590A989C560C88`)
maps the 39 launch-time modified/untracked files to canonical UTF-8/LF content.
Its manifest has SHA-256
`7CC97F4EE9E93A5A072578D5C5F5D426ED9C8BF260C4F1710EF82810DBA85DD0`.
The record is explicitly a reconstruction from the installed runtime plus
reversed known post-launch-only edits, not a retroactive pre-launch observation
or Git patch digest.

Run 1 reached terminal `completed` status after 20,771.407 seconds. All 18 cells
were collected and valid at population 200 and 25 generations. The 72 check,
run, view-cost, and baseline-postprocess command records all had return code zero,
`timed_out=false`, and no required cleanup. The terminal state contained no
anomalies, publication failures, or postprocessor failures. All 18 final
hypervolume and AUC rows were available and aggregate-eligible, all nine paired
comparisons were valid, all six cross-seed aggregates included 3/3 seeds, and
the nine GPSAF cells each recorded 24 completed and zero failed surrogate events.
The 450 hypervolume trajectory rows cover exactly 25 generations for every cell.

All 18 domain postprocessor manifests parsed successfully and their 84 referenced
outputs existed; the 18 cost PNGs also existed, with no zero-byte visualization
artifact. A final host process-table query found no process whose command line
referenced the run workspace after the retained wrapper was closed. The terminal
evidence hashes are: `state.json`
`C1CD0932219F11E52BC77C6D850774A95F2702E8BE04D8315FA71AE8696CE9C2`,
`results.json`
`08153F90DA63628474FE764C506F1A8BD451A785148114734633C019A9EDEE77`,
`results.csv`
`D64AF9BF4CBC871F369F692281D4DDE7A3996639FF91FF19259DFF8E082497E4`,
`reports/descriptive-results.json`
`45AC1066F6B15AFA7915B0157154CB9E680CE7B691BA25E3008B729705A8B009`,
and `reports/summary.md`
`A516E00EBD2A3F43941FD1ACF81E41D4E83979E11BED7457CB79DA5301AE3C71`.
Because run 1 satisfies the formal acceptance gate, run 2 is deliberately not
launched; the formal campaign used one of the allowed two complete runs.

### Final installed acceptance

The final `yadof-benchmark 0.4.0` wheel has SHA-256
`436ADFC49BA1191E6C2B0493A3C33156CAF58056A7CA5400C6C4A2FA68D1B72F` and
imports from the outer environment's `site-packages`. Its installed preset catalog
retains portable as the sole default, complete as explicit with population 200,
25 generations, and timeout 7200 seconds, and blank as explicit. The canonical
strategy hashes remain
`8149258DB44B9FE877323E7066677EEBA9FD0AA6B857DA65C4776588DF5F3FB0` and
`4F5F876226A6076F7EA530DBC65BB927B30A80DF217CFF4A0FF2C7880676876B`.
The complete installed suite passed 41/41 tests.

Fresh workspace
`temp/20260901_211911-20260901_final-candidate-complete-derived-smoke`
materialized the installed complete preset and mechanically selected the smoke
budget. Its check and plan proved 18 cells, population 200, generations 1,
timeout 7200 seconds, serial cell scheduling, the same three baselines, two
strategies, three seeds, and packaged input hashes. Execution completed 18/18
collected and valid in 756.307 seconds. All 72 command records returned zero with
no timeout or cleanup requirement; every result had 200 planned and attempted
evaluations, a complete 200-member generation-zero population, matching objective
and raw-data contracts, an available metric, and no issue. All 18 visualization
sets existed and a final process query found no residual process. Evidence hashes
are `state.json`
`8B378664A4F25DF7E2DBC2A48702B7B5CD95885FCF595EA8AE0C8E9D79805093`,
`spec.json`
`B71803CA0F543F3C36012219A509E61560E12A19457B3FFFC119DE4CD46C5DC1`,
`runtime.json`
`FA0FBC6692D5CAED844DBF9F5299E4C0002C833A17433F42AD64C1F5B55ECCC3`,
`reports/descriptive-results.json`
`46A2759FD0F5F646A1B797957CA0989FF3503924F4F25BFE06056CD51EBE491E`,
and `reports/summary.md`
`F8FC5449077A67DAB8FBEB33CD3AB88A85358E27542D98EEC4D6CD3203A72335`.

The synchronized `yadof 0.5.0` code-identical acceptance wheel had SHA-256
`96AD7EA9D64E442D80AABB383EA224E0BD9C9419C66E9C7B21C42EDF6A4536C9`,
imported from the outer environment's `site-packages`, and exposed the new
benchmark preset/label contract through
`yadof docs show user package_foundation.md`. The full installed yadof suite
passed 450/450 tests in 108.78 seconds. The benchmark suite then passed 41/41
again against that reinstalled yadof wheel. Because this terminal ledger and its
change record are themselves packaged development documents, one final doc-only
wheel is built and reinstalled after their content is frozen; its hash and focused
document acceptance are deliberately recorded outside this self-referential wheel
content in the task completion transcript.
