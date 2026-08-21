# yadof user-workflow guide for AI agents

`user_doc/` is the installed documentation home for the yadof user's workflow. Its
primary reader and executor is an AI coding agent acting under a human user's
direction. The human user normally supplies the task and any execution limits, then
reviews assumptions and results. Routine bounded execution may be delegated to the
agent, while long, costly, or materially consequential work still needs explicit
authorization under the risk rules in `config_and_run.md`; users rarely need to
read and carry out these pages command by command themselves. The `user_doc` name
identifies whose workflow and authority the guidance serves, not who literally
reads each step.

This README is therefore addressed to that user-directed AI agent. Treat the
installed package and these version-matched documents as read-only sources of
truth. Every task edit and runtime artifact belongs to an explicit writable
workspace.

yadof uses a user-directed, AI-agent-first workflow. A user should install an AI
coding agent before preparing a task, open the intended writable workspace in that
agent, and provide the task together with the repository prompt starter. OpenAI
Codex is recommended because it was used to develop and verify yadof.

Yadof also treats task flexibility as a core capability. A user may correct cost,
parameter ranges/levels, configuration, workflow/evaluator, or helper code between
optimization generations and continue the campaign while keeping parameter
identity/count and objective count stable. The new problem is allowed to be
scientifically different. Yadof does not decide whether retaining earlier evidence
is scientifically appropriate; it trusts the user to keep, clear, or separate that
history deliberately. Structural dimension changes need separate future support.
See `config_and_run.md` for the safe change boundary.

## First decide the request type

- For a question, list the available documents and read only the relevant pages.
- For task creation or modification, follow the complete task-authoring reading
  order below before editing the workspace.
- For framework implementation details not specified by these documents, inspect
  the relevant installed `yadof` code. Never modify files in site-packages.

Use the installed documentation interface from any directory:

```powershell
python -m yadof docs list user
python -m yadof docs show user package_foundation.md
python -m yadof docs bundle user
```

## Task-authoring reading order

1. Read [package_foundation.md](package_foundation.md) for installation, workspace
   layout, versioning, and safe `init`/`check` behavior.
2. Read [optimization_workflow.md](optimization_workflow.md) to define parameters,
   a workflow, rawData, and costs.
3. Read [config_and_run.md](config_and_run.md) for configuration precedence,
   local/distributed smoke, start/resume, history, and viewing commands.

Task author references:

- [workflow_typical_patterns.md](workflow_typical_patterns.md)
- [calc_cost_typical_patterns.md](calc_cost_typical_patterns.md)
- [adapters/README.md](adapters/README.md) and the adapter-specific pages
- [example_prompts/README.md](example_prompts/README.md) for the expandable prompt
  example directory

Optional agent-host troubleshooting:

- [agent_environment_permissions.md](agent_environment_permissions.md) for
  sandbox identity, filesystem ACL, Git ownership, and Git index permissions.
  These are host-agent environment concerns rather than yadof behavior.

When a source checkout is available, its top-level `examples/` directory may provide
additional task-specific reference workspaces. Those examples are not installed
package resources and must not be assumed to exist in a pip-only environment.

## Task/framework code boundary

Put code in `workflow.py` or `calc_cost.py` only when it can change because the
optimization task changes. Examples include simulator/project/design selection,
task parameters, measurements to export, rawData interpretation, objective
definitions, thresholds, and objective-relevant regions.

Code that does not change between optimization tasks belongs in yadof. A fast-
compatible task puts its shared rawData-producing kernel in `evaluation.py`; a
prepared `workflow.py` may call the same kernel. A workflow
must call the copied package-owned `worker_misc.py` for execute-side lifecycle,
machine identity, standard paths, metadata, rawData preparation, and transport.
A cost module must call `yadof.job_template` helpers for reusable rawData reduction,
cost dispatch, constraints, failure fallback, and objective counting. Do not copy
or reimplement those fixed mechanisms in task files.

Every newly authored `calc_cost.py` must convert physical metrics such as seconds,
MHz, dB, or length into independent dimensionless minimization costs in `[0, 1]`:
`0` is best and `1` is worst. Use the package's algebraic-sigmoid `soft_cost()`
directly,
or use `calculate_task_cost()`/registered calculators that call it. Keep physical
units in rawData, extracted values, and fixed task-owned `goal`/`worst` thresholds;
do not return physical values as objective costs or normalize against the changing
observed history. With the default curve, `goal`/`worst` map to `0.1`/`0.9` rather
than `0`/`1`; they are calibration anchors, not clipping bounds, so results outside
conservative thresholds can still be ranked and optimized in the two slow
algebraic tails.
Use `error_cost=1.0` for task-level calculation fallback. The framework's `inf`
result for an execution-level failed individual is a separate failure sentinel,
not a normal task cost.

Promote code only when the abstraction is common across materially different
optimization tasks or is part of a stable framework contract. Keep one-task data
shapes, specialized curve groupings, simulator conventions, and narrow objective
policies local; being extractable by itself is not enough to make code framework
code.

## Operating rules

- Run `yadof init PATH` rather than inventing the workspace marker or starter files.
- Edit only the selected workspace, normally `config.py`, `job_template/`, and
  task-owned assets. You may create additional workspace directories for task
  scripts, debugging material, exported animations/images/reports, and other
  outputs; avoid the reserved framework paths documented in
  `package_foundation.md`. Do not edit installed package resources.
- Run at most one optimization campaign in a workspace at a time. To run campaigns
  concurrently, create separate workspaces so their task snapshot, history,
  writer, checkpoints, and destructive operations cannot collide.
- Run `yadof check --workspace PATH` after generating or modifying task files.
- Before running an edited task's real smoke test or optimization, apply the
  cost- and risk-based execution policy in `config_and_run.md`. An agent may run
  short, bounded work autonomously; long, high-cost, or consequential work requires
  explicit user authorization.
- Report created files, validation results, unresolved task assumptions, and any
  real execution performed. When the risk policy requires explicit authorization,
  report the exact command the user can approve for the next execution stage.

The supported command surface is `yadof --help`, `version`, `docs`, `init`, `check`,
`smoke-test`, `run`, `view`, `history`, and `task`. `view surrogate` explicitly
selects the optional read-only checkpoint tool: its bare/default mode opens the
desktop viewer, while `summary` and `audit` print text or JSON without opening a
window. Commands that can execute real software, open a desktop GUI, perform model
inference, or delete history make that behavior explicit. Framework self-tests are
`pytest` tests and are different from a task smoke test.
