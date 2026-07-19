# yadof

yadof is an installable, task-agnostic optimization framework for expensive local
or HTCondor workflows. Its durable modeling contract is:

## Prompt starter

> Complete the task below. Before you begin, run `python -m yadof docs show agent README.md` and follow its instructions, reading any referenced documentation or installed yadof code needed for the task.

```text
normalized variables -> rawData -> current task cost
```

Install the wheel, create a writable workspace, edit only that workspace, and run
the CLI from any directory:

```powershell
python -m pip install yadof-0.1.0-py3-none-any.whl
yadof init D:\work\my-study
yadof check --workspace D:\work\my-study
yadof smoke-test --workspace D:\work\my-study
yadof run --workspace D:\work\my-study --generations 10
yadof view cost --workspace D:\work\my-study
```

The package owns framework code, defaults, worker support, templates, adapters,
tools, and documentation. A workspace owns `config.py`, `job_template/`, jobs,
recorded raw evidence, surrogate checkpoints, logs, and tool output. Package files
are treated as read-only and there is no `project.*` compatibility namespace.

See [agent_doc/README.md](agent_doc/README.md) for agent-oriented installation and
workflow guidance,
and [dev_doc/README.md](dev_doc/README.md) for architecture and contribution rules.
The checked-in [examples](examples/README.md) preserve complete reference workspaces,
including the former HFSS task; examples are tracked in Git but excluded from wheel
and sdist artifacts.
