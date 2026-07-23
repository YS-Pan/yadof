# Module blueprint: tests

## Scope

Maintained generic pytest modules live only in `tests/` and, for final acceptance,
import the wheel force-installed into the sibling `.venv`. Tests create neutral
temporary workspaces. Default tests require no live pool, simulator, concrete model,
license, machine identity, or credential.

## Required coverage

- package metadata, wheel/sdist members, console entry point, clean external install,
  and read-only site-packages operation;
- initialization no-overwrite behavior, marker/check diagnostics, explicit paths,
  config precedence, and two-workspace task/module isolation;
- parameter assignment, job static hash, task payload exclusions, minimal worker
  support, and absence of any yadof runtime archive/config in jobs;
- direct `workflow.py` HTCondor submit shape, Windows slot-user values, resource/time
  policy, matchmaking diagnostics, bounded retries, and per-job mocked failures;
- explicit `rawData.zip` output transfer, flat zip members, rejection of nested
  rawData, local validation, dynamic cost, and persistence atomicity;
- optimizer start/resume/shape/failure behavior, surrogate rawData-first training,
  checkpoint compatibility, intervals, and workspace-keyed scheduling;
- CLI/docs/tools/adapters and artifact exclusion of examples/runtime data.

## Test placement

Task-specific tests that assert a concrete model/design, physical objective,
frequency band, exact active parameter set, or expected simulator result stay with a
reference/disposable workspace. Neutral fake adapters and synthetic 0D/1D/2D/3D
rawData remain package fixtures.

## Acceptance

Build a wheel, force-reinstall without editable/PYTHONPATH shortcuts, verify
`yadof.__file__` is under the venv site-packages, run focused tests during iteration,
then the complete suite. Real simulator/HTCondor smoke is an explicitly authorized
integration step, not part of generic pytest.
