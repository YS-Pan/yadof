# File blueprint: src/yadof/_resources/adapters/chrono_com.py

## Intent

- Provide a self-contained adapter that runs a task-owned Project Chrono worker in
  a separately provisioned Python runtime without importing PyChrono into yadof or
  installing yadof into that runtime.

## Functionalities

- Resolve only an explicit absolute `YADOF_PYCHRONO_PYTHON` interpreter.
- Build bounded version-1 JSON requests from assigned parameters.
- Launch one child process group with unique scratch, a controlled environment,
  bounded diagnostics, timeout, and cancellation.
- On Windows, create a unique short temporary directory junction to the physical
  candidate scratch and use it for child `cwd`, request/result paths, and temp
  variables so launchability is independent of caller path depth.
- Validate result identity, direct paths, hashes, and no-pickle schema-compatible
  NPZ before returning memory rawData or atomically publishing file rawData.
- Expose `worker_main(simulate)` so task-owned `chrono_worker.py` validates its
  request before importing PyChrono and atomically writes a result manifest last.

## I/O format

- `run_pychrono()` accepts a task worker, assigned values, explicit scratch root,
  backend, and optional runtime/timeout/context values.
- Fast mode returns validated named memory payloads; local/distributed mode returns
  published direct NPZ paths plus bounded diagnostics.
- `PyChronoError` preserves one stable failure category, return code, diagnostic
  tails, truncation flags, and any validated child error manifest.
- Its `PyChronoSimulationError` subtype identifies explicit physical failures and
  time limits. The worker preserves `physical_failure` separately from task or
  protocol errors, allowing an oracle to reject programming faults visibly.

## Invariants

- No `import pychrono`, yadof import, Conda activation, PATH-based interpreter
  selection, shell launch, process-global environment/chdir mutation, pickle
  loading, objective calculation, or task-specific mechanics. Windows may prepend
  standard selected-prefix DLL directories only in the per-child environment copy.
- Child scratch never overlaps the external runtime prefix or final rawData; it is
  candidate-unique and reclaimed on every adapter-controlled outcome.
- A Windows launch junction is candidate-unique, contains no independent evidence,
  and is removed before the physical scratch; a failed junction setup may fall
  back only to an already launch-safe physical path.
- A nonzero exit, malformed manifest, escaping path, digest mismatch, or invalid
  NPZ never publishes partial evidence.
