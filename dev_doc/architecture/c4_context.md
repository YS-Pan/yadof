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
  policy, the complete `submit/optimization.py` composition, campaign configuration,
  and the authority limits for real execution.
- AI agents are the primary task-authoring interface. They read version-matched
  `user_doc` under a human user's direction, inspect documented package code, edit
  the selected workspace, and apply the documented cost/risk policy: bounded
  low-cost execution may be delegated, while long or consequential runs require an
  explicit user request.
- Administrators own Python/simulator installation, licenses, HTCondor deployment,
  execute-node permissions, resource advertisement, and Windows slot-user policy.
- Package maintainers own every cross-task invariant, stable framework contracts,
  packaged resources, persistence correctness, current APIs, and generic tests.

## External systems

- Local Python processes execute prepared workflows or reusable fast task kernels;
  fast kernels may launch local external simulators through isolated worker trees.
- Simulators/custom programs consume assigned variables and produce measurements.
- A dedicated PyChrono/Conda interpreter is treated as an external simulator:
  task-owned child code runs in a separate OS process and crosses the packaged
  adapter boundary only through versioned JSON requests/results and NPZ evidence.
- HTCondor transports self-contained job folders to administrator-managed workers.
- The filesystem durably stores job evidence, immutable standard-ZIP history
  segments and event files, checkpoints, logs, and tool output.
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
exclude repository examples, source-checkout benchmark automation, workspaces,
concrete models, jobs, history, checkpoints, logs, caches, credentials, and
secrets. A Git clone or repository download may additionally carry
`benchmark_automation/`: it invokes the matching installed distribution, owns
frozen run inputs plus inert versioned preregistration contracts, and writes only
generated execution evidence to an explicitly selected output root. A
preregistration does not itself authorize or launch a run.

## System guarantees

- No stateful API silently selects another workspace.
- A workflow writes task evidence; package worker support writes lifecycle metadata;
  neither writes authoritative costs.
- Fast, local, and distributed backends converge on backend-neutral results and the
  same finalizer. Fast results carry named memory rawData and no fake job path;
  local/distributed results carry file-backed rawData. Current cost is calculated
  before recorder admission, bounded recorder capacity applies backpressure, and a
  population cannot complete until all of its evidence is durably published.
- A failed candidate keeps population order, yields a correctly sized infinite
  objective row with diagnostics, and is durably recorded before the population
  boundary completes.
- Historical rawData can be reinterpreted by the current cost definition.
- Users may correct parameter ranges/levels, fixed-width objective/cost policy,
  optimization composition, configuration, and task execution code between generations. Parameter
  identity/count and objective count remain stable until separate structural-change
  support exists. An immutable task tree is captured once at each boundary, so the
  next generation uses one coherent current definition; yadof
  isolates mechanically unusable evidence but leaves the scientific decision to
  retain or clear old history to the user.
- Cross-task invariant code is implemented in yadof and called by task files;
  task-varying workflow/objective code is not hard-coded into yadof.
- Exactly one snapshotted workspace strategy is active. Semantic switches isolate
  component state while retaining inactive artifacts and recorded real evidence;
  package config never selects a second complete method.
