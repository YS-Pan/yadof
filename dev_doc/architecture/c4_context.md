# C4 context

Researchers install yadof, initialize a workspace, define task-owned parameters,
workflow/rawData, and costs, then check, smoke, run/resume, and inspect through the
CLI or workspace-explicit Python APIs. A workflow may call simulators or custom
software. Distributed mode talks to an administrator-managed HTCondor pool; yadof
submits, diagnoses, and records jobs but never installs or repairs the pool.

An AI agent can discover version-matched task-authoring documentation through the
installed `yadof docs` command, inspect relevant package code when the documented
contract is insufficient, and edit only the selected user-owned workspace.

Package artifacts are immutable framework inputs. Workspace directories are the
only mutable task/runtime boundary. Wheel and sdist contain package code, generic
templates, adapter resources, and documentation, but exclude repository examples,
workspaces, models, jobs, history, checkpoints, logs, caches, and secrets.
