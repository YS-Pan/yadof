# Benchmark baselines

Each leaf baseline owns a `baseline.json` and a clean yadof `workspace/`.
Discovery is recursive, so provider and task directories are organizational rather
than registry entries.

A manifest has this shape:

```json
{
  "format": "yadof.benchmark.baseline",
  "id": "provider/task",
  "name": "Readable task name",
  "description": "Current task purpose.",
  "workspace": "workspace",
  "execution": {
    "mode": "fast",
    "timeout_seconds": 7200,
    "resource": {
      "kind": "environment_executable",
      "variable": "TASK_RUNTIME"
    }
  },
  "contract": {
    "objective_count": 2,
    "rawdata_shapes": {
      "response": [101]
    }
  },
  "estimates": {
    "evaluation_seconds": 1.0,
    "record_mib": 0.1
  },
  "snapshot_excludes": []
}
```

The resource block is optional and describes only software required by the task.
Algorithm dependencies belong to the selected `optimization.py` and are validated
by the final-cell `yadof check`.

A snapshot copies the complete workspace while excluding standard generated
`jobs/`, `recorded_data/`, visualization output, bytecode/cache directories,
and generated `.yadof/` state other than its workspace marker. Additional
`snapshot_excludes` must stay inside the workspace and may name only
task-neutral generated content.

To add a baseline, create its manifest and workspace. No benchmark Python or study
registry change is required.
