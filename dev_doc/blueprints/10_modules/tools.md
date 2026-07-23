# Module blueprint: tools

## Boundary

`yadof.tools` is optional, user-launched, workspace-explicit functionality. Core
optimization/evaluation never imports it. Tools read public task/recorded APIs,
present diagnostics, and write only user-requested workspace tool output or
confirmed task edits. Pool/system administration remains under `admin_tool/`.

## Views and history

Cost/time views derive current values from public history/task APIs, support selected
records/objectives, and write relative outputs below the configured tool directory.
They do not mutate durable evidence. History clear requires explicit confirmation,
resolves and validates exact workspace-owned targets, and avoids package or unrelated
paths.

## Task utilities

Task tools list/copy packaged adapters without overwriting user edits and extract
HFSS parameters with backup and confirmation.
The CLI exposes software-specific extraction below `yadof task hfss`, not as a
generic task action that future software tools would have to overload.
HFSS extraction directly recognizes both standalone Optimetrics variable records
and optimization attributes embedded in `VariableProp(...)`; it uses `Min`/`Max`
for continuous variables and discrete `Level` values before attempting a PyAEDT
fallback.

## Invariants

- Every command takes an explicit workspace and respects effective output paths.
- No concrete project/design/objective assumptions enter generic framework tools.
- Potentially destructive history/task edits are previewed/confirmed and recoverable
  through backup where applicable.
- New simulator-specific actions get their own software namespace.
