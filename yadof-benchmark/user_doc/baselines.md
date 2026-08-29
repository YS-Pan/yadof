# Baselines and packaged resources

`yadof-benchmark baselines` lists the baseline collection installed with the
package. A collection has this source layout:

```text
BASELINES_ROOT/
└── provider/task/
    ├── baseline.json
    └── workspace/
        ├── .yadof/workspace.json
        ├── config.py
        ├── submit/
        └── job_template/
```

Discovery is recursive, but the manifest directory relative to `BASELINES_ROOT`
must exactly equal its semantic `id`. For example, the manifest with ID
`ngspice/saw-ladder` lives at `ngspice/saw-ladder/baseline.json`. Do not append a
content hash or other opaque fingerprint to an editable source directory.

Each `baseline.json` names the complete yadof workspace, its execution mode and
timeout, expected objective count and rawData shapes, rough time/record-size
estimates, and optional task-neutral snapshot exclusions. Behavioral inputs below
`submit/` and `job_template/`, `config.py`, and the workspace marker cannot be
excluded.

The package currently ships these semantic baseline resources:

- `chrono/trebuchet`
- `ngspice/saw-ladder`
- `test-com/synthetic-antenna`

Installed resources are read-only. Use `--baselines-root PATH` with `check`,
`plan`, or `run` to select an editable collection; Python callers pass
`baselines_root=`. One way to seed such a collection is:

```python
from pathlib import Path
import shutil

from yadof_benchmark import discover_baselines

source = discover_baselines()["ngspice/saw-ladder"].root
target = Path("D:/benchmarks/baselines/ngspice/saw-ladder")
shutil.copytree(source, target)
```

Edit the copied task at any time. A run freezes the current manifest and complete
clean workspace, so later source edits never alter or invalidate that run. IDs
remain decentralized: adding a valid semantic directory and manifest below the
selected root is sufficient; there is no central task or algorithm registry.

Baseline manifests are JSON evidence contracts. This does not create a second
workflow configuration surface: comparison structure and execution flow remain in
workspace `benchmark.py`.
