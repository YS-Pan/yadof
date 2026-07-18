# 4+1 development view

Framework source lives only under `src/yadof/`; maintained tests live under
`tests/`. Root `dev_doc/` and `user_doc/` are authoritative and are mapped into the
wheel as read-only resources. A checked-in example/real task may live under
`workspaces/`, but build inclusion is restricted so no workspace enters wheel or
sdist.

Tests import an installed distribution. Generic default tests do not depend on a
simulator or live HTCondor pool; scheduler commands and adapters are mocked. Artifact
tests build the distributions, inspect members, install a wheel outside the
repository, make package files read-only, and exercise the CLI and two-workspace
contracts.
