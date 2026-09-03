# yadof benchmark formal campaign results

## Scope and evidence identity

This document summarizes the terminal evidence from the formal `complete` campaign
run on 2026-09-01. It is historical, descriptive performance evidence rather than
an instruction, strategy ranking, or scientific acceptance decision. All
`temp/...` paths below are relative to the outer workspace that contains the
`20260822 yadof` checkout; those runtime artifacts are not committed to Git.

- Formal workspace: `temp/20260901_151852-formal-complete-run-1`
- Terminal report generation time: `2026-09-01T13:06:34.474513Z`
- Benchmark distribution: `yadof-benchmark 0.4.0`
- Benchmark wheel SHA-256:
  `436ADFC49BA1191E6C2B0493A3C33156CAF58056A7CA5400C6C4A2FA68D1B72F`
- Preset: explicit `complete`, with three baselines, two strategies, and seeds
  101/102/103, for 18 cells total
- Cell budget: population 200, generations 25, 5,000 planned evaluations, and a
  7,200-second timeout
- Scheduling policy: `cell_concurrency=1` and `fail_fast=False`
- Strategies: real-only NSGA-III and explicit NSGA-III with GPSAF plus PCA/SVD

The formal run reached terminal `completed` status in 20,771.407 seconds
(approximately 5 hours 46 minutes 11 seconds). Because it passed every formal
gate, the allowed second complete run was deliberately not launched.

## Verified terminal outcome

| Gate | Verified result |
| --- | --- |
| Cell collection and validity | 18/18 collected and valid |
| Commands | 72/72 returned zero; no command timed out or required cleanup |
| Budget | Every cell planned and attempted 5,000 evaluations |
| Metrics | 18/18 final-HV and normalized HV-AUC rows available |
| Paired fairness | 9/9 baseline/seed pairs valid |
| Cross-seed aggregation | 6/6 strategy/baseline aggregates included all 3/3 seeds |
| Trajectories | 450 rows, exactly 25 generations for each of 18 cells |
| Surrogate training | 216/216 events completed; zero failed events |
| Domain outputs | 18/18 manifests parsed and all 84 referenced outputs existed |
| Visualizations | 18/18 cost PNGs existed and none was zero-byte |
| Terminal diagnostics | No anomaly, publication failure, or postprocessor failure |
| Process cleanup | No process still referenced the formal workspace after wrapper closure |

The six Chrono cells had tolerated individual simulation failures but still met
their declared validity contracts. Across the three Chrono seeds, real-only
completed 14,016 of 15,000 attempted evaluations (984 failed), while GPSAF
completed 14,544 of 15,000 (456 failed). Every finite result count matched its
completed count. The SAW-ladder and synthetic-antenna cells completed all 5,000
evaluations per cell.

## Descriptive strategy observations

The following values are three-seed means from the generated report. Deltas are
`GPSAF - real-only`; percentages use real-only as the denominator.

| Baseline | Real-only mean final HV | GPSAF mean final HV | Delta |
| --- | ---: | ---: | ---: |
| `chrono/trebuchet` | 0.46824912 | 0.30866244 | -0.15958668 (-34.082%) |
| `ngspice/saw-ladder` | 0.37858397 | 0.28615779 | -0.09242618 (-24.414%) |
| `test-com/synthetic-antenna` | 0.30690181 | 0.21387809 | -0.09302371 (-30.311%) |

| Baseline | Real-only mean HV-AUC/evaluation | GPSAF mean HV-AUC/evaluation | Delta |
| --- | ---: | ---: | ---: |
| `chrono/trebuchet` | 0.35019031 | 0.26415523 | -0.08603507 (-24.568%) |
| `ngspice/saw-ladder` | 0.20628912 | 0.18413672 | -0.02215239 (-10.739%) |
| `test-com/synthetic-antenna` | 0.16847903 | 0.13654333 | -0.03193570 (-18.955%) |

Observed final HV was higher for real-only in all 9/9 matched baseline/seed pairs.
Observed HV-AUC/evaluation was higher for real-only in 7/9 pairs; GPSAF was higher
for SAW-ladder seeds 101 and 103. Consequently, the three-seed means favored
real-only on both reported metrics for all three baselines in this campaign.

This is not evidence of general strategy superiority. The campaign used only
three seeds per baseline, performed no significance test, and did not sweep GPSAF,
PCA/SVD, or optimizer settings. The unequal finite Chrono counts also remain part
of the interpretation even though planned budget, attempted budget, baseline
input, generation-zero population, and all declared pair-validity gates matched.

## Surrogate-training observations

Each of the nine GPSAF cells emitted 24 successful training events. Per-cell
median and maximum durations were:

| Baseline | Median range across seeds (s) | Largest observed event (s) |
| --- | ---: | ---: |
| `chrono/trebuchet` | 33.106-33.981 | 36.921 |
| `ngspice/saw-ladder` | 6.450-6.733 | 7.757 |
| `test-com/synthetic-antenna` | 26.593-28.154 | 101.693 |

No representative expensive-generation duration was configured, so the report
does not convert these timings into an overhead ratio or acceptance conclusion.

## Supporting acceptance and operational decision

- The default portable smoke completed 2/2 collected and valid cells in 24.131
  seconds.
- The final installed complete-derived smoke preserved the formal matrix,
  population, identities, hashes, policies, and timeout while changing only
  generations to 1. It completed 18/18 collected and valid in 756.307 seconds;
  all 72 commands returned zero and no process remained.
- The installed benchmark suite passed 41/41 tests. The installed yadof suite
  passed 450/450 tests, after which the benchmark suite passed 41/41 again.
- A three-repetition synthetic scheduling A/B test measured a 13.231-second serial
  median and an 8.128-second parallel median, a 38.568% reduction. Parallel peak
  process-tree memory rose from about 0.96 GB to 1.36 GB and process count from 12
  to 22. Because that test did not establish PyChrono/ngspice license, memory, or
  nested-worker safety, the shipped default remains `cell_concurrency=1`.
- The implementation and acceptance closure was committed as
  `6bd789137c5195ac25f252f135655440cd201614`.

The final documentation-only `yadof 0.5.0` wheel built after the closure ledger
was frozen has SHA-256
`614C06B0DF42100A31031CF2CB8460919B0903006B37644CBCE0831CE2801E99`.

## Artifact identities

| Artifact below the formal workspace | SHA-256 |
| --- | --- |
| `state.json` | `C1CD0932219F11E52BC77C6D850774A95F2702E8BE04D8315FA71AE8696CE9C2` |
| `results.json` | `08153F90DA63628474FE764C506F1A8BD451A785148114734633C019A9EDEE77` |
| `results.csv` | `D64AF9BF4CBC871F369F692281D4DDE7A3996639FF91FF19259DFF8E082497E4` |
| `reports/descriptive-results.json` | `45AC1066F6B15AFA7915B0157154CB9E680CE7B691BA25E3008B729705A8B009` |
| `reports/summary.md` | `A516E00EBD2A3F43941FD1ACF81E41D4E83979E11BED7457CB79DA5301AE3C71` |

The original pre-launch provenance record did not contain a canonical Git working-
tree patch digest. A separately hashed post-launch addendum and reconstruction
improve traceability without claiming retroactive pre-launch observation. The
installed benchmark wheel plus the materialized workflow and strategy hashes bind
the executable candidate used by the campaign; the missing pre-launch Git patch
digest remains a provenance limitation.
