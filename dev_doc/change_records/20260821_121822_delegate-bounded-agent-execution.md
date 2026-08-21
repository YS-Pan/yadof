# 2026-08-21 12:18 - Delegate Bounded Agent Execution

## Context

- The user workflow previously required explicit human authorization before every
  edited task's real smoke test or optimization, regardless of simulator cost.
- That blanket gate made inexpensive ngspice and simple Project Chrono work require
  the same interaction as an HFSS campaign that may run for days.
- Machine paths, the local virtual environment, and repository Git publication are
  host-specific concerns, while execution-risk policy should travel with yadof's
  installed, version-matched user documentation.

## Change

- Replaced the blanket real-execution gate with a concrete cost/risk assessment.
  Agents may run understood, bounded, modest workspace-local work autonomously;
  long, unknown-cost, paid, shared-resource, or consequential work requires an
  explicit user request.
- Documented typical profiles for ngspice, Project Chrono, and HFSS without treating
  the simulator name as sufficient evidence: an understood HFSS smoke may run
  autonomously, while a normal multi-day HFSS optimization requires authorization.
- Required explicitly requested long runs to use a detached process, workspace-owned
  logs, and a completion handoff without polling unless the user later requests
  monitoring.
- Aligned the current architecture, documentation contract, terminology, project
  and documentation blueprints, test boundary, and public README with the revised
  user/agent authority split.

## Rationale

- Runtime and external effects vary primarily by the concrete task, population,
  generation count, mode, and resources rather than by whether a command is called
  a smoke test or optimization.
- Keeping portable risk rules in packaged user documentation lets other computers
  and users inherit the workflow, while a repository-external `AGENTS.md` can remain
  limited to one machine's paths, environment, and Git procedure.

## Impact

- AI agents reading `yadof docs` can proceed with short bounded integration work
  without an extra confirmation round and must still stop before long or materially
  consequential execution.
- Generic pytest remains simulator-free. Real integrations remain separate and are
  now governed by the same user-workflow risk policy instead of a blanket gate.
- No package code, CLI behavior, workspace format, adapter implementation, or
  runtime data changed.

## Follow-Up

- Concrete task prompts may impose stricter execution limits and continue to take
  precedence over this default policy.
