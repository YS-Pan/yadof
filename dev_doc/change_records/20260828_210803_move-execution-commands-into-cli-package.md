# 2026-08-28 21:08 - Move Execution Commands Into CLI Package

## Context

- The installed `run` implementation and standalone-smoke safety assessment lived
  as direct files under `src/yadof/` even though their only consumer was the CLI.
- `cli/main.py` also contained the complete standalone-smoke handler, mixing parser
  routing with command-specific execution presentation.

## Change

- Moved `run_command.py` to `cli/run.py` and renamed its handler to
  `run_command()`.
- Moved `smoke_test.py` to `cli/smoke.py` and colocated the exact-starter safety
  assessment with the standalone-smoke command handler.
- Reduced `cli/main.py` to parser ownership plus tiny lazy dispatchers so help,
  version, and documentation commands still avoid importing optimization and
  evaluation runtime dependencies.
- Updated run-command tests, wheel membership assertions, and the project/CLI
  blueprints for the new physical ownership.

## Rationale

- Both implementations translate parsed CLI namespaces into terminal output and
  exit codes; placing them in `yadof.cli` matches their responsibility and removes
  misleading root-level framework modules.
- Retaining narrow lazy dispatch preserves the lightweight command surface without
  adding a compatibility module or a generic dispatch abstraction.

## Impact

- The supported `yadof smoke-test` and `yadof run` commands and their output/error
  behavior are unchanged.
- Internal imports that need the command modules now use `yadof.cli.smoke` and
  `yadof.cli.run`. The former root module paths were not package-root exports and
  receive no compatibility aliases.
- Core evaluation, optimization, workspace, task, persistence, and user-workflow
  contracts are unchanged, so no user-documentation or architecture update is
  required.

## Validation

- Parsed all changed Python sources and tests without writing bytecode.
- Built `dist/yadof-0.4.2-py3-none-any.whl`, force-reinstalled it into the outer
  `.venv`, and verified imports resolve below `.venv/Lib/site-packages/yadof`.
- Verified parser construction does not import `yadof.cli.run`,
  `yadof.cli.smoke`, `yadof.optimize`, or `yadof.evaluate_manager`.
- Focused run/smoke tests: 29 passed. Focused clean-artifact test: 1 passed.
  Final installed-wheel suite: 368 passed.
- An initial source-tree `compileall` attempt could not write to the pre-existing
  mixed-ACL `src/yadof/cli/__pycache__`; no cache, ACL, or ownership change was
  made, and the non-writing syntax plus installed-wheel acceptance checks passed.

## Follow-Up

- None.
