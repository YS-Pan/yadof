# Run format

A run is a self-contained directory created below the study's `runs_dir`:

```text
<run>/
├── spec.json
├── state.json
├── driver/
│   ├── benchmark.py
│   ├── benchmark_core.py
│   └── benchmark_runtime/
├── inputs/
│   ├── baselines/<baseline>/
│   │   ├── baseline.json
│   │   └── workspace/
│   └── strategies/<strategy>/<baseline>/optimization.py
├── cells/<cell>/attempts/<number>/
│   ├── workspace/
│   ├── commands/<number>-<label>/
│   │   ├── started.json
│   │   ├── finished.json
│   │   ├── stdout.log
│   │   └── stderr.log
│   └── result.json
├── visualizations/
├── results.json
├── results.csv
└── report.md
```

## Ownership

- `spec.json` freezes the normalized study, discovered baseline facts, expanded
  cell matrix, input paths, and provenance digests.
- `state.json` is the atomically replaced operational index. It records cell and
  attempt status but is not scientific evidence.
- `driver/` is the complete implementation used by resume.
- `inputs/` is the only baseline and strategy source used after creation.
- Each attempt is immutable execution evidence. A retry creates another numbered
  attempt instead of editing an earlier workspace.
- `result.json` is one public-yadof cell observation.
- Root result files are current derived views and can be regenerated from cell
  results without modifying measured workspaces.

All references owned by a run are relative to the run root. The directory may be
moved as a unit before inspection or resume.

## Status

The cell state sequence is:

```text
planned → checked → running → succeeded → collected
                       ↘ failed
```

On resume, an interrupted checked or running attempt is sealed as interrupted and
a new attempt is created. A succeeded cell retries only collection. A collected
cell is skipped. The run becomes completed only when every cell is collected.

## Commands

```powershell
python ".\benchmark_automation\benchmark.py" inspect --run D:\studies\runs\<run>
python ".\benchmark_automation\benchmark.py" resume --run D:\studies\runs\<run>
```

`inspect` reads `spec.json`, `state.json`, available result locations, and the
active command's bounded timestamps. It writes nothing and reports elapsed and
inactivity values without predicting completion time.

`resume` loads `driver/benchmark_runtime` under an isolated module name. It does
not reload the external study or strategy sources and does not compare recorded
digests with the current checkout. Digests remain provenance for explaining what
was executed.

## Interpretation

`results.json` contains arbitrary-arm long rows, cell summaries, and optional
reference deltas grouped by baseline, seed, population, and generation count.
Opaque public yadof optimization metadata is retained under an extension namespace
without algorithm-specific interpretation. `report.md` is descriptive; it does
not rank strategies, perform significance tests, or make an acceptance decision.
