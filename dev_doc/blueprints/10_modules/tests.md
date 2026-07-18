# Module blueprint: tests

Maintained pytest modules live only in `tests/` and import an installed yadof
distribution. Tests create neutral temporary workspaces and cover two-workspace
isolation, local behavior, mocked distributed behavior, rawData/cost/persistence,
optimizer/surrogate recovery, CLI/tools, artifact members, clean external install,
and read-only package operation. Default tests require no live pool, simulator,
concrete model, or credential.
