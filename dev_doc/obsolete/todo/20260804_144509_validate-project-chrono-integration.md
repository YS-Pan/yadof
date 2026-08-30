# Validate the Project Chrono Integration

## Context

- Execute this manual toDo only after both the shared PyChrono runtime and the
  yadof Project Chrono adapter have been completed.
- A real integration run changes task workspaces and consumes simulator resources;
  obtain explicit user authorization and a named validation workspace before
  starting it.
- Package tests with fake children establish protocol behavior, but they cannot
  prove that the selected PyChrono build, Windows runtime, model script, and
  multi-process execution work together.

## Goal

- Validate the full yadof-to-PyChrono boundary using a small deterministic mechanics
  problem whose expected behavior is independently checkable.
- Demonstrate that yadof and PyChrono use separate interpreters and processes and
  that the shared PyChrono environment remains clean and immutable.
- Compare local, fast, and, when an appropriate execution host is available,
  distributed behavior using the same logical rawData contract.

## Guidance

- Create the example in a user-approved external task workspace, not inside the
  yadof source package. Keep model construction and measurements in the task's
  child script and costs in `calc_cost.py`.
- Record the absolute executable paths, process IDs, Python versions, PyChrono
  version, protocol version, and package manifest used for the run. Confirm the
  parent resolves to yadof's environment and the child resolves to
  `C:\ProgramData\Miniforge3\envs\pychrono-10\python.exe`.
- Use a simple deterministic rigid-body or oscillator case with analytically or
  independently checkable displacement/velocity/energy behavior. Set explicit
  tolerances rather than comparing floating-point output byte-for-byte.
- Run one evaluation first, then bounded concurrent evaluations with separate
  candidate scratch directories. Exercise success, invalid task input, child
  failure, and timeout/cancellation without writing into the shared prefix.
- Compare the named arrays, shapes, units, metadata, and calculated costs produced
  by local and fast modes. Test distributed execution only after confirming that
  the execute identity can read/execute the shared prefix and access the configured
  absolute path; do not assume a path on a different host points to the same
  installation.
- Check that inherited `PYTHONPATH=C:\condor\lib\python;C:\condor\bin` is absent in
  the child, user-site packages are disabled, and imports resolve only from the
  pinned environment and task script.
- Re-list the PyChrono environment and inspect the shared-prefix timestamps/ACLs
  after validation. The run must not have installed packages, created caches, or
  changed files in the shared runtime.
- Retain request/result manifests, relevant stdout/stderr, rawData, expected-value
  comparisons, and environment provenance as validation evidence while avoiding
  machine-specific secrets.

## Completion Rule

- The deterministic real mechanics case passes its stated numeric tolerances in the
  supported yadof execution modes.
- Evidence proves separate parent and child interpreters/processes, controlled
  child environment variables, isolated scratch directories, correct rawData and
  cost provenance, bounded concurrency, and useful failure diagnostics.
- The shared PyChrono prefix and its package manifest are unchanged by all runs, and
  yadof is still absent from that environment.
- Any host-specific limitations, including distributed-host runtime provisioning,
  are documented rather than hidden behind PATH or environment fallbacks.
