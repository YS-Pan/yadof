# 2026-11-08 - Organize desktop toolboxes and release 0.8.1

## Context

The user requested two installed tool groups, four double-click framework
viewers, and a compact AEDT variable exporter in the user toolbox. The change
also carries the previously requested main-GUI tools button and per-run elapsed
timer, and the OptimizationSetup1-only AEDT exporter. Publication to the public
YS-Pan/yadof repository and release 0.8.1 are explicitly authorized.

## Change

- `tools/yadof_tools/` exposes `viewcost.pyw`, `viewtime.pyw`, `viewerror.pyw`
  and `surrogateviewer.pyw`. Each implementation has its own subdirectory.
  Console and shared launch/history helpers also have dedicated directories.
- The first three entries select an initialized workspace, read history in a
  worker, and present the existing plots or sortable error table through Tk.
  They share the same builders as the main console. SurrogateViewer retains
  its existing application and model behavior.
- Every installed `.pyw` binds its owning private Python runtime before
  importing yadof, including when Windows associates `.pyw` with another Python.
- `tools/user_tools/aedt_parameters_gui.pyw` contains the complete AEDT desktop
  UI. Its parser remains in one helper package because the workspace CLI also
  consumes that parser. Export selection remains exact `OptimizationSetup1`
  Include records, with validated bounds and original-output backups.
- CLI names and arguments remain stable. Python tool imports move to the two
  categorized namespaces. The native MSI launcher and package entry points
  follow the new console location; reused runtimes regenerate their launchers.
- Main-GUI tools opens the categorized installed directory. Its monotonic
  elapsed timer resets on each accepted start, freezes at stop/completion/error,
  and formats durations of at least one day as `D+HH:MM:SS`.
- Version advances to 0.8.1. A release workflow builds distributions and the
  private-runtime MSI, performs isolated acceptance, and publishes the exact
  verified commit with administrator sources, evidence and checksums. Runtime
  and compiler downloads are hash pinned; published releases are immutable.
- Release regression exposed a pre-existing administrator configuration cleanup
  false positive for paths containing `yadof_latest`. Legacy metadata references
  are now recognized as tokens, preserving filesystem path components while
  still rejecting unresolved legacy expressions.

## Validation

Installed-wheel validation covers categorized entry paths, owning-runtime
selection and forwarding, standalone viewer dispatch/cancel/error handling,
AEDT export and backup behavior, console timer state transitions, documentation
links and distribution contents. Native acceptance uses a separate MSI identity
and a scratch workspace, preserving existing installations and real campaigns.
The release validation artifact records the final MSI acceptance evidence.
