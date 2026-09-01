# 4+1 development view

## Repository layout

```text
src/yadof/                 installed framework source
tests/                     generic installed-package verification
dev_doc/                   developer current-view, context, toDo, and history docs
user_doc/                  installed task-authoring and runtime workflow
admin_tool/
  admin_doc/               source-checkout administrator documentation
  htcondor_pool/           HTCondor configuration and diagnosis tool
  pychrono_runtime/        PyChrono provisioning and validation tools
examples/                  source-checkout reference workspaces
yadof-benchmark/           independent benchmark distribution, resources, docs/tests
temp/                      ignored scratch and generated source-checkout evidence
```

Framework code lives only under `src/yadof/`. Runtime workspaces normally live
outside package source. Root `dev_doc/` and `user_doc/` are authoritative sources
mapped into installed read-only resources. Administrator resources, examples, and
benchmark automation remain source-checkout concerns.

The independent benchmark distribution exposes one `benchmark.py` per
timestamped workspace. Initialization defaults to a packaged portable preset;
complete and blank are explicit. Complete expands to 18 cells at population 200,
25 generations, and a 7200-second timeout; its smoke profile changes only
generations to one. One workspace owns one direct execution; another execution
uses another workspace. Runtime provenance, expanded plan, mutable state, results,
reports, visualizations, and short `cells/cNNNN` directories all live directly
under that root. The runner uses the installed packages and records their versions
once before execution; it has no `runs/`, resume, numbered attempts, copied code
driver, or cross-workspace timing history.

Workflow freeze resolves omitted comparison budgets to seed 101, population 200,
and 50 generations, or 15 generations when any selected strategy declares a slow
surrogate. Explicit budgets remain unchanged. Structural evidence is integration
only; performance evidence is descriptive and a single performance seed is
exploratory.

Every short cell path is paired with a full baseline/strategy/seed display label
in spec, state, terminal, inspect, errors, and reports. Version-matched yadof
evaluation snapshots are the only source of completion percentage; elapsed
heartbeats remain non-completion evidence. Timeouts stop process trees and allow
independent FIFO work to continue under non-fail-fast policy while final status
remains non-successful.

Result publication validates same-baseline/same-seed pairing from baseline input
digest, planned/attempted budgets, and the complete ordered generation-0
normalized population. Planned, attempted, completed, and finite counts stay
distinct. Individual simulation failures and non-finite completions are reported
but can be tolerated when every planned attempt exists and finite contract-valid
metric evidence remains. Invalid evidence is retained and excluded from paired
aggregates.

Cell and simulation concurrency remain separate explicit controls. FIFO admission
waits for terminal aggregate publication; storage failure is fatal. Foreground
Rich presentation receives real child generation snapshots and command output
stays in per-cell logs unless explicitly streamed. Inspect is bounded/read-only
and estimates timing only from current-workspace generation trends and baseline
lower bounds.

On Windows detach opens a new console but does not change the process account.
AI-agent guidance therefore requires host execution under the interactive human
account; a sandbox-owned detached console is not presented as visible. The visible
detached console is persistent after benchmark success or failure so its final
terminal output remains reviewable; hidden detach remains automatic.

## Package dependency discipline

- Core modules communicate through public exports or narrow APIs.
- Stateful APIs accept explicit workspace context.
- `job_template` is task-neutral and owns parameter/rawData/current-cost gateways.
- Evaluation may depend on task and persistence contracts; optimization may
  coordinate evaluation, history, and surrogate components.
- Backend-neutral optimization primitives may depend on common strategy/history
  values but import the optional pymoo adapter only inside operations. Public state,
  pool, prediction, and selection DTOs never expose pymoo objects.
- Concrete optional numerical backends load only after their component is selected.
- Hierarchical-CAE training-data filtering is component-local: implementations live
  below `surrogate/hierarchical_cae/data_filtering/`, and its factory exposes one
  explicit mode selector that defaults to no filtering; the current opt-in
  implementation is named `frequency`.
- Core runtime never imports optional tools, administrator code, benchmark code, or
  concrete workspace projects.
- Distributed workflows use job-local modules and deliberately provisioned
  dependencies; they do not import yadof.

Code placement follows variability. Cross-task mechanisms belong in the package.
Simulator selection, model construction, measurements, objective policy, and other
task-variable behavior belong in the workspace. Complete optimization composition
belongs in the workspace submit-side definition.

## Documentation ownership

- `user_doc/` owns task-authoring, runtime use, adapter use, and execution-authority
  guidance.
- `dev_doc/architecture/` contains only high-level current system relationships,
  flows, persistence/recovery rules, and core invariants.
- `dev_doc/blueprints/` contains selectively read implementation and module
  contracts.
- `dev_doc/context/` preserves time-named cross-session experimental and working
  context. Every agent lists its filenames without opening them, then reads only a
  task-relevant document whose name indicates a likely match. Expiry is assessed
  only on explicit user instruction.
- `dev_doc/change_records/` preserves completed decisions and implementation
  history; `toDo/` preserves active future work.
- `dev_doc/obsolete/` is a source-partitioned inactive archive: `todo/` contains
  retired toDo handoffs, `context/` contains explicitly reviewed expired context
  documents, and `other/` contains all other obsolete developer material. Files do
  not remain directly under `obsolete/`.
- `admin_tool/admin_doc/` owns administrator deployment, configuration, and
  troubleshooting guidance, while sibling directories own executable tools.
- Integrated tool subtrees may own focused developer documentation that is linked
  rather than duplicated in root architecture.

Architecture must not become a copy of blueprints, user manuals, administrator
procedures, test matrices, experiment reports, release status, or implementation
history. Such detail is read only when the corresponding task requires it.

## Verification boundary

Generic tests import the installed distribution and use neutral temporary
workspaces, fake adapters, and mocked scheduler boundaries. Live simulator or pool
validation is an explicit integration activity governed by the user workflow's
cost/risk policy.

Package code, build configuration, resource mapping, or documentation-mechanism
changes use the installed-wheel acceptance workflow. Content-only documentation
changes use proportional encoding, path, link, diff, and discovery checks unless
they alter packaged documentation behavior.

## Change discipline

Current architecture and blueprints are updated in place. Historical change
records are append-only. Context documents preserve cross-session evidence without
becoming current-view contracts or task authorization; confirmed-expired documents
move to `obsolete/context/` only after an explicit user-requested review. Completed
or retired toDos move to `obsolete/todo/`, while obsolete material from every other
source moves to `obsolete/other/`. Task-authoring changes update user documentation;
administrator procedure changes update `admin_tool/admin_doc/`. Repository changes
preserve workspace evidence and unrelated worktree modifications.
