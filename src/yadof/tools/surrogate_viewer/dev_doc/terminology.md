# Project-Specific Terminology

| Term | Meaning In This Project |
|---|---|
| `viewer workspace` | The explicit yadof workspace selected in the GUI. It is an external, read-only data source for this application, not the `surrogate_viewer/` source directory. |
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
