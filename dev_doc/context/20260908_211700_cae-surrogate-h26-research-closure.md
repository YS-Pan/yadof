# CAE surrogate H21–H26 research closure

The user amended this task on 2026-09-08: finish the two running benchmarks, start
no further research, and complete the goal after closure. Both runs have now
finished and their results are audited. This administrative completion does not
establish the original scientific target. No candidate was promoted, integrated,
or subjected to the required nine fresh paired confirmations.

This is historical evidence, not a request to resume experiments. The user's
latest instructions govern any future task. Task-owned artifacts named below are
under `temp/` in the selected outer workspace; large rawData remain outside Git.

## Scientific contract and final result

The frozen research protocol used ordinary NSGA-III with 200 candidates and 50
generations as its reference. Each true candidate score is the arithmetic mean of
its objective costs, using `math.fsum`. Q is the mean of the ten lowest finite
true scores in cumulative formal history. Crossing requires Q strictly below the
paired ordinary reference at a complete 200-attempt batch boundary, within 1.5
times the paired perfect-surrogate crossing budget, rounded down to a full batch.
Failed/nonfinite attempts are charged; fewer than ten finite scores or an undefined
crossing cannot pass. Seeds 101/401/402/403 are development evidence only.

H26 used one frozen joint multioutput residual forest on all baselines, with 256
aligned complete-response members and actual splits across multiple rawData field
features. Expected cost is the equal-weight mean of current task costs projected
from complete members. It is distinct from the cost of the mean response. Own
completed finite prior records supply all training; GP capacity 512, conditional
residual preparation capacity 1024, and all 256 trees were retained. NSGA-III,
GPSAF and INR in these completed runs were unchanged. The read-only rawData
sharing and reusable training buffers introduced by b392949 were reused.

| Baseline | Seed | Ordinary R | Perfect N | H26 first N | Cap | Final Q | Pass |
|---|---:|---:|---:|---:|---:|---:|---|
| Chrono | 101 | 0.198523288029 | 1600 | undefined | 2400 | 0.231179151231 | no |
| SAW | 101 | 0.219988488842 | 3800 | 4000 | 5600 | 0.156492428791 | yes |
| test_com | 101 | 0.290199969926 | 3600 | 5400 | 5400 | 0.289989069423 | yes |
| Chrono | 401 | 0.181925330978 | 2200 | undefined | 3200 | 0.249272683749 | no |
| SAW | 401 | 0.270359315942 | 2200 | undefined | 3200 | 0.280038919559 | no |
| test_com | 401 | 0.289821014631 | 4200 | 5200 | 6200 | 0.287267346214 | yes |

H26 passed 3/6 development cases. The run completed all 26,000 attempts: 25,811
finite and 189 charged failures (Chrono 101: 99; Chrono 401: 90). All 130 full-batch
Q values and first crossings were independently recomputed exactly. Initial paired
coordinates/costs, task physics/cost files, own-prior training IDs, capacities and
actual joint-field use passed their numerical/structural checks.

Failures are tolerated outcomes, never a failure-count veto. The algorithm
continued through failed evaluations and completed every registered batch. A
separate H26 functional fixture passed 20 checks with 1,000 attempts, including
520 failures and wholly failed batches; its costs are not baseline performance
evidence. Real simulation errors can be unpredictable, so zero failures is not an
acceptance requirement. The development failures above are metric/budget failures.

## Runtime audit amendment

The online root `20260908_013600-astra-h26-parallel-development-a` completed at
13:00:15 UTC on 2026-09-08, original foreground session 64035, actual exit 0.
Wall time was 41,058.247 seconds with three independent cells and two fit workers.
Context-free Luna monitoring checked metadata every five minutes; the parent
received hourly summaries and waited without polling the live results.

A separate infrastructure task waited for this run to finish, then installed new
yadof/benchmark wheels. The original observer consequently exited 1 at the current
installed-package fingerprint guard, before reading numerical results. The frozen
runtime lock and failure were preserved. No package rollback or experiment rerun
was performed.

