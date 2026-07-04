# `test_com.py`

Use this adapter when you want a pure-Python stand-in for an expensive simulator.
It does not calculate cost; it returns rawData-like blocks.

The source/reference copy is `project/com_lib/test_com.py`. To use it in a workflow,
copy it to `project/job_template/test_com.py`.

## Import Pattern

```python
from test_com import evaluate_raw_data
```

## Workflow Usage

```python
import json

import numpy as np

from test_com import evaluate_raw_data

blocks = evaluate_raw_data(load_variables(BASE_DIR))
for name, block in blocks.items():
    arrays = dict(block["arrays"])
    metadata = dict(block["metadata"])
    values = np.asarray(arrays.get("values", arrays.get("data")))
    metadata.setdefault("schema_version", 1)
    metadata.setdefault("rawdata_name", name)
    metadata.setdefault("shape", list(values.shape))
    arrays["metadata"] = json.dumps(metadata, ensure_ascii=True)
    np.savez_compressed(RAW_DATA_DIR / f"{name}.npz", **arrays)
```

## Input Shape

`evaluate_raw_data()` accepts either:

- a mapping of variable names to floats,
- or a sequence of floats.

If fewer than the internal synthetic input dimension are provided, missing values are
filled with `0.5`. Values are clipped into `[0, 1]`.

## Output Blocks

The returned dictionary contains rawData-style blocks:

- `summary`: scalar-like response channels,
- `curve`: multi-channel curve data,
- `surface`: two-dimensional surface data.

Each block contains:

- `arrays`: arrays that can be written into one `.npz` file,
- `metadata`: rawData metadata that should receive `schema_version`, `rawdata_name`, and `shape` defaults before saving.

This adapter is useful for checking `workflow.py`, `calc_cost.py`, `recorded_data`,
and optimizer behavior without opening AEDT.
