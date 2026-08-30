# Trebuchet visualization

`../postprocess.py` is the benchmark-facing entry point. It selects both the
completed optimization individual with the lowest finite arithmetic-mean objective
cost and the individual with the lowest finite `cost_range` (the farthest throw).
It copies each selected individual's immutable recorded rawData into an output
snapshot and invokes `render_trebuchet_animation.py` for both. The two selection
rules may identify the same individual, but both named artifact sets are still
exported.

The renderer starts one visualization-only PyChrono continuation through the same
external interpreter configured by `YADOF_PYCHRONO_PYTHON`. It does not add a yadof
evaluation or alter optimization history. It produces:

- `<prefix>trebuchet_best.mp4`, an H.264 replay;
- `<prefix>trebuchet_best_poster.png`, a representative still image;
- `<prefix>trebuchet_selected_job.zip`, the reproducible selected-job snapshot;
- prefixed continuation diagnostics, trajectory, and postprocess manifest files.

The additional range-best export produces:

- `<prefix>trebuchet_range_best.mp4` and
  `<prefix>trebuchet_range_best_poster.png`;
- `<prefix>trebuchet_range_selected_job.zip`;
- `<prefix>trebuchet_range_continuation_diagnostics.json` and
  `<prefix>trebuchet_range_animation_trajectory.npz`.

The manifest retains the original average-best fields and adds the range selection,
selection rule, and range artifact paths.

Animation scratch data is created in a temporary directory and removed after the
flat result files have been copied or archived successfully.

Run the common postprocessor from any directory:

```powershell
& ".\.venv\Scripts\python.exe" `
  ".\path\to\trebuchet-workspace\postprocess.py" `
  --workspace ".\path\to\trebuchet-workspace" `
  --output-dir ".\temp\benchmark-visualizations" `
  --output-prefix "trebuchet-example__"
```

Without `--output-prefix`, the output directory must be empty or absent. With a
safe prefix, the directory may already contain other results, but none of this
invocation's prefixed filenames may exist. Benchmark automation supplies one flat
run-level `visualizations/` directory and a unique
`<cell-id>__attempt-####__` prefix automatically. Both task-specific videos,
posters, diagnostics, trajectories, snapshot archives, the shared manifest, and
prefixed `benchmark-cost.png` are all stored directly in that one directory. The
videos require `ffmpeg`, and both continuations require the configured Project
Chrono 10 environment.

For a manually staged completed job, `render_trebuchet_animation.py` may also be
called directly with `--job`, `--output`, `--poster`, and `--work-dir`. Keep its
work directory outside `visualization/`; the benchmark fingerprints that directory
as immutable task input.
