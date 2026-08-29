# Module blueprint: tests

## Scope

Maintained generic pytest modules live only in `tests/` and, for final acceptance,
import the wheel force-installed into the sibling `.venv`. Tests create neutral
temporary workspaces. Default tests require no live pool, simulator, concrete model,
license, machine identity, or credential.

The independent benchmark distribution owns focused structural tests under
`yadof-benchmark/tests/`. They consume an installed yadof distribution and use
temporary code-first workspaces, self-describing baselines, complete strategy
files, fake commands, and public result fixtures. They do not launch simulators or
claim performance evidence.

Coverage requires:

- initialization creates direct single-execution roots without `runs/`;
- standard and slow-surrogate omitted budgets resolve to 200x50 and 200x15,
  respectively, with one default seed;
- explicit budgets and arbitrary explicit seed lists remain unchanged;
- cells use `cNNNN` paths and artifact filenames remain short while semantic
  identity stays in the spec;
- initialization records installed versions and process account once, with no
  driver/workflow/strategy snapshot tree;
- cell and workflow postprocessing outputs are direct and have no attempt layer;
- complete attempted budgets with individual failed/non-finite simulations remain
  valid when finite contract-valid metrics exist;
- missing attempts and all other hard validity failures remain non-successful;
- FIFO publication/storage boundaries, concurrency controls, progress ownership,
  and required visualizations retain focused fault tests proportional to changes;
- inspect is bounded/read-only and has no resume command;
- Windows detach runs the installed `run --workspace` command, defaults visible,
  keeps the visible console open after the command exits, returns
  PID/workspace/log/inspect, and never claims to switch process identity; hidden
  detach remains direct and automatic;
- public API/CLI and distribution entry points contain no run ID or resume surface.

Installed-wheel acceptance uses a fresh pytest base temp and does not substitute
for separately authorized real adapter smoke or performance work.

## Required coverage

- package metadata, wheel/sdist members, console entry point, clean external install,
  and read-only site-packages operation;
- initialization no-overwrite behavior, marker/check diagnostics, explicit paths,
  config precedence, normalized `[0, 1]` starter cost behavior, and two-workspace
  task/module isolation;
- parameter assignment, job static hash, task payload exclusions, minimal worker
  support, worker-owned lifecycle/execute metadata/flat transport, task/framework
  code-boundary templates, top-level-only AEDT results/lock exclusion, and absence
  of any yadof runtime archive/config in jobs;
- direct `workflow.py` HTCondor submit shape, Windows slot-user values, resource/time
  policy, matchmaking diagnostics, bounded retries, and per-job mocked failures;
- shared cross-backend resource calibration, local process-tree measurements,
  default-eight local cap, CPU/memory/disk capacity limits, reserve policy, disabled
  autodetection, and population bounds;
- explicit fast task validation; pure-memory and real-subprocess kernels; no
  durable job folders; fast-specific resource planning; parallel overlap and
  out-of-order completion; worker crash/timeout isolation, descendant cleanup, and
  replacement; scratch cleanup; memory NPZ persistence; fast/local shared-kernel
  equivalence; and two-workspace worker/history isolation;
- explicit `rawData.zip` output transfer, flat zip members, rejection of nested
  rawData, local validation, reusable cost/rawData helpers, dynamic cost, and
  persistence atomicity, including bounded slow-tail algebraic costs and task
  fallback `1.0`;
- backend-neutral finalization; immutable segments; exact unpublished count/byte
  budgets; float32/float64 large-candidate singleton publication; full-budget
  backpressure, same-batch retry, fatal writer propagation, and shutdown durability;
  OS campaign-lock
  exclusivity; corrupt candidate/segment tolerance; task-snapshot hot reload and
  fingerprint invalidation; no old-segment reopen; 5,000-row hot-finalizer and
  synthetic 100,000-row catalog scale;
- optimizer start/resume/shape/failure behavior, surrogate rawData-first training,
  checkpoint compatibility, intervals, and workspace-keyed scheduling;
- PCA/SVD centered-versus-uncentered per-field mathematics, rank clamp and
  mean-only cases, schema/dtype round trips, validation-oracle labeling,
  parameter-only ridge prediction, zero-width cost intervals, no posterior,
  atomic exact-state recovery, and lazy Torch imports;
- joint rawData posterior protocol through a neutral sample-backed backend with at
  least two candidates, different-shaped named fields, and two objectives: stable
  seed/draw/source identity, repeated candidates, empty populations, candidate
  permutation and chunk size/order invariance, exact basename/main-key selectors,
  schema rejection, streamed/materialized projector equivalence, finite task
  fallback validity, typed invalid outcomes, recorder non-entry, semantic identity,
  and optional-backend lazy imports;
- conditional-INR posterior adapter coverage for draw counts below/equal/above the
  ensemble size, seeded permutation cycles, exact selected-member full-grid and
  derived-cost parity, duplicate/permutation/chunk invariance, nominal/effective
  support, member-failure isolation without field splicing, bounded diagnostics,
  unchanged legacy identity/API, and direct projection into the Gate 2 backend;
