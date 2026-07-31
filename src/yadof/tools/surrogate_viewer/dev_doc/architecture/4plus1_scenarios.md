# 4+1 scenarios

## Inspect One Checkpoint

1. Load a compatible workspace.
2. Select a checkpoint generation.
3. Select zero, one, or two of the rawData item's listed dimensions and either
   choose a stored grid coordinate or enter an arbitrary finite coordinate for
   each remaining dimension.
4. Move normalized parameter sliders or use arrow keys.
5. Predict in the background.
6. Display a scalar, curve, or filled two-dimensional color contour plus current
   objective values. Scalar and curve modes also expose the ensemble range; a
   selected real two-dimensional result is shown beside the surrogate with the
   same color scale.

Acceptance behavior: the UI remains responsive, superseded results are ignored,
stored coordinates preserve legacy grid predictions, non-grid coordinates produce
a direct decoder query without a fabricated recorded overlay, filled
two-dimensional plots have no contour lines, and no workspace file changes.

## Compare With A Real Individual

1. Select an optimization generation and recorded individual.
2. Copy its normalized variables into all sliders.
3. Predict with the selected checkpoint.
4. Overlay scalar/curve truth or show two-dimensional truth beside the prediction,
   and show side-by-side objective bars.

Acceptance behavior: clearing the overlay returns to prediction-only mode without
changing the parameter vector unless the user changes it.

On workspace load, one available optimization generation and one individual from
that generation are selected randomly so the initial prediction immediately
contains a real comparison.

## Calculate And Explore An Error Audit

1. Choose a per-generation sample percentage.
2. Run each checkpoint against the same sampled individuals.
3. Complete cost and per-rawData relative/absolute aggregates.
4. Select all costs, one cost, all rawData, or one rawData item.
5. Switch relative/absolute error without another model calculation.

Acceptance behavior: every heatmap block is discrete, centered on its generation
tick, fully visible at the edge, allowed to be rectangular, flush against its
neighbors without grid lines or gaps, and drawn with a one-line title.

## Stop A Long Audit

1. Begin recalculation while a prior complete audit is displayed.
2. Press Stop.
3. Finish the current inference batch and raise cooperative cancellation.
4. Keep or restore the prior complete heatmap.

Acceptance behavior: partial aggregates are never presented as complete and never
replace the prior audit.

## Handle Incompatible Or Broken Data

Examples include a missing model artifact, parameter-name mismatch, rawData shape
mismatch, missing sampled rawData, or model inference failure.

Acceptance behavior: the operation fails visibly with a useful message. The viewer
does not patch the workspace, skip silently to another checkpoint, or publish a
partial audit.

## Package And CLI Integration

Install the yadof wheel with its `viewer` extra, confirm
`yadof view surrogate --help` works without opening a window, and launch the GUI
only through that explicit command or its nested module entry. Acceptance behavior:
the wheel and sdist contain viewer code plus this `dev_doc/`; `yadof --help` remains
lightweight; `view all` never launches the GUI; the viewer writes no package or
workspace files.
