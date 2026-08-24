# Trebuchet visualization

`../postprocess.py` is the benchmark-facing entry point. It selects the completed
optimization individual with the lowest finite arithmetic-mean objective cost,
copies that individual's immutable recorded rawData into an output snapshot, and
invokes `render_trebuchet_animation.py`.

The renderer starts one visualization-only PyChrono continuation through the same
external interpreter configured by `YADOF_PYCHRONO_PYTHON`. It does not add a yadof
evaluation or alter optimization history. It produces:

- `<prefix>trebuchet_best.mp4`, an H.264 replay;
- `<prefix>trebuchet_best_poster.png`, a representative still image;
- `<prefix>trebuchet_selected_job.zip`, the reproducible selected-job snapshot;
- prefixed continuation diagnostics, trajectory, and postprocess manifest files.

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
`<cell-id>__attempt-####__` prefix automatically. The task-specific video, poster,
manifest, diagnostics, trajectory, snapshot archive, and prefixed
`benchmark-cost.png` are all stored directly in that one directory. The video
requires `ffmpeg` and the continuation requires the configured Project Chrono 10
environment.

For a manually staged completed job, `render_trebuchet_animation.py` may also be
called directly with `--job`, `--output`, `--poster`, and `--work-dir`. Keep its
work directory outside `visualization/`; the benchmark fingerprints that directory
as immutable task input.
