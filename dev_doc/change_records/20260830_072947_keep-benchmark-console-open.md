# 2026-08-30 07:29 - Keep Detached Benchmark Consoles Open

## Context

Windows `yadof-benchmark run --detach` launched the benchmark Python process
directly with `CREATE_NEW_CONSOLE`. The console therefore disappeared as soon as
the process completed, preventing the user from reviewing its final result or
error output.

## Change

- Visible detached launches now run the installed benchmark command inside a
  `-NoExit` Windows PowerShell host.
- The host prints the benchmark command's exit code and remains open until the
  user types `exit` or closes the window.
- Hidden detached launches remain direct, noninteractive processes that exit
  automatically.
- Detached launch receipts now state whether the window remains open after the
  run, and the benchmark patch version is `0.2.1`.

## Rationale

Keeping only the visible console host alive preserves the existing benchmark
execution, workspace, process-account, and hidden-launch boundaries while making
terminal completion evidence reviewable. It also avoids fragile `cmd.exe` nested
quoting for interpreters and workspace paths containing spaces.

## Impact

The Windows launcher, focused structural test, package version, benchmark user and
developer documentation, and repository architecture/blueprints were updated.
There is no workspace-format, result-format, simulator, or measured-execution
change.

## Follow-Up

None.
