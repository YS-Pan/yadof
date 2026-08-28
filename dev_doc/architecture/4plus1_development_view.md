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
benchmark_automation/      source-checkout comparison tool and its local docs/tests
temp/                      ignored scratch and generated source-checkout evidence
```

Framework code lives only under `src/yadof/`. Runtime workspaces normally live
outside package source. Root `dev_doc/` and `user_doc/` are authoritative sources
mapped into installed read-only resources. Administrator resources, examples, and
benchmark automation remain source-checkout concerns.

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
