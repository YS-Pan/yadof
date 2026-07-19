# 2026-07-19 21:14 - Installed Venv Development Workflow

## Context

The project tests are intended to exercise an installed yadof distribution, but the
development guide did not name one canonical environment or spell out how a source
change reaches that installation. Ad hoc `PYTHONPATH=src` or editable installs can
hide missing wheel resources and entry-point defects.

## Change

- Defined repository sibling `../.venv` as the canonical local installed-package
  development and runtime environment.
- Documented one-time creation from the system Python and regular `.[dev]` install.
- Documented the repeated build, newest-wheel selection, force-reinstall without
  dependency churn, installed-origin verification, and pytest sequence.
- Explicitly prohibited editable installs and repository-source `PYTHONPATH` for
  acceptance testing.

## Rationale

Using an isolated but fixed venv avoids modifying the system Python while preserving
the important contract that commands and tests consume the same immutable package
shape a real user receives. Building before replacement also leaves the last working
installation intact when a new build fails.

## Impact

Maintainers should invoke `../.venv/Scripts/python.exe` explicitly after each edit,
reinstall the newly built wheel, confirm `yadof.__file__` is below venv
site-packages, and then run the suite without source-path injection.

## Follow-Up

The documented commands may later be wrapped in a repository script, but that script
must preserve the same build-before-replace and installed-origin checks.
