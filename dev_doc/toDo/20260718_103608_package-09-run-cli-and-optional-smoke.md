# Package Step 9: Run CLI And Optional Smoke Test

## Context

- This is step 9 of 10 and depends on steps 1 through 8 being completed and
  archived. It incorporates all requirements from
  `dev_doc/obsolete/20260716_194343_cli-run-with-optional-smoke-after-package.md`.
- Package/runtime conversion is now sufficient to replace the repository-root
  launcher; the final artifact and documentation audit remains step 10.

## Goal

- Make `yadof run` the normal installed command for starting or resuming
  optimization outside the source repository.
- Preserve the useful launcher behavior through package APIs and support explicit
  enable/disable overrides for the optional pre-run real smoke individual.

## Guidance

- Use only the packaged workspace/config loader and public optimize/evaluate APIs.
  Expose generation count, starting generation, evaluation mode where appropriate,
  progress behavior, and fail-on-all-infinite behavior using established CLI
  conventions and non-mutating overrides.
- Take the default smoke choice from workspace config. Provide opposite explicit
  flags such as `--smoke-test` and `--no-smoke-test`, with clear precedence shown in
  help/effective config.
- A requested smoke test runs exactly one deterministic representative real task
  individual (the current policy uses the parameter-space midpoint) through the
  selected backend with neither generation nor per-job timeout.
  Optimization starts only after at least one finite smoke cost; on failure, stop
  before generation submission and report actionable recent job diagnostics.
- When smoke is skipped, configured memory, disk, and per-job timeout baselines act
  as synthetic smoke measurements for generation zero under the current automatic
  calibration policy.
- Clearly distinguish package self-tests, generic local example checks, and a real
  task smoke that may invoke expensive external software.
- Delete `start_optimization_from_config.py`, `start_optimization_aedtopt.cmd`, and
  the repository-root launch path once `yadof run` is verified. Do not leave a
  compatibility wrapper or duplicate business logic.

## Verification

- From an installed wheel outside the repository, test direct start and resume,
  config-default smoke behavior, both CLI smoke overrides, smoke success/failure,
  no generation on smoke failure, progress/fail-on-all-infinite options, recent
  failure reporting, and configured-baseline calibration when smoke is skipped.
- Verify help text and exit/stdout/stderr behavior, and confirm no root launch entry
  or source-relative import remains.

## Documentation Rule

- Complete this phase's documentation work before archiving it: follow
  `dev_doc/README.md`, update every affected current architecture/blueprint/user
  document and terminology entry, and add this phase's own change record. Do not
  defer phase-specific documentation until step 10; step 10 only audits the set.

## Completion Rule

- Installed `yadof run --workspace PATH ...` fully replaces the old launcher with
  optional smoke semantics and tests. Archive this file, then execute step 10.
