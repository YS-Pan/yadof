# 2026-08-06 14:30 - Fix PyChrono Windows Child DLL Path

## Context

- The packaged PyChrono adapter passed fake-worker conformance but its first real
  mechanics workspace hung while importing the official Windows PyChrono build.
- Direct execution proved that an absolute Conda interpreter is insufficient for
  that build: native modules load only when the child process PATH includes the
  environment's standard DLL directories.
- The administrator installation record already captured this requirement, while
  the later subprocess contract and adapter accidentally prohibited implementing
  it.

## Changes

- Derived the Windows runtime prefix from the already-resolved absolute interpreter
  and prepended its prefix, `Library/mingw-w64/bin`, `Library/usr/bin`,
  `Library/bin`, `Scripts`, and `bin` entries to the per-launch child PATH copy.
- Preserved the inherited child PATH after those entries, normalized
  case-insensitive PATH keys, and left POSIX behavior plus the parent process
  environment unchanged.
- Extended fake-worker conformance to assert both the deterministic Windows prefix
  order and inherited-PATH retention.
- Corrected current architecture, blueprints, terminology, and user guidance to
  distinguish child-only native-DLL discovery from PATH-based interpreter selection
  or Conda activation.

## Rationale

- The configured absolute executable remains the only runtime selector. Adding DLL
  directories derived from that selected executable is load support, not discovery
  or activation.
- A child-only environment copy satisfies the released PyChrono loader while
  preserving user, machine, shell, and parent-process isolation.

## Verification

- Built `dist/yadof-0.2.0-py3-none-any.whl`, force-reinstalled it into the sibling
  `.venv` without editable/PYTHONPATH shortcuts, and verified imports resolved from
  `.venv/Lib/site-packages/yadof`.
- Focused fake-worker adapter conformance: `13 passed`.
- Complete installed-package suite: `217 passed`.
- The real King Arthur trebuchet workspace completed one midpoint PyChrono
  evaluation through both fast and local prepared-workflow paths with identical
  objective costs and schema-valid finite NPZ evidence.

## Automatic toDo check

- The expired `agent_doc` rename consistency handoff was archived according to its
  automatic obsolete rule.
- No packagify inconsistency or incidental duplicate implementation was found in
  the bounded adapter, contract, test, and workspace diff.
