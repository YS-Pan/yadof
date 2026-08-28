# Architecture index

The system is an installed, immutable `yadof` distribution plus one or more
explicit writable workspaces. There is no repository-local runtime namespace and
no implicit "current project". Every stateful operation is scoped to a workspace.
The normal user journey is AI-agent-first: a human user directs a locally installed
coding agent, which reads the installed, version-matched user documents and prepares
the selected workspace, while the CLI and Python APIs remain the underlying
execution surfaces.

The end-to-end invariant is:

```text
normalized variables
  -> assigned job-local parameters
  -> task workflow
  -> flat rawData/*.npz evidence
  -> current workspace calc_cost.py
  -> objective tuple
  -> recorded evidence / optimizer / surrogate
```

Core architectural goals are task-agnostic expensive evaluation, resumable
rawData-first history, fast/local/distributed evidence equivalence, per-individual
failure isolation, user-authoritative generation-boundary task correction, and safe
coexistence of multiple workspaces. A campaign does not freeze its initial
parameter ranges/levels, fixed-width objective/cost policy, or task code; the next
generation reconstructs derived state from the current workspace definition
without asking yadof to judge scientific equivalence. Parameter identity/count and
objective count remain stable in this contract. Fast evaluation uses reusable
isolated local workers and
memory-backed evidence without durable per-candidate job folders;
local/distributed retain prepared-job diagnostics. Costs and normalized history are
interpretations of evidence, not stored source truth.
Cross-task invariant behavior belongs in yadof; workspace workflow/cost files own
only behavior that varies with the selected optimization task.

The submit-side surrogate boundary also exposes a lightweight backend-neutral joint
rawData posterior protocol. One persistent sampler fixes function-draw identities
before candidate chunking; every draw reconstructs complete named rawData fields
identified by `(direct .npz basename, resolved values/data key)`. A thin projector
uses one frozen current-task `CostInterpreter` to stream those derived draws into a
joint objective tensor and invalid mask. Predicted rawData is discarded after
projection and never enters recorded evidence. Conditional INR now has a separate
opt-in finite-ensemble adapter whose identity does not alter the default
`conditional_inr()`/GPSAF checkpoint path. The independent
`posterior_assisted(..., acquisition=qnehvi(...))` strategy now reuses private
pymoo pool mechanics, freezes a real Pareto baseline, streams projected joint
samples, retains an explicit real-exploration quota, and hands every selected row
to the common real evaluator. BoTorch still owns qLogNEHVI numerics. Typed
performance/calibration/transferability readiness blocks every current posterior
component from exploitation, so explicit compositions remain full-real fallback
mechanisms rather than accepted optimizer-performance claims.

An independent experimental `hierarchical_cae()` component now provides full-grid
scalar/Conv1d/Conv2d codecs, global/optional-group/field-private latent state,
shared-codec predictor members, and the same joint rawData posterior boundary. A
generic versioned quality/regime policy carries task-owned explicit assessments or
declarative diagnostic/shape fallbacks into field weights, shared-token masks,
gated private residuals, and an uncalibrated applicability head. Original rawData
and current-cost interpretation remain unchanged. Gate 0 v5 found the first MVP
below its preregistered representation and clean-target leakage thresholds, so it
is retained for experiments but is not a production recommendation. A distinct
Gate 0 v6/v7 continuation completed a per-field, all-axis coordinate readout,
viewer adapter, and fixed offline path only as
`experimental / performance-not-accepted`; full-grid output remains authoritative.
Calibration requires a separate exact-state preregistration, and qNEHVI exploitation
remains blocked until performance and independent transferable calibration gates
pass. The new strategy plumbing does not weaken that boundary.

Integrated release is a separate fail-closed decision layer. Gate 0 v10 binds the
frozen v5 representation failure, v7 mechanism-only result, v8 non-transferable
calibration result, v9 full-real fallback evidence, the seven-arm formal matrix,
and the remaining threshold seals. Phase A is limited to experimental offline,
viewer/checkpoint, and separately preregistered diagnostic shadow work; Phase B's
public opt-in surface currently must fall back to full real search; Phase C remains
not recommended and cannot change the GPSAF + conditional-INR template default.
Structural benchmark success cannot open any scientific gate or authorize the
formal same-budget benchmark.

The packaged `chrono_com.py` adapter treats a dedicated Python/Conda runtime as an
external simulator installation. Its JSON/NPZ subprocess protocol, environment
isolation, scratch ownership, failure taxonomy, and backend-equivalent publication
rules are normative.

An optional read-only surrogate viewer is an installed `yadof.tools` leaf. It
consumes the same workspace records, current cost policy, and saved checkpoints
through an explicit GUI launch or terminal text/JSON reports, but it is outside
optimization execution and never publishes workspace state. Its detailed design
remains in the viewer subtree's own `dev_doc/`.

- [c4_context.md](c4_context.md): users and external systems
- [c4_container.md](c4_container.md): package/workspace/execution/persistence split
- [c4_component.md](c4_component.md): package module responsibilities
- [4plus1_logical_view.md](4plus1_logical_view.md)
- [4plus1_process_view.md](4plus1_process_view.md)
- [4plus1_development_view.md](4plus1_development_view.md)
- [4plus1_physical_view.md](4plus1_physical_view.md)
- [4plus1_scenarios.md](4plus1_scenarios.md)
- [pychrono_subprocess_contract.md](pychrono_subprocess_contract.md): normative
  task-owned PyChrono child-process boundary

For implementation-level current state, continue with
`../blueprints/10_modules/`. Historical decisions live in `../change_records/` and
must not be treated as the current contract when architecture or blueprints differ.

## 2026-08-28 structural boundary

Hierarchical CAE is separated into networks, objectives, training, inference, data
adaptation, state repository, projection, checkpoint policy, scheduler, and
posterior adapter. Conditional-INR and CAE share only atomic artifact, bounded
training-event, and deterministic finite-member primitives. The source-checkout
benchmark uses a small facade plus run-owned execution snapshots; hashes are
provenance only, never resume or historical-completion locks.
