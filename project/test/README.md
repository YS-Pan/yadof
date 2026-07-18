# Test Scope And Placement

`project/test/` is the only source location for maintained automated tests. Do not
place pytest modules beside implementation code, including under
`project/tools/specific/<software>/` or `project/com_lib/`.

This remains the test home for both installed `src/yadof/` contracts and the
temporarily unmigrated `project/` runtime. Workspace tests must create neutral
temporary workspaces and must verify that no task/config/module state leaks between
them.

Tests here may cover either generic framework behavior or reusable behavior tied to
a particular simulator, vendor, adapter, or software-specific tool. A
software-specific test must remain independent of the active optimization task. It
should use mocks, synthetic data, and generated temporary resource names, and it
must not require the real external software during the default `pytest -q` run.

A test is task-specific when it encodes assumptions belonging to one optimization
task rather than to a reusable framework or software integration contract. Do not
put such tests in `project/test/`. Task-specific assumptions include, but are not
limited to:

- a concrete task input or model filename, such as a particular `.aedt` filename or
  design name;
- a concrete objective or measurement, such as `S11`, or a task's expected physical
  result;
- the active task's exact optimization-variable count, names, ranges, or units;
- importing, executing, or inspecting the active files under `project/job_template/`
  to assert the behavior of the current task.

Neutral generated filenames and minimal synthetic variable/objective shapes are
allowed when they exist only to exercise a reusable contract and do not reproduce
the active task.

If a current optimization task needs a regression or real-workflow smoke test, put
the test and every supporting model/input file under the ignored root `temp/`
directory. Everything under `temp/` except `.gitkeep` is disposable and must remain
safe to delete at any time. After yadof uses an installed package plus user
workspaces, keep and run task-specific tests in the corresponding workspace instead.
