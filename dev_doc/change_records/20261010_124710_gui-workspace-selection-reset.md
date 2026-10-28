# 2026-10-10 12:47 - GUI workspace selection and confirmed full reset

## Context

The user requested an explicit workspace directory-selection button and a
confirmed reset that clears jobs, metadata, recorded data and optional surrogate
training records so optimization can restart from zero.

## Change

- The existing directory chooser is exposed as **设定 workspace…**. Cancellation
  keeps the selected path. **清空 workspace** previews the selected workspace and
  effective configured deletion paths and uses a default-No confirmation.
- The GUI invokes the existing history cleanup mechanism on a worker with the
  explicit new `all_recorded_data=True` option. That option removes the entire
  recorded-data root, including extra entries, then recreates it empty. Default
  API and CLI history cleanup still retain extra recorded-data entries.
- Cleanup removes all jobs, recorded metadata and training events, all retained
  checkpoint namespaces and optimization resume state. It preserves configuration,
  task sources/assets, marker and general tool outputs. Successful GUI cleanup
  resets the start generation to zero and clears progress. Failure restores
  controls, reports possible partial deletion and does not reset the generation.
- Workspace controls and launching are disabled during process startup/running,
  stopping, views and cleanup. Views are serialized against cleanup; worker
  completion updates Tk state through the existing event queue.
- Full reset validates all deletion targets before mutation, rejects external
  targets and protects configuration, task roots, workspace marker and campaign
  lock. Windows junction entries are identified through their reparse tag, including
  on Python 3.11, and removed without traversing their destination.

## Rationale and reliability

Reusing history cleanup keeps task ownership, optional surrogate deactivation and
configured paths in one mechanism. Full recorded-data deletion is an explicit
opt-in because the existing CLI deliberately preserves unrelated entries there.

The bounded reliable-recording automatic check exposed that cleanup previously
acquired and released the campaign lock only as an inactivity probe. A campaign
could start after that probe and race deletion. Cleanup now holds the same lock
through deactivation, deletion and empty-directory recreation, releasing it on both
success and failure. This correction applies to both default and full cleanup.

## Impact and validation

The implementation remains under `src/yadof/tools/`; source-checkout launchers are
unchanged. User guidance, the tools/history/tests blueprints and the component
architecture describe the full reset and lock boundary. Existing checkout edits
were retained; this change does not commit the working tree.

- Built a regular wheel with the installed hatchling backend (`--no-isolation`),
  force-reinstalled without dependencies and verified yadof 0.6.0 imports from
  `D:/.venv/Lib/site-packages/yadof`.
- Focused GUI/history/CLI/recording tests: **70 passed**. Fixtures use disposable
  workspaces under ignored `temp/`, no live Condor jobs or simulator campaign.
- Initial full installed-package regression: 613 passed, 7 skipped, 5 failed solely
  because the existing posterior strategy tests require the optional `botorch`
  dependency. Installed the project-declared compatible BoTorch 0.18.1 and its
  dependencies in the development venv; all 14 posterior strategy tests then passed.
  Final full installed-package regression with the optional backend available:
  **625 passed**, with two existing sklearn Gaussian-process convergence warnings.
- Reviewed the changed source and documentation and checked added-line whitespace
  against Git index blobs with an ignored scratch helper. Git is unavailable on
  this host, so `git diff --check` itself could not be run.

No existing user workspace was cleared during implementation or validation.
