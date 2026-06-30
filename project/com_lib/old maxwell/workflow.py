from __future__ import annotations

import glob
import json
import os
from pathlib import Path
import shutil

import numpy as np

from maxwell2D_com import analyze, save_transient, set_Mxw2d_temp_directory, set_para, solver_exit, solver_init
from optConfig import ERROR_COST, JOB_CPUCORE, NON_GRAPHICAL
from worker_misc import bootstrap_home_dirs, evaluate_constraints, softmax

BASE_DIR = Path(__file__).resolve().parent
PROJECT_PATTERN = "*.aedt"
DESIGN_NAME = "t91703 POS_CTRL"
PARAMETER_FILE = BASE_DIR / "parameters_constraints.py"
TEMP_DIR = BASE_DIR / "_tmp"
RAW_DATA_DIR = BASE_DIR / "rawData"
COST_JSON = BASE_DIR / "cost.json"

ALL = "ALL"
LAST = "LAST"
DEFAULT_TRANSIENT_RANGE = (ALL, 0)

#——————————————————————————————————————————————Costs Calculation Setup Begin——————————————————————————————————————————————————————————————
COST_KEYS_IN_ORDER = (
    "cost_speed",
    "cost_Mass",
    "cost_Efficiency",
    "cost_Voltage",
    "cost_constraints",
)

OBJECTIVE_NAMES = COST_KEYS_IN_ORDER

# data_range:
#   (ALL, 0)   -> use all points
#   (LAST, N)  -> use the last N points
#   (a, b)     -> use points with x in [a, b], in the raw axis unit stored in npz
TRANSIENT_COSTS = (
    {
        "expression": "Moving1.Speed",
        "goal": 140.0,
        "worst": 10.0,
        "variations": {"Time": ["All"]},
        "ext_ratio": 0.4,
        "scale": 1.0,
        "data_range": (LAST, 10),
    },
    {
        "expression": "MassTotal", #kg
        "goal": 300,
        "worst": 1200.0,
        "variations": {"Time": ["All"]},
        "ext_ratio": 0.9,
        "scale": 1.0,
        "data_range": DEFAULT_TRANSIENT_RANGE,
    },
    {
        "expression": "Moving1.Speed^2*MassProjectile*0.5/$StoreEnergy", #Efficiency = KineticEnergy / StoredEnergy
        "goal": 0.50,
        "worst": 0.01,
        "variations": {"Time": ["All"]},
        "ext_ratio": 0.9,
        "scale": 1.0,
        "data_range": (LAST, 10),
    },
    {
        "expression": "-InducedVoltage(Winding10)",
        "goal": 1000.0,
        "worst": 4000.0,
        "variations": {"Time": ["All"]},
        "ext_ratio": 1.0,
        "scale": 1e-3,
        "data_range": DEFAULT_TRANSIENT_RANGE,
    },
)
#——————————————————————————————————————————————Costs Calculation Setup End——————————————————————————————————————————————————————————————

def _as_float_1d(values) -> np.ndarray:
    arr = np.asarray(values)
    if np.iscomplexobj(arr):
        arr = np.real(arr)
    return arr.astype(float).ravel()


def _write_final_cost_json(path: str | Path, cost_keys, values, default_cost: float) -> None:
    vals = [float(x) for x in list(values)[: len(cost_keys)]]
    vals += [float(default_cost)] * max(0, len(cost_keys) - len(vals))
    Path(path).write_text(
        json.dumps({k: v for k, v in zip(cost_keys, vals)}, indent=2),
        encoding="utf-8",
        newline="\n",
    )


def _pick_x_key(z, y_key: str, y_size: int) -> str | None:
    files = list(z.files)
    valid = lambda k: k != y_key and not k.lower().startswith("unit_") and k.lower() not in {"meta", "imag", "imaginary"}

    for pred in (
        lambda kl: kl in {"x", "time", "sweep", "primary_sweep", "primarysweep", "freq"},
        lambda kl: kl.startswith("axis_"),
        lambda kl: "time" in kl or "freq" in kl or "sweep" in kl,
    ):
        for k in files:
            arr = np.asarray(z[k])
            if valid(k) and arr.ndim == 1 and arr.size == y_size and pred(k.lower()):
                return k

    for k in files:
        arr = np.asarray(z[k])
        if valid(k) and arr.ndim == 1 and arr.size == y_size:
            return k

    return None


