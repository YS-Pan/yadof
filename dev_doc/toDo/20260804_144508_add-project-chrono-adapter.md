# Add the Project Chrono Adapter

## Context

- Complete the PyChrono subprocess-contract toDo before implementing this adapter.
- The adapter is the yadof-side launcher for an external simulator runtime. It is
  not a Python wrapper that imports PyChrono into yadof's process.
- Mechanical models, bodies, loads, solver settings, measurements, and cost
  calculations are task-specific workspace content and must not be hard-coded into
  the yadof package.

## Goal

- Add an officially documented Project Chrono adapter resource to yadof.
- Let a workspace provide a task-owned child simulation script and use a configured
  PyChrono interpreter to produce normal yadof rawData.
- Make the adapter discoverable through the same CLI/resource workflow used by
  other adapters without adding PyChrono as a yadof dependency or optional extra.

## Guidance

- Add `src/yadof/_resources/adapters/chrono_com.py` as a parent-side adapter. It
  must contain no `import pychrono` and no dependency on Conda's Python packages.
- Keep the public adapter surface small: interpreter resolution, request creation,
  child launch, timeout/cancellation, result validation, and diagnostic reporting.
  Reuse existing process and rawData abstractions where they satisfy the documented
  subprocess contract.
- Supply or document a task-owned `chrono_worker.py` template that is copied into a
  workspace and executed by the PyChrono interpreter. It may import PyChrono, but it
  must not import yadof.
- Do not install yadof into the PyChrono environment, add `pychrono` to yadof's
  dependencies/extras, invoke `conda activate`, modify PATH, or assume a particular
  user profile.
- Validate files and result schemas at the trust boundary. Reject paths that escape
  the assigned candidate workspace and never deserialize pickle from the child.
- Add focused tests using fake external interpreters and fake worker scripts. Test
  paths containing spaces, runtime-not-configured behavior, version/protocol
  mismatch, malformed output, nonzero exit, timeout, and concurrent isolated jobs.
- Confirm the adapter resource is included in the built wheel and can be listed and
  copied by the CLI. Update user documentation, architecture, relevant blueprints,
  terminology, examples, and the change record as required by the documentation
  contract.
- Keep actual Project Chrono mechanics validation in the separate real-integration
  toDo so the package test suite does not depend on a machine-global installation.

## Completion Rule

- A built and reinstalled yadof wheel exposes and copies the Project Chrono adapter
  through the documented resource workflow.
- The yadof process can launch a compatible fake external runtime and ingest its
  valid rawData while all specified failure cases are covered by automated tests.
- Neither yadof's dependency metadata nor its running process requires PyChrono or
  Conda, and the child runtime does not require yadof.
- Canonical developer/user documentation explains setup, configuration, process
  separation, task ownership, and failure diagnostics.
