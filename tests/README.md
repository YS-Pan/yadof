# Tests

`tests/` is the only maintained pytest source directory. Tests import the installed
`yadof` distribution and create isolated generic workspaces under pytest temporary
directories. They do not import a repository-local `project.*` namespace or inspect
an active user task.

Simulator-specific integration belongs in a disposable external workspace and is
run only when its software is available. The default suite remains independent of
HTCondor, HFSS, Ansys, concrete model files, and user credentials; distributed
contracts use mocked scheduler commands.
