# 2026-09-11 14:42 - Refresh README entry points with surrogate delivery

## Context

The root README and example index did not yet expose the delivered amplitude GP
and retrieval-response programs. The benchmark README omitted surrogate-complete
and the documented low-cost monitoring policy.

## Change

Updated the project, examples, and benchmark READMEs with the existing component
guides, dependency extras, executable examples, full comparison preset, and measured
results. Corrected the outdated five-program reference and qualified viewer support.
Linked the archived result and root research summary, retaining limitations about
reused seeds, model overhead, antenna gains, and the interrupted original run.

## Rationale and impact

This is minor documentation maintenance of existing behavior and already recorded
evidence. It changes no implementation, budget, model default, or scientific
acceptance rule. Both package README metadata descriptions are refreshed through
wheel builds and force reinstalls; no simulator or software test rerun is needed.

## Validation

Checked UTF-8, all local links and heading anchors in the changed READMEs, the
reported numbers against the committed result, and the final Git diff. Verified
the installed package descriptions match the source READMEs and imports resolve
to the selected environment's site-packages. No pre-existing changes were present.
