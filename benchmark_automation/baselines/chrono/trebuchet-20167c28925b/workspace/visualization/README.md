# Trebuchet visualization

`../postprocess.py` is the benchmark-facing entry point. It selects the completed
optimization individual with the lowest finite arithmetic-mean objective cost,
copies that individual's immutable recorded rawData into an output snapshot, and
invokes `render_trebuchet_animation.py`.

The renderer starts one visualization-only PyChrono continuation through the same
external interpreter configured by `YADOF_PYCHRONO_PYTHON`. It does not add a yadof
evaluation or alter optimization history. It produces:

- `trebuchet_best.mp4`, an H.264 replay;
- `trebuchet_best_poster.png`, a representative still image;
- `postprocess_manifest.json`, the selection and provenance record;
- `selected_job/` and `_animation_work/`, the reproducible snapshot and scratch
  evidence.

Run the common postprocessor from any directory:

```powershell
& ".\.venv\Scripts\python.exe" `
  ".\path\to\trebuchet-workspace\postprocess.py" `
  --workspace ".\path\to\trebuchet-workspace" `
  --output-dir ".\temp\benchmark-visualizations\trebuchet-example"
```

The output directory must be empty or absent. Benchmark automation supplies a
unique run-level `visualizations/<cell-id>/attempt-####/` directory automatically.
The task-specific video, poster, manifest, and reproducibility evidence are stored
there together with the automation-generated `benchmark-cost.png`. The video
requires `ffmpeg` and the continuation requires the configured Project Chrono 10
environment.

For a manually staged completed job, `render_trebuchet_animation.py` may also be
called directly with `--job`, `--output`, `--poster`, and `--work-dir`. Keep its
work directory outside `visualization/`; the benchmark fingerprints that directory
as immutable task input.
