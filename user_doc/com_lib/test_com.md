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
filled with `0.5`. Values already in `[0, 1]` are used as normalized inputs. If the
input appears to be raw task values outside `[0, 1]`, the adapter rescales that
vector into `[0, 1]` before generating deterministic synthetic responses.

## Output Profiles

The default profile is `profile="hfss_like"`. It mirrors the current HFSS-like
`temp/jobs` rawData shape:

- `s11_pinState1`, `s11_pinState2`, `s11_pinState3`: one-dimensional `Freq` traces.
- `gain_lhcp_pinState1`, `gain_lhcp_pinState2`, `gain_lhcp_pinState3`: `Freq x Phi x Theta` grids with shape `1 x 73 x 73`.
- `axial_ratio_pinState1`, `axial_ratio_pinState2`, `axial_ratio_pinState3`: `Freq x Phi x Theta` grids with shape `5 x 73 x 73`.

Each block contains:

- `arrays`: arrays that can be written into one `.npz` file, including `data`, axis arrays, and axis units,
- `metadata`: rawData metadata with `schema_version`, `rawdata_name`, `shape`, `axis_names`, and ordered `axes` descriptors.

A smaller legacy-style profile remains available for lightweight examples:

```python
blocks = evaluate_raw_data(variables, profile="generic")
```

That profile returns `summary`, `curve`, and `surface` blocks.

This adapter is useful for checking `workflow.py`, `calc_cost.py`, `recorded_data`,
optimizer behavior, and surrogate training without opening AEDT.
