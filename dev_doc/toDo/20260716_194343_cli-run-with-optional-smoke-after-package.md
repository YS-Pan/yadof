# Add The Optimization Run CLI After Package Conversion

## Context

- Execute this manual toDo only after `dev_doc/toDo/20260703 package.md` has been completed and archived.
- The current repository launcher is `start_optimization_from_config.py`, called by `start_optimization_aedtopt.cmd`.
- The current launcher reads effective config, optionally runs a no-timeout real smoke individual, aborts on an all-infinite smoke result, starts/resumes generations, prints progress, and reports recent job failures.
- Package conversion will replace repository-root launch scripts with the installed `yadof` command and a workspace context.

## Goal

- Make starting or resuming optimization a normal yadof CLI command, expected to be `yadof run` unless the package CLI establishes a clearer consistent name.
- Preserve the useful behavior of `start_optimization_from_config.py` through package APIs rather than retaining the root script as a compatibility wrapper.
- Make the pre-run real smoke test optional from both workspace config and an explicit CLI override.

## Guidance

- Use the packaged workspace/config loader and public optimize/evaluate APIs; do not depend on the repository root, `project.*` imports, or source-relative paths.
- Expose generation count, start generation, progress behavior, and fail-on-all-infinite behavior with the CLI's established option conventions.
- The default smoke choice should come from workspace config. Provide explicit opposite CLI flags, such as `--smoke-test` and `--no-smoke-test`, so automation can override it without editing config.
- A requested smoke test runs exactly one representative real individual through the selected backend with no generation or per-job timeout. Optimization starts only after a finite smoke result.
- When smoke is skipped, preserve the automatic resource/time contract: configured memory, disk, and per-job timeout baselines act as synthetic smoke measurements for generation zero.
- Keep package self-tests and real task smoke tests visibly distinct in help text and errors.
- Delete the repository-root Python/`.cmd` launch path when the package handoff says to remove old entry points; do not add a compatibility wrapper unless the user separately requests migration support.

## Completion Rule

- An installed `yadof run --workspace PATH ...` can start and resume an optimization outside the source repository.
- CLI help documents the config default and explicit smoke enable/disable overrides.
- Tests cover smoke enabled, smoke disabled, smoke failure before generation submission, direct start/resume options, and configured-baseline auto calibration when smoke is skipped.
- User/package documentation names the CLI as the normal launch path, and no root launch compatibility entry remains.
