# Package Step 4: Job Preparation And Local Evaluation

## Context

- This is step 4 of 10 and depends on step 3 being completed and archived.
- A prepared job must combine stable package worker support with one workspace's
  mutable task payload without writing to or importing runtime state from the
  installed source tree.

## Goal

- Migrate job preparation and the local evaluation backend to the packaged
  workspace/context model.
- Run the initialized pure-Python task through the real local prepare/workflow/result
  path while retaining current failure, timeout, and rawData boundaries.
- Add the standalone `yadof smoke-test [--workspace PATH] [--mode local]` user path,
  distinct from package self-tests and from the later optional pre-run smoke.

## Guidance

- Move `evaluate_manager` local/job-preparation responsibilities into `yadof.*` and
  update cross-module calls to package public APIs or internal relative imports.
- Define explicit composition rules for package worker support plus workspace task
  files/resources. Preserve multiple task-local adapters and arbitrary task assets,
  exclusion of submit-side `calc_cost.py`, and the rule that workflows produce only
  rawData and metadata, never authoritative `cost.json`.
- Detect collisions between package-reserved worker filenames and workspace task
  filenames and report understandable errors; never silently overwrite.
- Materialize the assigned parameter snapshot and preserve current dynamic reload,
  definition-only static hashing, workflow lifecycle metadata, timeout, and
  per-individual failure-isolation behavior.
- Record yadof version, workspace identity, task static hash, and an effective config
  summary in prepared-job metadata. Copy only the effective worker-side config
  information required for diagnosis/execution, not the package's full config source
  into the workspace.
- Keep job folders under the workspace and return the existing result/cost tuple
  shapes. Do not retain source-root path or `project.*` import assumptions.
- Make standalone smoke execution explicit and safe: it evaluates exactly one
  deterministic representative individual in the selected workspace with no
  timeout. A generic initialized task may run directly; invoking an external or
  expensive task must require an explicit real-task choice or equally clear user
  intent, and help text must say what can launch.

## Verification

- Test prepared-job contents, reserved-name conflicts, static hash behavior,
  assigned values, metadata provenance, no `calc_cost.py`/`cost.json`, arbitrary
  task resources, and multiple adapters.
- Test successful, failed, and timed-out local pure-Python jobs from an installed
  wheel outside the repository with a read-only package directory.
- Test standalone smoke help, safe selection behavior, exactly-one-individual
  execution, success/failure reporting, and the distinction from package self-tests.

## Documentation Rule

- Complete this phase's documentation work before archiving it: follow
  `dev_doc/README.md`, update every affected current architecture/blueprint/user
  document and terminology entry, and add this phase's own change record. Do not
  defer phase-specific documentation until step 10; step 10 only audits the set.

## Completion Rule

- The local prepare/evaluate contract works entirely from installed framework plus
  explicit workspace inputs. Archive this file, then execute step 5.
