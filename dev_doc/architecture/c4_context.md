# C4 context

Yadof coordinates optimization around expensive workflows without owning the
scientific meaning of a task. Researchers install the package, initialize a
workspace, define parameters, a workflow, rawData outputs, and current cost policy,
then check, smoke, run/resume, and inspect through the CLI or workspace-explicit
Python APIs.

The supported default journey is agent-led. The user first installs an AI coding
agent, preferably OpenAI Codex because it is the development reference, opens the
intended writable workspace, and gives the agent the task plus the prompt starter.
Direct CLI/API use remains supported but is the lower-level surface.

## People and responsibilities

- Users own workspace task-variable definitions, simulator/model inputs, objective
  policy, campaign configuration, and decisions to launch expensive work.
- AI agents are the primary task-authoring interface. They read version-matched
  `user_doc` under a human user's direction, inspect documented package code, and
  edit the selected workspace.
- Administrators own Python/simulator installation, licenses, HTCondor deployment,
  execute-node permissions, resource advertisement, and Windows slot-user policy.
- Package maintainers own every cross-task invariant, stable framework contracts,
  packaged resources, persistence correctness, current APIs, and generic tests.

## External systems

- Local Python processes execute workflows and framework logic.
- Simulators/custom programs consume assigned variables and produce measurements.
- HTCondor transports self-contained job folders to administrator-managed workers.
- The filesystem durably stores job evidence, JSONL metadata, archives,
  checkpoints, logs, and tool output.
- Terminal stdout/JSON and the Tkinter/Matplotlib desktop UI provide two explicit,
  read-only surrogate checkpoint inspection surfaces; PyTorch performs checkpoint
  inference for audits and interactive predictions.

Yadof diagnoses but does not install, configure, restart, or repair external
software or the HTCondor pool. A workflow can orchestrate several simulations or
task-local computations before producing rawData; the framework sees only the job
contract.

The user's AI agent can discover version-matched task-authoring documentation
through the installed `yadof docs` command, inspect relevant package code when the
documented contract is insufficient, and edit only the selected user-owned
workspace.

Package artifacts are immutable framework inputs. Workspace directories are the
only mutable task/runtime boundary. Wheel and sdist contain package code, generic
templates, adapter resources, documentation, and the optional viewer source, but
exclude repository examples, workspaces, concrete models, jobs, history,
checkpoints, logs, caches, credentials, and secrets.

## System guarantees

- No stateful API silently selects another workspace.
- A workflow writes task evidence; package worker support writes lifecycle metadata;
  neither writes authoritative costs.
- Local and distributed backends converge on the same `JobResult` and recording
  path.
- A failed candidate keeps population order and yields a correctly sized infinite
  objective row with diagnostics.
- Historical rawData can be reinterpreted by the current cost definition.
- Cross-task invariant code is implemented in yadof and called by task files;
  task-varying workflow/objective code is not hard-coded into yadof.
