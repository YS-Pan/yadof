# Package Step 8: Distributed Worker Execution

## Context

- This is step 8 of 10 and depends on step 7 being completed and archived.
- Local execution and persistence already use the installed package plus workspace;
  distributed jobs must now preserve the same contract without requiring a shared
  writable site-packages directory.

## Goal

- Migrate the HTCondor backend and worker bootstrap/payload rules to packaged,
  workspace-aware execution.
- Keep resource, timeout, retry, slot-user, metadata, and failure contracts intact.

## Guidance

- Move distributed evaluator code into `yadof.*` and create self-contained jobs
  from package-provided worker support plus workspace task payload. Define how a
  worker obtains compatible framework support; if an installed package is expected,
  detect missing/incompatible versions early and return a diagnostic job failure.
- Do not write to package resources or require shared writable site-packages. Record
  and return yadof/workspace/task versions plus the effective config needed to
  explain execution.
- Preserve local/distributed parity for prepared jobs, rawData, lifecycle metadata,
  recording, cost tuple shapes, and failure isolation.
- Preserve the current concrete memory/disk request, generation calibration,
  yadof-managed bounded resource retry, scheduler execution-limit, smoke/no-timeout,
  whole-generation deadline, final ClassAd, and timeout semantics unless a separately
  triggered current toDo changes them.
- Keep Windows slot-user deployment and the administrator/user boundary. The CLI and
  runtime may diagnose HTCondor but must not install, repair, or configure the pool.
- Extend the standalone `yadof smoke-test` command to `--mode distributed` while
  preserving its no-generation/no-per-job-timeout and exactly-one-individual
  contract.

## Verification

- Extend mocked submit-file/runner tests for packaged paths, worker bootstrap,
  version mismatch, missing worker dependency, resource retry/calibration, timeout,
  output return, and metadata provenance.
- Test the installed distributed smoke CLI wiring and unlimited-smoke submit
  contract with mocked HTCondor execution.
- Run an explicit real-pool smoke only when the environment and user request permit;
  default package tests must remain independent of HTCondor and simulators.

## Documentation Rule

- Complete this phase's documentation work before archiving it: follow
  `dev_doc/README.md`, update every affected current architecture/blueprint/user
  document and terminology entry, and add this phase's own change record. Do not
  defer phase-specific documentation until step 10; step 10 only audits the set.

## Completion Rule

- Distributed execution uses the same workspace contract as local execution and
  failures are diagnosable without package writes. Archive this file, then execute
  step 9.
