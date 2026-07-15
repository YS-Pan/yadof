# Framework Test Scope

`project/test/` contains only reusable yadof framework-contract tests. Tests here
must be independent of the active optimization task and of any particular simulator
or vendor.

Do not add assertions about the current task's parameter names or count, objective
names or count, model/input filenames, simulator expressions, adapter-specific
arrays, or expected physical results. Use generic task doubles, neutral filenames,
and schema-valid synthetic rawData when a framework test needs task behavior.

Tests for a simulator-specific tool or reusable adapter may live beside that code
under `project/tools/specific/<software>/` or `project/com_lib/` and are run
explicitly. They are not part of the default `pytest -q` path.

If the active optimization task needs a temporary regression or real-workflow smoke
test in the current repository layout, put it under the ignored root `temp/`
directory. Files there are disposable and may be deleted at any time. After yadof
uses an installed package plus user workspaces, keep and run task-specific tests in
the corresponding workspace instead.
