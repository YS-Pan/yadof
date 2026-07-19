# `hfss_com.py`

Use this adapter for HFSS/PyAEDT workflows.

The source/reference copy is a packaged adapter resource. The workflow uses the
active copy at `<workspace>/job_template/hfss_com.py`, so copy the file with
`yadof task copy-adapter hfss_com.py --workspace PATH` into
`job_template` before importing it from `workflow.py`. Reusable fixes validated in
an active copy can be contributed back to the packaged resource after task-only
assumptions are removed.

## Import Pattern

```python
from hfss_com import (
    analyze,
    save_antPara,
    save_farField,
    save_modal,
    save_nearField,
    set_hfss_temp_directory,
    set_para,
    set_variables,
    solver_exit,
    solver_init,
)
```

## Start And Stop HFSS

```python
hfss_app, project_path, design_name = solver_init(
    projectName=str(BASE_DIR / "your_model.aedt"),
    designName="YourDesignName",
    non_graphical=True,
    new_desktop=True,
)
...
solver_exit(
    hfss_app,
    save_project=True,
    cleanup_results=True,
    project_path=BASE_DIR / "your_model.aedt",
)
```

If `designName` is omitted, the adapter expects exactly one design in the project.

## Set A Job-Local Temp Directory

```python
set_hfss_temp_directory(hfss_app, BASE_DIR / "_tmp")
```

Use a job-local temp path so local and distributed jobs do not fight over shared
temporary files.

## Set Variables

```python
set_variables(
    hfss_app,
    {
        "parameter_a": "12.5mm",
        "parameter_b": "2mm",
        "$project_parameter": "1.0",
    },
)
```

Project variables begin with `$`; design variables do not. HFSS values should include
units when the AEDT variable expects units.

For optimization variables, use the assigned values in the job-local parameter
snapshot directly:

```python
set_para(hfss_app)
```

Use `set_variables()` separately for task-local state changes that are not optimizer
parameters, such as selecting a simulator mode during the workflow.

## Analyze

```python
analyze(hfss_app, analyzeSetup="YourSetup", CPUcores=4, ParallelTasks=1)
```

Keep `CPUcores` aligned with `YADOF_HFSS_JOB_CPUCORE`. In the current HFSS config
that value is the manual HTCondor CPU request times `HFSS_CPUCORE_MULTIPLIER`, so it
may intentionally be greater than the scheduler request.

## Save Modal Data

```python
save_modal(
    hfss_app,
    "YourModalExpression",
    variations={"YourSweepVariable": ["All"]},
    setup="YourSetup : YourSweep",
    out_dir=str(RAW_DATA_DIR),
    output_name="modal_response",
    metadata={"hfss_quantity": "task_modal_quantity"},
)
```

Modal data is usually trace-like. If `primary_sweep_variable` is supplied, the adapter
exports that trace. Otherwise it derives a compatible trace or grid from PyAEDT
solution data.

## Save Far-Field Data

```python
save_farField(
    hfss_app,
    "YourFarFieldExpression",
    context="YourFarFieldSetup",
    variations={"YourAngleAxis1": ["All"], "YourAngleAxis2": ["All"], "YourFrequencyAxis": ["YourFrequency"]},
    setup="YourSetup : LastAdaptive",
    out_dir=str(RAW_DATA_DIR),
    output_name="far_field_response",
    metadata={"hfss_quantity": "task_far_field_quantity"},
)
```

For far fields, omitting `primary_sweep_variable` preserves full-matrix rawData when
PyAEDT exposes it. This is preferred for surrogate training because `calc_cost.py`
can select objective windows later without losing the rest of the field.

## Save Near-Field Or Antenna-Parameter Data

```python
save_nearField(
    hfss_app,
    "YourNearFieldExpression",
    context="YourNearFieldContext",
    variations={"YourNearFieldAxis": ["All"], "YourSweepVariable": ["All"]},
    setup="YourSetup : YourSweep",
    out_dir=str(RAW_DATA_DIR),
    output_name="near_field_response",
)

save_antPara(
    hfss_app,
    "YourAntennaParameterExpression",
    variations={"YourSweepVariable": ["All"]},
    setup="YourSetup : YourSweep",
    out_dir=str(RAW_DATA_DIR),
    output_name="antenna_parameter"
)
```

## Metadata And File Names

The active workspace `job_template/hfss_com.py` supports `output_name=` and
`metadata=` for save functions. Use them so `calc_cost.py` can find rawData by stable
names and task-specific tags.

If you replace the active adapter by copying a fresh packaged resource, make sure
the copied adapter still supports the arguments your workflow uses.
