# Project-Specific Terminology

| Term | Meaning In This Project |
|---|---|
| `viewer workspace` | The explicit yadof workspace selected in the GUI. It is an external, read-only data source for this application, not the `surrogate_viewer/` source directory. |
| `active strategy scope` | The optimization strategy signature selected by `.yadof/optimization/active.json`. Viewer checkpoint discovery selects one compatible declared `conditional-inr`, experimental `hierarchical-cae`, or deterministic `pca-svd` component namespace inside that strategy; inactive or alternate namespaces remain retained but are not mixed into the current report. |
| `deterministic viewer member` | The single PCA/SVD prediction represented as one member so generic prediction, plot, and audit shapes remain uniform. It is not an ensemble, uncertainty estimate, posterior draw, or off-grid decoder. |
| `checkpoint generation` | The optimization generation associated with the training evidence used to produce a saved surrogate checkpoint. It is the heatmap x-axis. |
| `optimization generation` | The generation to which a recorded real individual belongs. It is the heatmap y-axis and is independent of the selected checkpoint generation. |
| `real result` | One completed recorded individual containing variables and retrievable rawData. It may be overlaid on an interactive surrogate prediction. |
| `rawData item` | One named rawData entry reconstructed through the yadof rawData contract, such as `gain_port1_hf` or `s11_hf`. |
| `modeled scalar` | One flattened numeric value covered by a checkpoint's modeled rawData slots. Metadata and unmodeled fields do not contribute an error count. |
| `error audit` | One complete cross-product inference pass in which every selected checkpoint predicts the same sampled historical individuals. |
| `complete audit` | An error audit that reached successful completion. A stopped or failed run never replaces the previous complete audit displayed by the GUI. |
| `aggregate cache` | In-memory error `sum/count` arrays indexed by optimization generation, checkpoint generation, and cost or rawData item. It contains no per-individual prediction history and is not written to disk. |
| `quantity` | The heatmap target selection: all costs, one cost, all rawData, or one rawData item. |
| `relative epsilon` | `SURROGATE_RELATIVE_ERROR_EPS`, used as the denominator floor in `abs(prediction - truth) / max(abs(truth), epsilon)`. It prevents division by zero; it is not a model perturbation. |
| `interactive predictor` | The session-local loaded-checkpoint path used for one parameter vector and optional real-result comparison. It is separate from the cross-generation audit. |
| `plot dimension` | One rawData dimension selected as an interactive independent variable. Zero, one, or two selections produce a scalar, curve, or filled two-dimensional color contour respectively. |
| `fixed dimension` | Any rawData dimension not selected for plotting. Its checkpoint-grid dropdown preserves the legacy stored slice, while its text entry may request any finite physical coordinate. |
| `off-grid rawData query` | A plot-only evaluation at a fixed physical coordinate absent from the checkpoint grid. Conditional INR evaluates its decoder and interpolates the target scaler; coordinate-enabled hierarchical CAE evaluates its declared all-axis in-domain readout. Recorded truth is unavailable, full-grid output remains authoritative, and the checkpoint is not changed. |
| `terminal report` | A complete stdout-only `summary` or `audit` result below `yadof view surrogate`. It identifies strategy/run/component scope, is human-readable text or schema-versioned JSON, uses stderr for optional progress, and is never persisted. |
| `quantity selector` | The terminal audit syntax `all-costs`, `cost:NAME`, `all-rawdata`, or `rawdata:NAME`, resolved exactly against the current workspace objective/rawData names after one complete audit. |
