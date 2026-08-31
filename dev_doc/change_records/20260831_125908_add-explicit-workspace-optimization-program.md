# Add an explicit workspace optimization program

## Context

The installed optimizer previously fresh-loaded one complete
`submit/optimization.py:build_optimization()` strategy at every generation. That
made component composition workspace-owned, but the framework still owned the
hidden generation loop, data movement, training/evaluation ordering, and result
commit. Workspace authors could not express ordinary Python/NumPy transformations
or visibly compose the Stage 2--5 dataset, fit, search, and evaluation primitives.

The old source snapshot also mixed optimization control flow with generation-live
cost/evaluation sources. `yadof check` imported the strategy and called its factory,
so a nominally read-only validation could execute workspace top-level/factory code.
Resume relied on durable evidence and component checkpoints but had no explicit
framework-owned complete-generation pointer for a user-owned loop.

## Decision

Introduce an opt-in explicit workspace program with one exact literal declaration:
`YADOF_OPTIMIZATION_PROGRAM` v1 names the entry, exact helper files, semantic
identity, and capabilities. Validate its syntax, top-level shape, entry signature,
and canonical contained helper paths statically. Freeze the entry and exact helpers
once per run, before optional CLI smoke, and isolated-load the entry once. Keep its
source fingerprint separate from semantic compatibility identity.

Expose framework-created `OptimizationProgramContext`, `OptimizationRunScope`, and
`ProgramGenerationScope`. The workspace owns the visible generation/data/control
flow, while the scopes retain the existing `CampaignSession`, OS lock, recorder,
generation snapshots, evaluation/training handle registry, metadata, cleanup, and
result validation. A generation commits only on normal scope exit after training
resolution, evaluation-handle closure, durable recording flush, and strict metadata
publication.

Publish a small atomic program completion pointer after that boundary. Resume for
the same semantic signature must begin at exactly the next generation. Do not
serialize mid-generation Python, candidate, prediction, rawData, or pymoo state;
an interrupted generation leaves the prior pointer intact and reconstructs from
durable evidence/history.

Retain the legacy factory path only as the bounded Stage 6--8 migration seam. Static
checking recognizes it without executing it. Advanced consumers migrate in Stage 7
and the old loop/factory contract is deleted in Stage 8.

## Implementation

- Added `optimize/program.py` for static inspection, frozen source snapshots,
  isolated entry execution, semantic/source identity, public scopes, commit, and
  strict resume. CLI and public optimization APIs dispatch explicit programs
  directly and close caller/program-owned snapshots on every exit.
- Classified program entry/helper sources out of generation task copies while
  merging their hashes/fingerprint into complete provenance and task snapshot ID.
  Current parameters, cost, workflow, evaluation, and other task helpers remain
  generation-reloaded.
- Extended generation-handle accounting and strict metadata support so program
  scope exit waits normal training, rejects unclosed cancel-policy evaluations,
  flushes the existing recorder, then advances completion. No second writer,
  evaluator, campaign lock, or session was introduced.
- Added atomic program completion state beside the active semantic strategy pointer;
  corruption and incompatible/skip/repeat resume fail closed.
- Added public `combine_predicted_cost_rows()` and made GPSAF phases reuse it. The
  operation projects candidate subsets from prediction supersets and accepts only
  one interpretation/state/source semantic owner; GPSAF `gamma` behavior remains
  unchanged.
- Added real-only and PCA/SVD+GPSAF program fixtures covering static no-execution,
  helper isolation, program freeze, generation task reload, backend-independent
  event order, ordinary row transformation, commit/resume, handle/error cleanup,
  recorder failure, parity, and prediction non-entry.
- Updated the independent benchmark distribution to 0.2.2. Its planner statically
  recognizes an explicit strategy source set, hashes ordered relative paths and
  bytes for entry plus exact helpers, and materializes that set into every cell.
  Transitional single-file strategies remain supported for the migration window.
