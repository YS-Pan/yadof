# 2026-08-27 15:24 - Add Conditional-INR Posterior Adapter and qLogNEHVI Spike

## Context

- Gate 1 supplied the backend-neutral persistent rawData function-sampler and
  current-cost projector. Gate 2 requires the earliest concrete vertical slice:
  expose conditional-INR members honestly as finite joint draws, then prove a
  mature qLogNEHVI backend can consume fake and adapter-backed objective samples.
- The default `conditional_inr()` + GPSAF path, checkpoint mathematics, viewer,
  task rawData, and real-evaluation/recording contract must remain unchanged.
- This change is not authorized to implement CAE, calibration, a complete
  posterior-assisted strategy, a real-simulator campaign, or a 1000/2000-design
  performance claim.

## Library-First Audit

Implementation-day audit selected BoTorch 0.18.1:

| concern | finding / decision |
|---|---|
| distribution / release | `botorch==0.18.1`, released on PyPI 2026-06-08; official qLog multi-objective API is available |
| license | MIT, from the official [BoTorch license](https://github.com/meta-pytorch/botorch/blob/main/LICENSE) |
| Python / Torch | BoTorch declares Python `>=3.11` and Torch `>=2.4`; the acceptance host uses CPython 3.13.11 and Torch 2.10.0+cu128 |
| selected API | official `qLogNoisyExpectedHypervolumeImprovement`, preferred over legacy non-log qNEHVI by the [BoTorch acquisition API](https://botorch.readthedocs.io/en/latest/acquisition.html) |
| baseline / noise | the API consumes `X_baseline`; yadof repeats completed real costs deterministically across empirical draws and includes no observation noise |
| pending / constraints | BoTorch supports these surfaces, but Gate 2 deliberately exposes neither because yadof has no corresponding joint pending/outcome-constraint contract yet |
| sample-backed posterior | BoTorch `EnsembleModel` produces `EnsemblePosterior`; a thin lookup model plus `MCSampler` can enumerate yadof's aligned empirical draws exactly once |
| discrete candidates | acquisition evaluation accepts supplied q tensors; yadof scores explicit discrete index batches and does not use gradient `optimize_acqf` |
| seed | upstream persistent sampler owns function identities; the backend records its seed and enumerates supplied draws without independently reshuffling candidates/objectives |
| device | explicit Torch device; CPU exercised. CUDA availability is validated but GPU execution was not part of this Gate 2 host audit |
| exception / diagnostics | yadof validates shapes/contracts, rejects incomplete MC draws as a whole, reports support/mask/timing/memory, and converts a missing optional stack to `install yadof[qnehvi]` |

The optional extra is `torch>=2.4,<3` plus `botorch>=0.18,<0.19`. Torch is declared
directly because the adapter imports it; no undeclared transitive dependency is
assumed. BoTorch 0.18.x makes this optional feature Python 3.11+, while core yadof
retains Python 3.10 support.

### Ownership matrix

| owner | responsibility |
|---|---|
| BoTorch | qLogNEHVI log-improvement, non-dominated partitioning, hypervolume cells, smoothing, and the core numerical loop |
| yadof Gate 2 adapter | fixed real baseline samples, one minimization-to-maximization negation, exact sample lookup, complete-draw masking, finite-support policy, discrete batch grouping, lazy dependency error, compact diagnostics |
| future posterior-assisted strategy | pymoo/history-informed candidate pool, warm-up/freshness, exploration quota, low-support fallback choice, common real evaluation, recording, and generation metadata |

No custom hypervolume loop or empirical qNEHVI estimator was added. The official
wheel attempted its optional fused qLogEHVI C++ extension on this Windows host;
the user-local Torch extension directory was not writable, so BoTorch emitted its
documented warning and successfully used the pure-Python numerical fallback. This
is a non-blocking acceleration limitation, not a correctness fallback implemented
by yadof.

## Change

- Added the explicit `conditional_inr_posterior()` wrapper with a separate
  component/posterior semantic identity. `conditional_inr()` remains component
  version 2 and keeps its existing GPSAF-facing methods.
- Added a private persistent sampler that:
  - freezes exact `.npz` basenames with the trained state schema;
  - chooses one member per draw using deterministic seeded permutation cycles;
  - keeps that member across every candidate, rawData field, and derived objective;
  - uses the existing selected-member forward/scaler path and complete stored-grid
    reconstruction one candidate at a time for batch/chunk invariance;
  - never splices fields after a member failure; and
  - reports nominal loaded-member support separately from effective distinct
    complete sources.
- Extended streaming posterior diagnostics so inference or cost-projection failure
  visibly reduces effective draw/source support without changing stable nominal
  capability identity.
- Added a transient named-evidence session view solely to recover stable direct
  basenames; recorded-data format, writer, segments, and ownership are unchanged.
- Added the experimental `yadof.optimize.qnehvi_backend` boundary and private
  BoTorch adapter. It requires at least two objectives, fixed valid baseline truth,
  unique normalized candidate rows, explicit non-repeating q batches, and `[0,1]`
  cost/reference semantics. Finite `1.0` remains valid; any invalid candidate
  rejects its complete empirical draw.
- Added an independent `qnehvi` optional extra. Ordinary surrogate/optimize parent
  imports do not load Torch, BoTorch, or GPyTorch.

## Backend Spike Evidence

- Fake sample-backed tests exercise q=1 and q=2, deterministic seeds, fixed
  baseline, default minimization reference `(1, 1)`, correlated draw pairing,
  invalid whole-draw rejection, finite `1.0`, support warning/rejection, empty and
  duplicate pools, missing backend, and a spy proving BoTorch owns the acquisition
  object/numerical loop.
- In the deterministic fixed-baseline limit, qLogNEHVI log values match BoTorch
  qLogEHVI within `1e-4` for q=1 and q=2. Rearranging one objective independently
  across draws changes acquisition, demonstrating that the adapter preserves joint
  draw pairing rather than marginally resampling objectives.
- A real conditional-INR adapter sampler is streamed through
  `RawDataCostProjector` and then through the same qLogNEHVI backend. Its nominal
  and effective three-member support remains visible end to end.
- Focused installed-package result before final documentation refresh: `21 passed`.

One warm-process CPU measurement used q=1 batches and fake finite samples. Input
tensor bytes are deterministic; RSS deltas include allocator/runtime effects:

| pool × draws × objectives | backend wall | retained/constructed tensor bytes | process RSS delta |
|---|---:|---:|---:|
| 64 × 16 × 2 | 0.178451 s | 36,448 | 541,028,352 bytes (first Torch/BoTorch load and failed fused-extension attempt included) |
| 256 × 32 × 2 | 0.015201 s | 273,504 | 11,325,440 bytes |
| 128 × 32 × 3 | 0.175115 s | 205,408 | 6,729,728 bytes |

All acquisition values were finite and every supplied draw remained usable. These
are API/resource spike measurements on one host, not defaults, scaling guarantees,
or optimization-quality benchmarks. RawData projection cost and future strategy
pool-generation/evaluation cost remain separate measurements for later gates.

## Documentation

- Updated architecture, module/file blueprints, terminology, installation guidance,
  and optimization-workflow guidance for the explicit finite adapter and bounded
  backend spike.
- The completed conditional-INR adapter work package is archived. The qNEHVI
  strategy and overall validation TODOs remain active, with Gate 2 evidence
  recorded but no claim that their completion rules are met.

## Verification

- Built `yadof-0.4.1-py3-none-any.whl`, force-reinstalled it without dependency
  churn into the outer workspace `.venv`, and confirmed import origin is
  `.venv/Lib/site-packages/yadof/__init__.py`, not repository `src`.
- Focused posterior/adapter/backend installed-package suite: `21 passed`.
- Existing GPSAF/checkpoint/composition/viewer regression selection: `43 passed`.
- Complete installed-package suite after implementation, documentation, artifact
  assertions, and TODO archival: `279 passed in 71.46s`.
- Wheel metadata exposes `qnehvi` with direct `botorch<0.19,>=0.18` and
  `torch<3,>=2.4` requirements. Tests assert the new source modules, blueprints,
  change record, archived adapter TODO, and absence of its old active TODO path in
  built artifacts.
- No simulator, HTCondor job, smoke task, CAE training, frozen-dataset fit, or real
  optimization campaign was started.

## Impact and Follow-Up

- Gate 2 now validates the library/API/numerical boundary early without waiting for
  CAE data or claiming that a three-member uncalibrated posterior is production-
  quality uncertainty.
- The next execution unit may begin the minimal CAE Gate 3 only from this committed
  tree. Full qNEHVI strategy orchestration remains blocked on its own explicit
  implementation unit and later preregistered data/threshold/real-budget gates.
- The Windows fused-extension acceleration limitation is non-blocking; production
  timing work may provision a writable Torch extension cache, compiler, and Ninja,
  but this Gate does not mutate host tooling or package correctness semantics.
