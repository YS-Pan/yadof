# HTCondor matchmaking and worker bootstrap fixes

## Problem

A distributed generation could remain entirely idle until the generation timeout
when its submit requirements matched no execution slot. Progress output only showed
the pending count, hiding the mismatched ClassAd condition.

After the requirement mismatch was corrected, a real pure-Python Condor job exposed
a second failure: direct `workflow.py` execution selected a Windows-associated Python
that did not import the transferred `sitecustomize.py` and had no installed yadof.

The first real HFSS smoke then exposed a third Windows submit bug before solver
startup: double-quoting an AEDT filename with spaces made Condor include the quote
characters in the source path and hold the job during input transfer.

## Change

- After a pending job remains unresolved for 5 to 60 seconds (scaled by the polling
  interval), query one representative cluster with
  `condor_q -better-analyze:nouserprios`.
- Print a compact diagnostic containing failed requirements, the no-match warning,
  and the scheduler's last match failure.
- Preserve normal queue semantics: the diagnostic is read-only and does not fail or
  remove jobs because slots may appear later.
- Prepare `yadof_worker.py` and an importable `yadof_worker_package.zip` in every job.
  Condor directly executes the launcher; it prepends the matching archive, explicitly
  invokes compatibility bootstrap, and only then runs `workflow.py`.
- Have the launcher create `rawData_outputs.zip` after every workflow attempt. This
  supplies the existing submit-side restore path when Windows Condor returns top-level
  output files but omits the nested `rawData` directory.
- Emit transfer filenames with spaces literally, reject unrepresentable commas or
  newlines, and remove non-resource held clusters after recording their diagnostics.

## Validation

- Added a focused regression test for extracting
  `TARGET.YADOF_RAMDISK is true` from representative HTCondor output.
- Submit-file and job-preparation tests assert the launcher/archive transfer contract
  and wheel contents.
- Package tests and installed-wheel validation are recorded in the task handoff.
