# Shorten benchmark execution workspaces

## Problem

The code-first benchmark runner materialized each yadof workspace below the full
run ID, semantic cell ID, and attempt path. A real ngspice 46 integration produced
driver and log paths around 280 characters and every candidate exited with code 1,
although the same netlist and parameters succeeded in a short directory. Because
the runner did not request yadof's all-infinite failure policy, both zero-success
cells were then collected as completed benchmark cells with contract issues.

## Change

- Keep readable attempt evidence below `cells/<cell-id>/attempts/<number>`.
- Materialize the executable yadof workspace below
  `workspaces/<16-character cell SHA-256 prefix>/<number>` and record that path in
  attempt state.
- Add `--fail-on-all-infinite` to every measured yadof run.
- Cover the compact layout and failure flag in the focused benchmark tests, and
  update the independent package's current developer/user contracts plus the root
  project blueprint and terminology.

## Rationale

Cell IDs are evidence identities and should remain explicit, but they do not need
to be repeated in a path passed to an external simulator. A deterministic compact
run-local directory preserves immutable snapshots and resume behavior without an
external alias or machine-global scratch. Rejecting an all-infinite generation
prevents process-level success from being mistaken for usable benchmark evidence.

## Impact

New runs use the compact workspace layout and fail cells that produce no finite
candidate. Existing runs remain self-contained and resume with their snapshotted
driver and recorded workspace paths. Yadof core, baseline physics, strategy
composition, and historical benchmark evidence are unchanged.

## Verification

- Built the independent `yadof-benchmark` wheel, force-reinstalled it into the
  outer workspace virtual environment, and confirmed its import originated from
  `site-packages`.
- Ran the installed-wheel focused suite with a fresh pytest base directory and
  cache disabled: `14 passed`.
- Ran the six-cell integration workspace across all three packaged baselines and
  both strategies. All six cells were collected without issues, both contracts
  matched, and every cell had finite completed evaluations; both ngspice cells
  completed all 24 planned evaluations.
- Confirmed the six executable workspace paths used the compact layout and were
  155 characters at the workspace root in the integration run.
