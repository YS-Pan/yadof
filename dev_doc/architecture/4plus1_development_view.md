# 4+1 development view

Framework source lives only under `src/yadof/`; maintained tests live under
`tests/`. Root `dev_doc/` and `agent_doc/` are authoritative and are mapped into the
wheel as read-only resources. Complete reference workspaces may be tracked under
`examples/`, but build inclusion is restricted so examples never enter wheel or
sdist artifacts. Runtime workspaces live outside `examples/` and remain user-owned.

Tests import an installed distribution. Generic default tests do not depend on a
simulator or live HTCondor pool; scheduler commands and adapters are mocked. Artifact
tests build the distributions, inspect members, install a wheel outside the
repository, make package files read-only, and exercise the CLI and two-workspace
contracts.

The canonical local environment is the repository sibling `../.venv`, created from
the system Python. Development acceptance never uses an editable install or
repository `src/` on `PYTHONPATH`: after each change, build a wheel, force-reinstall
that wheel without dependency churn, verify the import path is below the venv's
site-packages, and only then run pytest with the venv interpreter.

Installed command routing lives under `src/yadof/cli/`; workspace context,
initialization, marker, and checking live under `src/yadof/workspace/`. Packaged
documentation commands list, show, or bundle audience-relative resources without
requiring an agent to locate site-packages.
