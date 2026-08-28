# Default to a visible benchmark process window

## Context

The benchmark CLI and its runtime driver did not hide their processes, but an AI
agent could still detach a long run through an external hidden Windows launcher.
That caller-side choice made progress invisible even though the benchmark emitted
live events and retained durable evidence. The user requires the same visible
process-window default for human and AI-initiated measured runs.

## Change

- Made a visible terminal the documented default for measured `run` and `resume`
  operations.
- Added a Windows `Start-Process -WindowStyle Normal` example for an AI agent that
  must detach a long run, including PID reporting.
- Restricted hidden launch flags and default output redirection to cases where the
  user explicitly requests them.
- Recorded that process-window ownership belongs to the caller boundary; the
  synchronous Python API remains window-neutral.

## Rationale

The package cannot make a process visible after an external caller deliberately
hides it without changing synchronous CLI/API semantics or spawning surprising
extra consoles. A normative installed launch contract covers direct users and AI
agents while preserving ordinary foreground execution, recovery, and automation.

## Impact

No runtime, run format, evidence, recovery, or API behavior changes. Future agents
must start detached Windows benchmark campaigns in a normal visible console unless
the user explicitly requests a hidden process.

## Verification

- Built `yadof_benchmark-0.1.0-py3-none-any.whl` successfully and force-reinstalled
  it into the outer workspace virtual environment.
- Confirmed `yadof_benchmark` imports from the virtual environment's
  `site-packages` directory.
- Confirmed installed `docs show README.md` and `docs show run_and_recovery.md`
  expose the visible-window default, the `WindowStyle Normal` launch example, and
  the explicit hidden-launch restriction.
- Applied the documentation-only validation exception; no runtime code or tests
  changed, so pytest was not run.
