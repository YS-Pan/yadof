# 4+1 development view

## Repository layout

```text
src/yadof/                 installed framework source
tests/                     generic installed-package verification
dev_doc/                   developer current-view, blueprint, toDo, and history docs
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

The independent benchmark distribution exposes one editable workflow program per
benchmark workspace. Its baseline collections use exact semantic
`provider/task` source paths and freeze content only when a run is created; source
directory names do not carry provenance digests. Human-visible workspace, run, and
workspace output-index names use local `YYYYMMDD_HHMMSS` prefixes, while internal
cell execution paths remain compact digests. Each collected cell owns one cost
plot and one uniformly invoked baseline-domain postprocess result below its single
authoritative run root; workspace top-level output roots contain run indexes. Its
CLI owns Rich presentation on the foreground thread, receives real child
generation snapshots through a queue, and keeps active-cell/global rows in that
order. Windows detach opens a normal console and returns PID/run/log/inspect
details; hidden detach is explicit, while Python calls stay synchronous and
window-neutral. Planning/check output is bounded unless complete JSON is explicit;
child stdout/stderr stays in per-command logs unless explicit streaming is
selected. Read-only inspect bounds anomalies and exposes validity, comparison
readiness, next steps, activity, and ETA. ETA freezes bounded earlier same-arm
timing records, distinguishes exact from compatible task/resource/host/config
matches, excludes cross-arm point estimates, and models a non-negative
generation-duration trend once enough timestamped phases exist. Every benchmark
workflow also freezes one explicit evidence class. Structural package/CLI tests,
recovery fault injection, real adapter smoke, and bounded canaries prove engineering
behavior only and cannot support algorithm performance conclusions. Performance
campaigns remain descriptive and follow bounded plan/check, adapter smoke, and a
same-path structural canary before separately authorized full execution. The class
is carried through plan, cells, reports, indexes, and inspect rather than inferred
from budget.

Benchmark result publication validates same-baseline/same-seed pairing from the
frozen task snapshot, matching planned/attempted budgets, and the complete ordered
generation-0 normalized-population fingerprint. It publishes
planned/attempted/completed/finite counts plus final HV and
attempted-evaluation-aligned HV trajectory/AUC. Invalid or incomplete cell evidence
is preserved but excluded explicitly from cross-seed descriptive aggregates;
failures are validity facts rather than a performance score. Surrogate-training
duration is reported separately from optimizer wall time and may use only an
explicit external representative expensive-generation reference.

Benchmark result publication validates same-baseline/same-seed pairing from the
frozen task snapshot, matching planned/attempted budgets, and the complete ordered
generation-0 normalized-population fingerprint. It publishes
planned/attempted/completed/finite counts plus final HV and
attempted-evaluation-aligned HV trajectory/AUC. Invalid or incomplete cell evidence
is preserved but excluded explicitly from cross-seed descriptive aggregates;
failures are validity facts rather than a performance score. Surrogate-training
duration is reported separately from optimizer wall time and may use only an
explicit external representative expensive-generation reference.

## Package dependency discipline

- Core modules communicate through public exports or narrow APIs.
- Stateful APIs accept explicit workspace context.
- `job_template` is task-neutral and owns parameter/rawData/current-cost gateways.
- Evaluation may depend on task and persistence contracts; optimization may
  coordinate evaluation, history, and surrogate components.
- Concrete optional numerical backends load only after their component is selected.
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
- `dev_doc/change_records/` preserves completed decisions and implementation
  history; `toDo/` preserves active future work.
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
records are append-only. Task-authoring changes update user documentation;
administrator procedure changes update `admin_tool/admin_doc/`. Repository changes
preserve workspace evidence and unrelated worktree modifications.