- Updated architecture, blueprints, terminology, packaged user guidance, and both
  benchmark developer/user contracts. The consumer inventory and Stage 8 deletion
  proof remain explicit.

## Verification and evidence

- Program/check/snapshot/evaluation/search/surrogate focused installed-wheel tests
  passed `69 passed in 18.65s`. The final installed yadof suite passed
  `443 passed in 94.11s`; the independent installed benchmark suite passed
  `21 passed in 1.02s` (its explicit-helper focused subset passed
  `4 passed in 0.39s`). Imports resolved from the outer `.venv/Lib/site-packages`:
  yadof `0.4.2` and yadof-benchmark `0.2.2`.
- The fresh explicit-program smoke workspace
  `temp/20260831_121405-stage6-benchmark-smoke` ran once in the authorized Windows
  host foreground and completed collected/valid `40/40/40/40` with zero issues,
  anomalies, or publication failures. Optimization took `9.0020409 s`; end-to-end
  benchmark elapsed time was about `12.345 s`.
- The single measured workspace
  `temp/20260831_121405-stage6-benchmark-measured` ran once in the authorized host
  foreground and completed collected/valid `2000/2000/2000/2000` with zero issues,
  anomalies, or publication failures. Optimization took `635.0217210 s`; cell
  runtime was `665.9498404 s`; end-to-end benchmark elapsed time was about
  `681.297 s`. Single-seed performance is descriptive, not an algorithm-quality
  gate.
- The measured workspace contains 20/20 strict generation metadata events, training
  events, checkpoint aliases/manifests/artifacts, and completion through generation
  19. Generation 0 used full-real warmup; generations 1--19 visibly executed the
  explicit PCA/SVD+GPSAF alpha/beta/exploration flow, NumPy reverse-row transform,
  common real evaluation, and synchronous fit. Training support grew from 100 to
  2,000 rows and every recording-failure counter remained zero.
- Smoke and measured program/helper bytes were identical and their expanded plans
  differed only by budget/path. Entry SHA-256 was
  `E626C62D90BF27FB7538C6C3EC8D234BCCEA1CEDD2C7F92A48FD97C2A8E1655A`, helper
  SHA-256 `A436D2DAD34B40886C7B39E38985049D455FE8212A3B3E5486A48B21C129AD5F`, expanded
  strategy digest `7017FE12845BACDDBCA496916E29B605C53639C77BD06C99A0248E1F9BE080A9`, program
  semantic signature `403FC869DE3AF65C51E5752262156C2159CD3B1B7138937498B62E25D12E7ECC`, and source
  fingerprint `2D4F4782D761390AB9A44CE94198D99862C4E3F5FFD224B5BCABEACD63E2B2F0`.
- Fast/local/distributed parity and ordering were covered through bounded common-API
  contracts; no real HTCondor or external simulator was launched.

## Automatic TODO check

Reliable recording was naturally in scope. Explicit scopes reuse the common
finalizer/writer, flush before commit, propagate recorder failure, and published all
2,000 measured rows. No consistency defect was found.

The bounded redundancy check confirmed the public predicted-row combiner replaced
the GPSAF-private merge and the program scopes do not duplicate existing campaign
owners. It also combined the duplicate `pathlib` imports in benchmark
`planning.py` and `storage.py` (one net line removed per file); the final 21-test
benchmark suite passed. The retained legacy path is a deliberate, inventoried
Stage 7/8 migration boundary, so deleting it in Stage 6 would violate the staged
contract; no other safe incidental deletion was proved.

The release-marker check found only the real v1 protocol identity and the explicit
Stage 7/8 migration/deletion marker, not an incidental edition label. The
component-configuration check found only program/factory keyword arguments plus
semantic identity and retained core campaign policy; no uppercase, hidden override,
fallback, or second settings entry remains. All four recurring automatic TODOs stay
active.

The repository entered Stage 6 clean at
`b68e9597d641c96775ef1fc72f5615587f3f0990`; there were no pre-existing user
changes to include.
