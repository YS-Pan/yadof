# Define the PyChrono Subprocess Contract

## Context

- yadof can coordinate many external tools, including AEDT, ngspice, and future
  adapters. It must remain in its own Python environment rather than being moved
  into a simulator-specific environment.
- PyChrono will run under the dedicated interpreter referenced by
  `YADOF_PYCHRONO_PYTHON`. The yadof parent and PyChrono worker are separate
  operating-system processes with separate Python runtimes.
- Treat the complete Conda environment as an external simulator installation. The
  parent-side adapter must not import `pychrono`, and the child must not import
  yadof.
- This contract should be designed and tested with a fake child interpreter before
  the real shared runtime is required.

## Goal

- Specify a small, stable, backend-neutral protocol for launching a task-owned
  PyChrono worker from yadof.
- Preserve yadof's existing evidence chain: assigned parameters lead to simulator
  output in rawData, and only the task's `calc_cost.py` derives optimization costs.
- Keep process, environment, diagnostics, timeout, scratch, and concurrency
  behavior explicit enough for local, fast, and distributed execution.

## Guidance

- Resolve the child interpreter from an explicit configuration value, initially
  the machine-level `YADOF_PYCHRONO_PYTHON`. Validate that it is an absolute path to
  an executable file. Do not search PATH, activate Conda, or silently fall back to
  the parent interpreter.
- The parent-side adapter should serialize a versioned JSON request containing
  normalized/assigned parameters and relevant task context. Do not use pickle or
  pass live Python objects across the process boundary.
- A task-owned child entry point, for example `chrono_worker.py`, should import
  PyChrono, construct and run the mechanical model, and emit schema-compatible
  `.npz` rawData plus a small JSON result/diagnostic manifest. Costs stay outside
  the child and continue to be calculated by yadof from recorded evidence.
- Launch the child by absolute interpreter path without environment activation.
  Build a controlled child environment that removes inherited `PYTHONPATH`, sets
  `PYTHONNOUSERSITE=1` and `PYTHONDONTWRITEBYTECODE=1`, and directs `TEMP`/`TMP` and
  the working directory to a candidate-specific scratch directory.
- Specify argument quoting, request and result schemas, protocol versioning,
  encoding, numeric/array constraints, allowed output paths, success/failure exit
  codes, stdout/stderr capture, diagnostic size limits, timeouts, cancellation, and
  process-tree termination.
- Give every evaluation its own request, scratch, and output locations. The shared
  Conda prefix is read-only and must never hold task data, caches, logs, or mutable
  state. Multiple evaluations may use the same interpreter concurrently only when
  their workspaces remain isolated.
- Make missing runtime configuration, missing child entry point, malformed JSON,
  missing/invalid rawData, nonzero exit, crash, and timeout distinguishable to the
  caller. Preserve useful diagnostics without treating partial output as valid
  evidence.
- Define how fast mode can load validated `.npz` output into memory before scratch
  cleanup while local and distributed modes retain the same logical rawData
  contract.
- Test the protocol with controlled fake workers covering success, large stderr,
  invalid output, inherited-environment contamination, timeout, crash, and child
  processes. These tests must not require Miniforge or PyChrono.

## Completion Rule

- The subprocess protocol, schemas, environment policy, failure taxonomy, timeout
  behavior, and scratch ownership are documented in yadof's canonical developer
  documentation.
- Automated tests prove the contract with fake child interpreters without importing
  PyChrono in the yadof process or importing yadof in the child.
- The design supports equivalent rawData ingestion in local, fast, and distributed
  execution and does not require Conda activation or PATH mutation.
