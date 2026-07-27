# Architecture index

The surrogate viewer is an optional, read-only `yadof.tools` application around
one explicit yadof workspace. `yadof view surrogate` launches it separately from
non-GUI history views. It presents interactive checkpoint predictions and a
cross-generation error audit without training a model or changing workspace
evidence.

The two primary data paths are:

```text
normalized parameters
  -> selected checkpoint
  -> predicted rawData
  -> current workspace cost calculation
  -> interactive plots

sampled recorded individuals + real rawData
  -> every saved checkpoint
  -> predicted rawData and current costs
  -> relative/absolute sum-count aggregates
  -> instantly selectable heatmap matrix
```

Core invariants are:

- The selected yadof workspace is explicit and read-only.
- Real rawData is source evidence; predictions and error aggregates are derived.
- Tk widgets and Matplotlib canvases are mutated only on the Tk main thread.
- A stopped or failed audit never replaces the previous complete audit.
- Metric and quantity changes derive a new matrix from memory without model
  inference.
- Private yadof checkpoint/rawData dependencies remain isolated in `backend/`.

Read the current views in this order:

- [c4_context.md](c4_context.md): people, workspace, installed yadof, and external
  runtime systems.
- [c4_container.md](c4_container.md): GUI/backend/workspace/model boundaries.
- [c4_component.md](c4_component.md): source component responsibilities and
  dependency direction.
- [4plus1_process_view.md](4plus1_process_view.md): loading, prediction, audit,
  cancellation, and failure flows.
- [4plus1_development_view.md](4plus1_development_view.md): repository structure,
  tests, documentation, and integration boundary.
- [4plus1_scenarios.md](4plus1_scenarios.md): concrete behavior expected by users.

For implementation-level contracts, continue with
`../blueprints/10_modules/` and targeted entries below
`../blueprints/20_files/`.