An explicit post-exit audit amendment retained the original observer's numerical,
pairing, full-response, training and failure-accounting checks. It verified exact
frozen experiment inputs and unchanged Python files under recorded_data,
job_template and workspace. The reviewed config change only added optional
optimizer batch/initial-population settings. All 54 installed-file differences
were recorded, with no installed change during the amended audit. The original
installed-runtime guard is still recorded as failed; amended audit success is not
a retroactive pass of that guard. The amended observer, original session 7818,
exited 0 in 141.792 seconds. Closure adds no fits, simulations or formal records.
Four already completed Chrono visualization replays are accounted separately.

## Exact compute reuse evidence

The second active run, `astra-h26-inverse-cache-parity-20260908-a`, completed at
10:45:56 UTC, original session 48019, actual exit 0, wall time 9,839.512 seconds.
All 24 cases, 28,800 queries and 7,372,800 complete member predictions matched the
reference response hashes, member costs, validity, mean response and expected
costs exactly. It fitted 6,144 residual trees and made no GP/PCA fits, simulator
calls or future-label reads.

The model-owned inverse-transform cache recorded 20,237,862 hits and 2,786,683
expansions with a 512 MiB payload bound. It preserves all members and weights,
uses exact coefficient keys, and falls back to the original tensor operation for
non-contiguous layouts. Earlier failed fixture/layout attempts remain recorded.
This cache is task-local, was not used by the online H26 candidate, and is not
installed. Different concurrency and machine loads prevent a total-wall speedup
claim from these runs. Exact parity is not scientific optimization acceptance.

## Earlier development and verified source fix

H21 passed 3/6 development cases; H23 passed 4/6 and failed both Chrono seeds.
H22 failed its offline screen; H24/H25 failed their SAW offline gates. H26's weak
offline minimax gate did not translate into passing all online development cases.
No offline improvement or software check is substituted for fresh confirmation.

The research exposed and fixed a local preparation deadlock: a coordinator's cost
interpreter retained the task import lock while later preparation workers needed
that lock. Local dispatch now freezes immutable parameter definitions before
worker startup, gives each job independent assignments, and hashes the same
definition signature without another import. Durable per-candidate errors and
cancellation precedence remain. This is the only framework implementation change
owned by this research task; experimental surrogate algorithms remain in `temp/`.

The fix's installed wheel passed 114 focused tests, 544 full yadof tests and 64
benchmark tests. After the separate infrastructure task updated the shared
installation, its successful installed-package regressions were reused: yadof
571 tests (two GP convergence warnings), benchmark 72 tests. These later runs
include the preparation regression tests and do not validate H26 scientifically.
See [the preparation fix record](../change_records/20260907_192303_unblock-parallel-local-preparation.md).

## Durable evidence identities

- `astra-h26-online-registration-20260908.json`: SHA256 `8e7db2b661193007710a7e1dcad8d1929274ae02ce97e048bbde226ee4362d2e`.
- Online `runtime_lock.json`: SHA256 `10688543d5a4a43d02f5cbe800f3794cb80429a3bcc5df39fff50594cfb6d607`.
- `astra-h26-online-closure-v2-20260908.json`: SHA256 `9063ab5e41325e5c6d0902166952720d9e72cd16e64148c240b74dd65ef8cd47`.
- `astra-h26-postexit-audit-amendment-20260908.json`: SHA256 `73ce1ef83f0fb0b4a8905fbfc604cd41c9d1526b30dc8db2e1d624e442f59437`.
- `astra-h26-postexit-runtime-audit-complete-20260908.json`: SHA256 `e8ff4bebdc85c09e0ec8427df8bcbb63b95b0f343a06be97c4ce895b74592af7`.
- `astra-h26-inverse-cache-parity-closure-20260908.json`: SHA256 `7f8f008c13fd4c2b055d9ec5a173c4d1c0b2dfa254e55c99207578a51e9a88a0`.
- Detailed history: `cae-surrogate-continuation-20260907.md`; amended scope: `cae-surrogate-stop-after-active-20260908.md`; reused test output: `astra-reused-installed-validation-20260908.json`.