- hierarchical-CAE coverage for mixed scalar/1-D/2-D and explicit rank-3 layouts,
  schema/dtype/axis round trips, stable non-overlapping groups, no-policy ordinary
  behavior, explicit/diagnostic/shape assessment priority, design-by-field cap and
  weights, shared-token masks, clean residual gates, independent anti-noise arms,
  applicability/semantic identity, tiny staged training, atomic recovery, complete
  rawData prediction, coherent member draws, all-axis linear/log/periodic coordinate
  encoding, stored-grid consistency, in-domain off-grid queries, checkpoint recovery,
  viewer dispatch, and query-state immutability. Source-benchmark tests separately
  freeze Gate 0 v2--v5 integrity and failed performance decision, plus the v6 pre-access
  experimental plan and v7 descriptive result without backfilled thresholds;
- fake sample-backed qLogNEHVI coverage against BoTorch's own qLogEHVI zero-noise
  fixed-baseline limit: minimization negated exactly once, reference point, q=1/q=2,
  deterministic seed, aligned correlated draws, whole-draw invalid rejection,
  finite `1.0`, finite-support warn/reject, empty/duplicate/backend-missing cases,
  mature-backend spy ownership, compact memory/timing diagnostics, and lazy parent
  imports;
- posterior-assisted coverage for public composition/identity, multi-objective-
  only and pending/outcome rejection, baseline filtering/duplicates/finite `1.0`,
  deterministic greedy backend delegation, empty/duplicate pools, finite support
  warn/fallback/reject, typed current blockers, variance-only rejection, calibrated
  applicability exclusion plus low/boundary real exploration, sampler/readiness
  signature binding, no predicted rawData retention, common real-evaluator handoff,
  full-real backend fallback, support hard stop, and recorder-failure propagation.
  This validates framework behavior, not acquisition or optimizer performance;
- CLI/docs, integrated cost/time views including grouped `view all`,
  the 50-generation run default, default-on run progress with an explicit quiet
  override, per-generation successful/error/remaining outcome counts, streamed
  distributed result notification, flushed pre-execution standalone-smoke feedback,
  cost-view isolation/reporting for unusable history rows and optional annotations,
  streamed candidate progress and its final total,
  left-axis average cost, all-individual/current-generation hypervolume values,
  generation grouping, renderable image output, useful summaries, lazy optional
  viewer registration,
  execute-machine/error encodings, worker-over-Condor machine precedence,
  active/held/removed/terminated historical timeout log fallback,
  evicted/never-executed timeout behavior,
  tools/adapters, and artifact exclusion of examples/runtime data;
- ngspice adapter discovery/copying, parameter staging, owned batch-control
  generation, real/complex ASCII rawfile parsing, explicit component conversion,
  and schema-versioned rawData export without requiring a live simulator;
- packaged PyChrono adapter conformance through fake external interpreters:
  explicit absolute runtime resolution, paths with spaces, versioned JSON/NPZ,
  cleaned Python environment, Windows child-only Conda DLL search entries with
  inherited-PATH retention, bounded diagnostics, invalid/escaping/missing output,
  handled error versus crash, timeout descendant cleanup, and concurrent scratch
  isolation without Miniforge or PyChrono, plus a Windows physical scratch longer
  than the traditional process current-directory limit launched through a cleaned
  short alias;
- lazy `view surrogate` GUI/summary/audit registration and help, viewer
  wheel/sdist/dev_doc/report membership, deterministic text/JSON summary and audit
  encoding, checkpoint discovery, 0D/1D/2D rawData slice extraction from
  higher-rank data, arbitrary fixed-coordinate controls, method-specific
  stored-grid/off-grid surrogate-query compatibility, hierarchical checkpoint
  discovery/dispatch, aggregate selection, sampling, and cancellation
  when optional dependencies are installed.

## Test placement

Task-specific tests that assert a concrete model/design, physical objective,
frequency band, exact active parameter set, or expected simulator result stay with a
reference/disposable workspace or, when they verify the declared frozen comparison
contract, below `yadof-benchmark/`. Neutral fake adapters and synthetic
0D/1D/2D/3D rawData remain package fixtures.

Tests should prefer observable behavior, durable data, public boundaries, and
failure semantics. Do not add repository-layout meta-tests, scans that merely prove
an old token or path is absent, duplicate import-alias checks, or assertions over
exact font sizes, DPI, colors, legend coordinates, line widths, and other incidental
presentation constants. A rendering smoke may prove that valid data produces a
non-empty artifact without freezing its pixel dimensions.

## Acceptance

Build a wheel, force-reinstall without editable/PYTHONPATH shortcuts, verify
`yadof.__file__` is under the venv site-packages, run focused tests during iteration,
then the complete suite. Real simulator/HTCondor smoke is an integration step, not
part of generic pytest; whether an agent may start it autonomously follows the user
documentation's concrete cost/risk policy.

For benchmark-runner changes, run its focused unit suite with a fresh absolute
`--basetemp` and disabled pytest cache, then use an external temporary study to
exercise the no-write `plan` from the repository root. Do not launch a measured
study as generic acceptance.