def _result_from_npz(
    npz_path: str | Path,
    goal: float,
    worst: float,
    ext_ratio: float,
    data_range=DEFAULT_TRANSIENT_RANGE,
) -> float:
    with np.load(npz_path, allow_pickle=False) as z:
        y_key = "data" if "data" in z.files else "real" if "real" in z.files else next(
            (k for k in z.files if k.lower() in {"y", "value", "values"}),
            None,
        )
        if y_key is None:
            raise KeyError(f"No y-axis data found in {npz_path}")

        y = _as_float_1d(z[y_key])
        x_key = _pick_x_key(z, y_key, y.size)
        x = None if x_key is None else _as_float_1d(z[x_key])

    if not isinstance(data_range, (tuple, list)) or len(data_range) != 2:
        raise ValueError(f"Invalid data_range: {data_range!r}")

    start, end = data_range
    if isinstance(start, str):
        mode = start.strip().upper()
        if mode == ALL:
            values = y[np.isfinite(y)]
        elif mode == LAST:
            n = int(end)
            if n <= 0:
                raise ValueError(f"LAST data_range must use a positive count: {data_range!r}")
            values = y[-n:]
            values = values[np.isfinite(values)]
        else:
            raise ValueError(f"Unsupported data_range mode: {data_range!r}")
    else:
        lo, hi = sorted((float(start), float(end)))
        if x is None:
            raise ValueError(f"No x-axis data found in {npz_path} for data_range={tuple(data_range)!r}")
        if x.size != y.size:
            raise ValueError(f"x/y size mismatch in {npz_path}: {x.size} != {y.size}")
        values = y[np.isfinite(x) & np.isfinite(y) & (x >= lo) & (x <= hi)]

    if values.size == 0:
        raise ValueError(f"No finite data selected in {npz_path} for data_range={tuple(data_range)!r}")

    ext = float(values.max() if goal < worst else values.min())
    return ext_ratio * ext + (1.0 - ext_ratio) * float(values.mean())


def _transient_cost(
    Mxw2dApp,
    expression: str,
    goal: float,
    worst: float,
    variations,
    ext_ratio: float,
    scale: float,
    data_range=DEFAULT_TRANSIENT_RANGE,
) -> float:
    path = save_transient(
        Mxw2dApp,
        expression,
        variations=variations,
        out_dir=str(RAW_DATA_DIR),
        scale=scale,
    )
    return softmax(_result_from_npz(path, goal, worst, ext_ratio, data_range), goal, worst)


def _constraint_cost(module_name="parameters_constraints") -> float:
    vals = [v if v <= 0 else 0.0 for v in evaluate_constraints(module_name)]
    return 0.0 if not vals else float(sum(softmax(v, goal=0.0, worst=-1.0) for v in vals) / len(vals))


def main() -> None:
    bootstrap_home_dirs(BASE_DIR)
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    project_name = os.path.abspath(sorted(glob.glob(str(BASE_DIR / PROJECT_PATTERN)))[0])

    costs: list[float] = []
    Mxw2dApp = None

    #——————————————————————————————————————————————Simulation Workflow Begin——————————————————————————————————————————————————————————————
    try:
        Mxw2dApp, *_ = solver_init(projectName=project_name, designName=DESIGN_NAME, non_graphical=NON_GRAPHICAL)
        set_Mxw2d_temp_directory(Mxw2dApp, TEMP_DIR)
        set_para(Mxw2dApp, str(PARAMETER_FILE))
        analyze(Mxw2dApp, CPUcores=JOB_CPUCORE)

        for cfg in TRANSIENT_COSTS:
            costs.append(_transient_cost(Mxw2dApp, **cfg))

        costs.append(_constraint_cost(PARAMETER_FILE.stem))
    finally:
        _write_final_cost_json(COST_JSON, COST_KEYS_IN_ORDER, costs, ERROR_COST)
        save_transient(Mxw2dApp, "Moving1.Force_z", variations={"Time": ["All"]}, out_dir=str(RAW_DATA_DIR), scale=1.0)
        solver_exit(Mxw2dApp, cleanup_results=True, project_path=project_name)
        shutil.rmtree("_tmp", ignore_errors=True)
    #——————————————————————————————————————————————Simulation Workflow End——————————————————————————————————————————————————————————————

if __name__ == "__main__":
    main()