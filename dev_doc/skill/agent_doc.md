# Agent Documentation Contract

## Purpose And Boundary

`agent_doc/` is the companion agent-facing documentation home. It explains how AI
assistants should prepare task files, use `_com.py` adapters, write `workflow.py`
and `calc_cost.py`, edit run configuration, smoke-test, and launch optimization.

Detailed task-authoring instructions belong under `agent_doc/`; do not duplicate
them in `dev_doc/`. The agent package-foundation document owns the installed command
surface and the boundary between immutable package code and writable task
workspaces.

## Reading Contract

Every full `dev_doc/` context pass must read `../../agent_doc/README.md` and follow
its instructions. Framework changes can affect how AI assistants prepare tasks, so
developer context is incomplete without that agent-facing pass.

Reading `agent_doc/` alone must not trigger a `dev_doc/` pass. Agent-facing task
setup documentation is allowed to stand on its own.

## Maintenance Contract

Update the relevant `agent_doc/` pages whenever a framework or documentation change
alters task-authoring behavior, supported installed commands, workspace ownership,
configuration, validation, smoke testing, execution, adapters, workflow output, or
cost calculation. Keep administrator-only installation and HTCondor pool operations
under `admin_tool/`.
