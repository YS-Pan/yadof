# Perfect surrogate comparison

`init --preset perfect` creates six cells: NSGA-III and GPSAF with a direct
simulation oracle on Chrono trebuchet, ngspice SAW ladder, and synthetic antenna.
Seed is 101, population is 200. The reference runs all 50 generations (10,000
formal evaluations). GPSAF stops at its first strictly lower cumulative top-10
mean, or after generation 50. The initial design is generation 1 and is paired
between strategies. Alpha=3, beta=3, gamma=0.5 and exploration=0.10; operator
settings are explicit in each strategy's identity.

Each individual's avg cost is the arithmetic mean of its objectives. At each
generation, sort the cumulative formal real history by avg cost and average the
ten lowest. Failed/nonfinite outcomes cannot displace finite top-ten entries;
fewer than ten finite entries has no finite metric and cannot beat a threshold.
The reference's last-generation metric is frozen before GPSAF starts. Equality
does not count as a crossing. No extra generations or automatic retuning occur.
If no crossing occurs, the summary records `50 代内未超过`.

`Benchmark.compare(..., stop_on_top10_reference=True)` declares this opt-in
stopping protocol. It requires `reference` to be the first strategy and
`cell_concurrency=1`. Strategies must publish generation receipts with
`yadof_benchmark.perfect_protocol.record_generation`. The executor supplies
`benchmark_control.json` before the command starts. Collected real records
independently recompute every metric and validate that the budget was either the
full declared budget or exactly the first strict crossing. Other comparisons
still require equal complete attempted budgets. Paired initial designs and task
digests remain required; early stopping does not establish performance robustness.

The oracle is the installable `yadof_benchmark.perfect_oracle.PerfectSimulationOracle`.
It calls the baseline's frozen `evaluate_rawdata` kernel and the same assigned
parameters/current cost chain as formal evaluation. It passes
`StructuredRawDataSample.cost_items()` payloads to that cost interface. It performs
no training and does not load the growing rawData archive for model fitting.
The exact zero error is justified by this contract, and every selected predicted
row is compared bitwise with its later formal cost row. Any mismatch stops the cell.
Its empty training value does not block freshness: the real kernel belongs to the
current context. After the initial real generation, failure to enter assisted
selection is a fatal contract error, not an apparently successful real-only run.

Task kernels may declare `PHYSICAL_FAILURE_TYPES` as a tuple of specific exception
classes. Only these failures become `valid_mask=False`, no rawData and all `+inf`
costs, matching failed formal evaluations. Chrono marks impossible initial geometry
explicitly; its adapter distinguishes physical errors and time limits from task,
launch and protocol errors. ngspice distinguishes solver/time-limit errors from
interface errors. Import, programming, rawData and cost errors propagate as
`SurrogateContractError`. All-one finite costs are valid and never an error signal.

The Chrono model also identifies numerical divergence in simulator-produced
positions, velocities, reactions and histories before they reach task-input
guards. These are failed candidates, just like impossible geometry or an
individual timeout: selection continues with `valid_mask=False`, no rawData and
`+inf` costs. The formal evaluation applies the same failure contract. A failed
candidate does not stop the comparison. Shape/API errors, missing evidence and
an all-infinite formal generation remain visible stopping conditions. This is
not a blanket conversion of arbitrary exceptions into predictions.

Chrono's trebuchet model explicitly calls `SetMinBounceSpeed(0.15)` after every
`ChSystemNSC()` creation. This sets the documented NSC default, avoiding the
uninitialized contact-container member in Chrono 10.0.0. The model and bundled
adapter copies are included in the wheel and therefore in newly created cells.

Oracle screening lives only in memory and `oracle_audit/events.jsonl`. It never
enters formal history, evaluation budgets or the top-ten metric. The audit records
oracle simulation counts, physical failures, contract errors, and selected/actual
cost correspondence. Prediction events also retain each failed candidate's
index, normalized parameters and bounded error text for reproduction, outside
the formal history. `experiment_metrics/gNNNN.json` and `latest.json` record
formal counts, failures/nonfinite counts and the cumulative metric after each
committed generation. `reports/perfect-surrogate-summary.json` and `.md` contain
the final matrix summary, including failed cells.
The perfect preset registers this summary with `run_on_failure=True`; it runs
after the scheduler terminates even if a cell failed. Failed comparisons remain
failed, and ordinary postprocessors that require complete collection are skipped.

Before a full run, use an independent required complete-preset smoke workspace
and a small integration workspace that reaches assisted generations. Keep both
outside the formal experiment. Concurrency comes from baseline physical-core
multipliers; record both the resolved workers and multipliers. Oracle simulation
can dominate runtime: size the baseline cell timeout for the full 50-generation
run, not one generation. A task-local copied baseline can set a larger explicit
timeout and a host-derived multiplier without changing the packaged baseline.

For a frozen experiment, call `runtime_freeze.freeze_runtime(workspace,
command=..., provenance=...)` before starting it. Record wheel hashes, source
commit, simulator versions/executable hashes and all settings in provenance.
The packaged programs check the installed-file fingerprint at generation start,
before formal evaluation and before commit. A changed installation aborts the
run. Use a new workspace for a new implementation.

Launch with the documented `run --detach --hidden` when a background process is
desired. Verify the complete matrix, live controller, and a real-evaluation
progress/log artifact in a short bounded check. Once verified, hand off; final
results are produced automatically without an agent or periodic monitoring.

To repeat only Chrono, initialize a new `perfect` workspace and change the
comparison's `baselines` to `["chrono/trebuchet"]`. Keep both strategy
registrations, `reference="real-nsga3"`, the paired seed/budget, the stopping
protocol and the final-summary registration. Run both arms from fresh history;
do not continue or overwrite an earlier failed workspace. Keep validation data
outside this new measured workspace.
