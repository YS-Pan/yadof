# Package Step 7: User Tools CLI

## Context

- This is step 7 of 10 and depends on step 6 being completed and archived.
- Normal user tools must become subcommands of the installed CLI; administrator
  environment and HTCondor-pool maintenance remain outside it.

## Goal

- Provide packaged, workspace-aware inspection, history, adapter/task, parameter
  extraction, and documentation commands.
- Retire the corresponding script-style user entry points without changing their
  useful framework behavior.

## Guidance

- Implement the established command families, allowing small consistent naming
  adjustments: `yadof view cost|time`, `yadof history clear`,
  `yadof task adapters|copy-adapter|extract-parameters`, and
  `yadof docs user|dev`.
- Move reusable behavior from `viewCost.py`, `viewTime.py`, `clear_history.py`, and
  parameter extraction/user tools into callable package functions. CLI handlers
  must not change the current directory, patch `sys.path`, or spawn another source
  script to reach business logic.
- Package optional example adapters as resources. List/copy only a user-selected
  adapter into a workspace; do not copy every adapter during init. Preserve support
  for one or more task-local adapters and do not make a simulator dependency core.
- History clearing and any other destructive command require explicit confirmation;
  provide a documented non-interactive confirmation flag and never let init/upgrade
  use it to erase runtime data.
- Keep help, actionable errors, exit codes, stdout/stderr, workspace selection, and
  non-interactive behavior consistent across the CLI. GUI opening is explicit;
  documentation commands default to printable location/content behavior.
- Do not expose administrator installation, dependency repair, HTCondor-pool
  configuration, or machine maintenance through the user CLI. User diagnostics may
  report missing external components only.

## Verification

- Test each subcommand from an installed wheel outside the repository, including
  explicit workspaces, absent/invalid inputs, destructive confirmation, non-GUI
  docs, adapter listing/copying, and simulator-independent operation.
- Verify removed script entry points have no remaining business logic or callers.

## Documentation Rule

- Complete this phase's documentation work before archiving it: follow
  `dev_doc/README.md`, update every affected current architecture/blueprint/user
  document and terminology entry, and add this phase's own change record. Do not
  defer phase-specific documentation until step 10; step 10 only audits the set.

## Completion Rule

- All normal non-run user tools have stable package APIs and CLI paths, while admin
  boundaries remain intact. Archive this file, then execute step 8.
