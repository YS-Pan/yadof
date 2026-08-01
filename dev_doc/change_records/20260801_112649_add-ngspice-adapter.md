# 2026-08-01 11:26 - Add Ngspice Adapter

## Context

- Circuit-optimization workflows needed a reusable adapter for changing ngspice
  parameters, running a simulation, and exporting simulator evidence as yadof
  rawData.
- The deployed machines expose the console executable through
  `YADOF_NGSPICE_EXE`; no Python binding or persistent simulator session was
  required.

## Change

- Added the self-contained packaged `ngspice_com.py` adapter with executable and
  netlist initialization, assigned/top-level parameter staging, one-process batch
  execution, timeout and diagnostic handling, ASCII rawfile parsing, and explicit
  real/imaginary/magnitude/phase/dB rawData export.
- Kept source netlists immutable. The adapter creates a candidate driver control
  block using `alterparam`, `reset`, one analysis command, `write`, and `quit`.
- Added generic mocked tests for adapter discovery, parameter/driver behavior,
  ngspice's zero-exit-code error reporting, real and complex rawfiles, and yadof
  rawData metadata. Added a live-machine smoke workspace outside the package
  repository for the installed adapter.
- Added user workflow guidance and updated adapter/test blueprints.

## Rationale

- A fresh batch subprocess matches yadof's existing job-level failure and process
  isolation, while avoiding shared-library callback state across concurrent
  candidates.
- Explicit float component conversion keeps complex AC results compatible with the
  surrogate's float training contract without guessing whether a task wants real,
  magnitude, phase, or dB data.
- Rejecting task-owned control blocks prevents duplicate runs and ambiguous plot
  selection while keeping analysis choice in task-owned workflow arguments.

## Impact

- `yadof task adapters` now lists `ngspice_com.py`, and `copy-adapter` can place it
  into an explicit workspace without changing the existing no-overwrite policy.
- Execute machines must provide the configured ngspice executable and any model
  files referenced by the self-contained task payload.
- Core evaluation, persistence, optimizer, and surrogate APIs are unchanged.

## Follow-Up

- Multi-plot or task-owned control-language experiments remain outside the initial
  adapter contract. Workflows needing them may contribute a separate explicit
  export contract after real task requirements are known.
