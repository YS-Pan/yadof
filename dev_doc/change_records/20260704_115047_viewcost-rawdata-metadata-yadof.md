# 2026-07-04 11:50 - viewCost, rawData Metadata, And YADOF Naming Fixes

## Context
- `dev_doc/toDo/20260630 viewCost.md` requested plot readability and axis-scaling fixes for `project/tools/viewCost.py`.
- `dev_doc/toDo/20260703 bug fixes.md` requested removing duplicate rawData `meta.npy`/`metadata.npy` payloads and fixing the old `YADOT` spelling in code.

## Change
- Updated `viewCost.py` so objective and combined-cost legend entries use the same hollow marker style as the visible best Pareto points.
- Lowered the dense-scatter opacity floor so very large histories can render with more transparent points.
- Scaled the combined-cost right axis so the observed combined-cost maximum aligns vertically with individual cost `1.0` on the left axis.
- Removed duplicate `meta` arrays from active and source HFSS rawData exporters; rawData `.npz` files now use only the canonical `metadata` key.
- Renamed current code, tests, launch scripts, and current docs from `YADOT`/`yadot` to `YADOF`/`yadof` where they referred to the project or project-owned environment variables.
- Added tests for viewCost scaling helpers, rawData `meta` rejection, and HFSS export payload keys.

## Rationale
- The plot legend should visually describe the highlighted Pareto points, not the background scatter markers.
- Keeping one rawData metadata key avoids duplicate archive payloads and avoids hidden compatibility paths that can mask contract drift.
- Project-owned environment variables and visible names should match the project name, YADOF.

## Impact
- Users should switch project-owned environment variables such as `YADOF_PROGRESS`, `YADOF_HFSS_JOB_CPUCORE`, and `YADOF_RUN_HFSS_TESTS` to the corrected spelling.
- Existing rawData files with both `meta` and `metadata` still load through `metadata`, but new exports no longer write `meta`; files with only `meta` are not accepted by the current rawData contract.
- `viewCost.py` generated PNGs will have more transparent dense point clouds and a combined-cost axis aligned against the left cost scale.

## Follow-Up
- No compatibility alias for `meta` should be added unless the project explicitly chooses a migration path for legacy rawData archives.