# C4 context

Yadof coordinates optimization around expensive workflows without owning the
scientific meaning of a task. Researchers install the package, initialize a
workspace, define parameters, a workflow, rawData outputs, and current cost policy,
then check, smoke, run/resume, and inspect through the CLI or workspace-explicit
Python APIs.

## People and responsibilities

- Users own workspace task definitions, simulator/model inputs, objective policy,
  campaign configuration, and decisions to launch expensive work.
- AI agents may read version-matched `agent_doc`, inspect documented package code,
  and edit the selected workspace or package source when explicitly requested.
- Administrators own Python/simulator installation, licenses, HTCondor deployment,
  execute-node permissions, resource advertisement, and Windows slot-user policy.
- Package maintainers own stable framework contracts, packaged resources,
  persistence correctness, current APIs, and generic tests.

## External systems

- Local Python processes execute workflows and framework logic.
- Simulators/custom programs consume assigned variables and produce measurements.
- HTCondor transports self-contained job folders to administrator-managed workers.
- The filesystem durably stores job evidence, JSONL metadata, archives,
  checkpoints, logs, and tool output.

Yadof diagnoses but does not install, configure, restart, or repair external
software or the HTCondor pool. A workflow can orchestrate several simulations or
task-local computations before producing rawData; the framework sees only the job
contract.

An AI agent can discover version-matched task-authoring documentation through the
installed `yadof docs` command, inspect relevant package code when the documented
contract is insufficient, and edit only the selected user-owned workspace.

Package artifacts are immutable framework inputs. Workspace directories are the
only mutable task/runtime boundary. Wheel and sdist contain package code, generic
templates, adapter resources, and documentation, but exclude repository examples,
workspaces, concrete models, jobs, history, checkpoints, logs, caches, credentials,
and secrets.

## System guarantees

- No stateful API silently selects another workspace.
- A workflow writes evidence and lifecycle metadata, never authoritative costs.
- Local and distributed backends converge on the same `JobResult` and recording
  path.
- A failed candidate keeps population order and yields a correctly sized infinite
  objective row with diagnostics.
- Historical rawData can be reinterpreted by the current cost definition.
