# 2026-09-29 17:18 - Select pre-run smoke in the Condor GUI

## Context

The desktop controller exposed generation bounds but no way to choose whether
the next optimization launch should run a smoke job.

## Change

- Add a default-checked **启用 smoke job** checkbox beside the start/stop controls.
- Pass `--smoke-test` when checked and `--no-smoke-test` when unchecked through
  the existing `yadof run` command. The selection applies to that launch and
  overrides the workspace default without writing its configuration.
- Place action controls below numeric settings so the new option fits the
  window's existing minimum width.
- Document the GUI choice and cover both values from the start handler through
  the real CLI parser. Existing CLI tests cover smoke/config precedence.

## Boundary

The GUI continues to use the installed command and existing smoke implementation.
Evaluation, calibration, recording, and optimizer behavior are unchanged.
Verification uses the installed wheel and generic tests; no live simulator or
HTCondor job is needed.
