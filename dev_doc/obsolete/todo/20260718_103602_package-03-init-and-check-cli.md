# Package Step 3: Init And Check CLI

## Context

- This was step 3 of 10 and depended on step 2 being completed and archived.
- The workspace loaders needed a safe, repeatable way to create and diagnose a
  user-owned task directory.

## Goal

- Implement `yadof init [PATH]` and `yadof check [--workspace PATH]` around the
  packaged workspace, config, and task contracts.
- Provide a simulator- and vendor-neutral pure-Python starter workspace.

## Guidance

- `init` creates or confirms the minimum workspace: short `config.py`, user-owned
  task files under `job_template/`, and `.yadof/workspace.json` with workspace schema,
  yadof version, and template version. Runtime directories may be eager or lazy, but
  both paths must converge on one layout.
- The default template must be a minimal runnable generic task with no current
  model filename, concrete active-task variables/objectives, hard-coded physical
  result, simulator, vendor, or preselected adapter.
- Repeated init is idempotent: do not reset config, overwrite task files, delete
  history, or otherwise change user content. Default conflicts stop and list exact
  files. Define any explicit force/upgrade mode separately, with backup or a proof
  that a template remains unmodified.
- Validate generation in a temporary location and publish atomically enough that a
  partial failure cannot leave a workspace falsely appearing complete. Do not store
  machine-specific absolute installation paths in the marker.
- `check` validates workspace structure, marker/config, task imports,
  parameters/objectives, rawData contracts that can be checked statically, and the
  selected backend's read-only prerequisites. It may report missing external tools
  but must not install/repair Python, simulators, HTCondor, or cluster settings.
- Keep package self-tests distinct from a real task smoke test. `init` and `check`
  must not unexpectedly launch HFSS or any other expensive external program.

## Verification

- Test empty-directory init, explicit-path init, repeated init, partial/conflicting
  directories, user-modified files, non-interactive execution, and failure cleanup.
- From a wheel installed outside the repository, initialize and check the generic
  workspace and verify it contains no framework-side `api.py`, parameter class,
  rawData contract, optimizer, evaluator, recorder, or surrogate implementation.

## Documentation Rule

- Complete this phase's documentation work before archiving it: follow
  `dev_doc/README.md`, update every affected current architecture/blueprint/user
  document and terminology entry, and add this phase's own change record. Do not
  defer phase-specific documentation until step 10; step 10 only audits the set.

## Completion Rule

- Installed `yadof init` and `yadof check` satisfy the safe workspace contract and
  their help/errors are actionable. Archive this file, then execute step 4.

## Completion Note

- Completed and archived on 2026-07-18. The next step remains manual and was not
  executed as part of this task.
