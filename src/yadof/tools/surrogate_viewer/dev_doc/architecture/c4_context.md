# C4 context

## People And Responsibilities

- A **viewer user** selects a compatible yadof workspace and either requests
  terminal metadata/error matrices or chooses checkpoints and real individuals,
  adjusts parameters, starts or stops audits, and interprets desktop plots.
- A **viewer maintainer** owns this optional tool's code and independent nested
  developer documentation while following yadof's root package-change workflow.
- A **yadof maintainer** owns checkpoint/rawData internals, CLI/package
  compatibility, wheel membership, and the maintained tests.

## External Systems

- The selected **yadof workspace** supplies effective configuration, parameter and
  objective definitions, completed records, rawData, the active optimization
  strategy pointer, and retained checkpoint artifacts.
- The enclosing **yadof package** supplies configuration/task loading, record
  access, rawData contracts, checkpoint model loading, prediction, reconstruction,
  denormalization, current cost calculation, and CLI routing.
- **PyTorch** executes checkpoint inference on the configured CPU, CUDA, or XPU
  device.
- **Tkinter** owns desktop interaction and widget state; terminal report modes do
  not import it.
- **Matplotlib** renders rawData curves, objective comparisons, and discrete
  heatmaps in the GUI.
- Standard output carries text or schema-versioned JSON reports; optional audit
  progress is isolated on standard error.
- The filesystem exposes workspace evidence and checkpoint artifacts. The viewer
  does not publish files into that workspace.

## System Boundary

The GUI starts at `yadof view surrogate [--workspace PATH]`, explicit
`yadof view surrogate gui`, or the equivalent
`python -m yadof.tools.surrogate_viewer` module entry. Terminal analysis starts at
`yadof view surrogate summary|audit`. The tool is installed below `yadof.tools`,
but remains outside core optimization/evaluation imports. The selected workspace
is an explicit input, the report mode's documented current-directory default, or
an explicit GUI selection, never an inferred package-relative project.

The application may allocate process memory, initialize accelerator contexts, and
read many workspace files. It must not:

- launch the workspace workflow or simulator;
- train or update a surrogate;
- edit configuration, records, rawData, or checkpoints;
- persist an audit cache into the workspace;
- silently switch to a different workspace.
- combine checkpoint artifacts from inactive strategy/component namespaces with
  the active strategy's report.

## Package-Internal Compatibility Boundary

The backend uses package-internal yadof functions for conditional-INR inference,
finite filling, and rawData reconstruction. Those dependencies are isolated in the
viewer backend and are not a public external API. UI modules must not spread or
depend on them.
