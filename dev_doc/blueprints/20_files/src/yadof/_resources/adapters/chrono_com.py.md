# File blueprint: src/yadof/_resources/adapters/chrono_com.py

## Intent

- Provide a self-contained adapter that runs a task-owned Project Chrono worker in
  a separately provisioned Python runtime without importing PyChrono into yadof or
  installing yadof into that runtime.

## Functionalities

- Resolve only an explicit absolute `YADOF_PYCHRONO_PYTHON` interpreter.
- `PyChronoSession` launches one external interpreter lazily, serializes requests,
  continuously drains bounded stderr, and receives one bounded binary response at
  a time. `resident_worker_main(simulate)` loads the native module once but calls
  the task afresh with isolated candidate scratch on every request.
- The resident protocol sends bounded versioned JSON headers and complete numeric
  arrays with declared name/dtype/shape/byte count. Validate schema, finiteness and
  framing before returning memory rawData. It does not serialize NPZ between calls.
- Send the owned session directory in the initial frame. When a long Windows TEMP
  would stall a venv launcher, bootstrap with a short temporary root, then switch
  the child to owned candidate scratch. The launch-directory bound is 258 UTF-16
  units, reserving the appended separator and NUL; 259-unit paths already need
  the short bootstrap. No resident junction is created.
- Session close drains/terminates/reaps the child, closes pipes/readers and removes
  scratch. Physical errors retain the child; protocol errors, crash and timeout
  close it so later evaluation starts a fresh process.
- Retain the following independent one-shot JSON/NPZ API for prepared consumers:
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
- `PyChronoSession.evaluate_rawdata(parameters, timeout=..., evaluation_id=..., backend=...)` returns full named rawData
  from its resident child. The owning task session must call `close()`.
- Fast mode returns validated named memory payloads; local/distributed mode returns
  published direct NPZ paths plus bounded diagnostics.
- `PyChronoError` preserves one stable failure category, return code, diagnostic
  tails, truncation flags, and any validated child error manifest.
- Its `PyChronoSimulationError` subtype identifies explicit physical failures and
  time limits. The worker preserves `physical_failure` separately from task or
  protocol errors, allowing an oracle to reject programming faults visibly.

## Invariants

- No `import pychrono`, yadof import, Conda activation, PATH-based interpreter
  selection, shell launch, caller-process environment/chdir mutation, pickle
  loading, objective calculation, or task-specific mechanics. Windows may prepend
  standard selected-prefix DLL directories only in the per-child environment copy.
- Child scratch never overlaps the external runtime prefix or final rawData; it is
  session/candidate-owned and reclaimed on every adapter-controlled outcome.
- Resident transport reuses interpreter/native libraries only. No candidate result
  cache or physical-state warm start is implied; each task callback rebuilds the
  physical system and all memory arrays belong to the current candidate.
- A Windows launch junction is candidate-unique, contains no independent evidence,
  and is removed before the physical scratch; a failed junction setup may fall
  back only to an already launch-safe physical path.
- A nonzero exit, malformed manifest, escaping path, digest mismatch, or invalid
  NPZ never publishes partial evidence.
