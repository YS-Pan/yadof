# 2026-11-12 18:25 - Fix cluster configuration save cleanup

## Context

The user reported a remote computer's save dialog asking for removal of YADOF_*
configuration without a location. Its configuration was unavailable. The local
running 0.8.1 optimization and dirty checkout were preserved; development used a
separate 0.8.1-based Git worktree and virtual environment below ignored temp/.

## Change

- Clean whole logical native configuration entries, including continued attribute
  lists and interspersed comment lines, before removing legacy metadata.
- Preserve quoted literal labels and ordinary executable filenames; still reject
  actual legacy macro and unquoted ClassAd dependencies that cannot be migrated
  automatically without changing a custom policy.
- Pass each loaded source path into cleanup. Errors identify the file, first
  physical entry line, native key and legacy names without publishing values.
- Prepare version 0.8.2 for wheel, sdist, administrator ZIP and MSI distribution.

## Evidence and limits

Pre-fix regressions reproduced the continued-list save error and literal-name false
positives. Offline tests cover cleanup, native Condor/frpc staged validation,
loaded-source diagnostics and unchanged source files on failure. No live Condor
configuration, service, queue, installed runtime or optimization workspace is
changed by this fix or its tests. The remote machine's exact offending entry still
requires its configuration or the improved diagnostic; no exact-machine root cause
is claimed.
