"""Optional HFSS/PyAEDT adapter.

This file is migrated from the reference project as a future backend. The
default v3 workflow does not import or call it, so normal tests do not require
PyAEDT or start HFSS.
"""

from __future__ import annotations

import glob
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

import numpy as np

_NUM_UNIT_RE = re.compile(r"^\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)\s*(.*?)\s*$")
RAWDATA_SCHEMA_VERSION = 1


def _sanitize_filename(s: str, max_len: int = 180) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1F\s]+', "_", str(s).strip()).strip(" ._")
    name = re.sub(r"_+", "_", name) or "unnamed"
    stem = os.path.splitext(name)[0].upper()
    reserved = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}
    return ("_" + name if stem in reserved else name)[:max_len]


def _value_or_call(obj: Any, name: str):
    if not hasattr(obj, name):
        return None
    value = getattr(obj, name)
    try:
        return value() if callable(value) else value
    except Exception:
        return None


def _positive_int(value) -> int | None:
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _delete_path(path: str | Path) -> None:
    path = Path(path)
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists():
        try:
            path.unlink()
        except OSError:
            pass


def _project_cleanup_targets(project_file: str | Path) -> list[Path]:
    project_file = Path(project_file).resolve()
    return [
        project_file.with_name(project_file.stem + ".aedtresults"),
        project_file.with_name(project_file.stem + ".aedtresult"),
        project_file.with_name(project_file.stem.replace(" ", "_") + ".pyaedt"),
        project_file.with_name(project_file.name + ".lock"),
    ]


def _set_variables_low_level(target: Any, tab: str, server: str, name_to_value: dict[str, str]) -> None:
    changed = ["NAME:ChangedProps"] + [["NAME:" + k, "Value:=", v] for k, v in name_to_value.items()]
    target.ChangeProperty(["NAME:AllTabs", ["NAME:" + tab, ["NAME:PropServers", server], changed]])


def _build_setup_sweep_name(hfss: Any, setup: str | None, sweep: str | None) -> str:
    if setup and ":" in setup:
        return setup
    if setup:
        return f"{setup} : {sweep}" if sweep else setup
    setups = hfss.get_setups()
    if len(setups) != 1:
        raise RuntimeError(f"Expected 1 setup, found {len(setups)}: {setups}")
    setup = setups[0]
    if sweep:
        return f"{setup} : {sweep}"
    sweeps = hfss.get_sweeps(setup) or []
    if len(sweeps) > 1:
        raise RuntimeError(f"Expected 0-1 sweeps under '{setup}', found {len(sweeps)}: {sweeps}")
    return setup if not sweeps else f"{setup} : {sweeps[0]}"


def _axis_values(values) -> tuple[np.ndarray, str]:
    out, unit = [], ""
    for x in np.asarray(values, dtype=object).ravel():
        if isinstance(x, (int, float, np.integer, np.floating)):
            out.append(float(x))
            continue
        m = _NUM_UNIT_RE.match(str(x))
        if not m:
            raise ValueError(f"Could not parse axis value {x!r}")
        out.append(float(m.group(1)))
        text = m.group(2).strip()
        if text and not unit:
            unit = text
        elif text and unit and text.lower() != unit.lower():
            raise ValueError(f"Inconsistent axis units: {unit!r} vs {text!r}")
    return np.asarray(out, dtype=float), unit


def _axis_bundle(sd: Any) -> tuple[list[str], dict[str, np.ndarray], dict[str, str]]:
    intrinsics = getattr(sd, "intrinsics", None) or {}
    units_sweeps = dict(getattr(sd, "units_sweeps", None) or {})
    axes, axis_arrays, axis_units = [], {}, {}
    for raw_name in intrinsics:
        name = str(raw_name)
        values, parsed_unit = _axis_values(intrinsics[raw_name])
        axes.append(name)
        axis_arrays[name] = values.ravel()
        axis_units[name] = str(units_sweeps.get(name, parsed_unit) or parsed_unit or "")
    return axes, axis_arrays, axis_units


def _expression_key(mapping: dict[Any, Any], expression: str):
    if expression in mapping:
        return expression
    keys = list(mapping)
    if len(keys) == 1:
        return keys[0]
    raise KeyError(f"Expression {expression!r} not found in keys {keys!r}")


def _nearest_index(values: np.ndarray, target: float) -> int:
    vals = np.asarray(values, dtype=float).ravel()
    if vals.size == 0:
        raise ValueError("empty axis")
    return int(np.argmin(np.abs(vals - float(target))))


def _nearest_indices(values: np.ndarray, coords: np.ndarray) -> tuple[np.ndarray, float]:
    vals = np.asarray(values, dtype=float).ravel()
    pts = np.asarray(coords, dtype=float).ravel()
    if vals.size == 0:
        raise ValueError("empty axis")
    if pts.size == 0:
        return np.zeros(0, dtype=int), 0.0
    if vals.size == 1:
        idx = np.zeros(pts.size, dtype=int)
        return idx, float(np.max(np.abs(pts - vals[0])))
    delta = np.diff(vals)
    if np.all(delta >= 0.0):
        pos = np.clip(np.searchsorted(vals, pts, side="left"), 0, vals.size - 1)
        prev = np.clip(pos - 1, 0, vals.size - 1)
        idx = np.where(np.abs(vals[prev] - pts) <= np.abs(vals[pos] - pts), prev, pos)
    else:
        idx = np.asarray([_nearest_index(vals, x) for x in pts], dtype=int)
    return idx.astype(int, copy=False), float(np.max(np.abs(vals[idx] - pts)))


def _active_intrinsic(sd: Any, axes: list[str], axis_arrays: dict[str, np.ndarray]) -> dict[str, float]:
    raw = dict(getattr(sd, "active_intrinsic", None) or {})
    return {ax: float(raw.get(ax, axis_arrays[ax][0])) for ax in axes if axis_arrays[ax].size}


def _extract_expression_y(sd: Any, expression: str) -> np.ndarray:
    getter = getattr(sd, "get_expression_data", None)
    if callable(getter):
        xy = getter(expression)
        data = xy[1] if isinstance(xy, (tuple, list)) and len(xy) == 2 else xy
    else:
        data_real = getattr(sd, "data_real", None)
        if not callable(data_real):
            raise AttributeError("SolutionData has neither get_expression_data nor callable data_real")
        data = data_real(expression)
    data = np.asarray(data)
    data = np.real(data) if np.iscomplexobj(data) else data
    return data.astype(float).ravel()


def _trace_contract(sd: Any, expression: str, requested_primary_sweep_variable: str | None) -> dict[str, Any]:
    data = _extract_expression_y(sd, expression)
    axes_all, axis_arrays_all, axis_units_all = _axis_bundle(sd)
    axis_lengths = {ax: int(axis_arrays_all[ax].size) for ax in axes_all}
    primary = str(getattr(sd, "primary_sweep", None) or requested_primary_sweep_variable or "").strip()
    if primary in axis_lengths and axis_lengths[primary] == int(data.size):
        return {
            "data": data.reshape((axis_lengths[primary],)),
            "axes": [primary],
            "axis_arrays": {primary: axis_arrays_all[primary]},
            "axis_units": {primary: axis_units_all.get(primary, "")},
            "primary_sweep_variable": primary,
            "data_contract": "trace",
            "source": "SolutionData trace data",
        }
    if len(axes_all) > 1:
        shape_all = tuple(axis_lengths[ax] for ax in axes_all)
        if int(np.prod(shape_all, dtype=np.int64)) == int(data.size):
            return {
                "data": data.reshape(shape_all),
                "axes": list(axes_all),
                "axis_arrays": axis_arrays_all,
                "axis_units": axis_units_all,
                "primary_sweep_variable": None,
                "data_contract": "grid",
                "source": "SolutionData trace data",
            }
    axis_name = primary if primary in axis_lengths and axis_lengths[primary] == int(data.size) else None
    if axis_name is None:
        matches = [ax for ax in axes_all if axis_lengths[ax] == int(data.size)]
        if len(matches) != 1:
            raise ValueError(
                f"Could not derive a self-consistent trace contract for {expression!r}: "
                f"data.size={int(data.size)}, primary={primary!r}, intrinsic_lengths={axis_lengths!r}"
            )
        axis_name = matches[0]
    return {
        "data": data.reshape((axis_lengths[axis_name],)),
        "axes": [axis_name],
        "axis_arrays": {axis_name: axis_arrays_all[axis_name]},
        "axis_units": {axis_name: axis_units_all.get(axis_name, "")},
        "primary_sweep_variable": axis_name,
        "data_contract": "trace",
        "source": "SolutionData trace data",
    }


def _full_matrix_contract(sd: Any, expression: str) -> dict[str, Any]:
    axes, axis_arrays, axis_units = _axis_bundle(sd)
    axis_lengths = {ax: int(axis_arrays[ax].size) for ax in axes}
    if not axes:
        raise ValueError(f"Far-field solution data for {expression!r} has no intrinsic axes")
    tables = getattr(sd, "full_matrix_real_imag", None)
    if not isinstance(tables, (tuple, list)) or len(tables) != 2 or not isinstance(tables[0], dict):
        raise ValueError(f"SolutionData.full_matrix_real_imag is unavailable for {expression!r}")
    raw_table = tables[0][_expression_key(tables[0], expression)]
    if isinstance(raw_table, dict):
        rows = []
        for raw_coords, value in raw_table.items():
            coords = tuple(raw_coords) if isinstance(raw_coords, (tuple, list)) else (raw_coords,)
            if len(coords) < len(axes):
                raise ValueError(
                    f"Unexpected far-field coordinate key for {expression!r}: "
                    f"coords={coords!r}, axes={axes!r}"
                )
            rows.append(tuple(coords[-len(axes) :]) + (value,))
        table = np.asarray(rows, dtype=float)
    else:
        table = np.asarray(raw_table, dtype=float)
    if table.ndim != 2 or table.shape[1] != len(axes) + 1:
        raise ValueError(
            f"Unexpected far-field full matrix shape for {expression!r}: "
            f"table_shape={tuple(int(x) for x in table.shape)}, axes={axes!r}"
        )
    shape = tuple(axis_lengths[ax] for ax in axes)
    index_cols, match_error = [], {}
    for col, ax in enumerate(axes):
        idx, err = _nearest_indices(axis_arrays[ax], table[:, col])
        index_cols.append(idx)
        match_error[ax] = err
    bad_match = {
        ax: err
        for ax, err in match_error.items()
        if err > 1e-9 * max(1.0, float(np.max(np.abs(axis_arrays[ax]))))
    }
    if bad_match:
        raise ValueError(
            f"Far-field full matrix coordinates do not align with intrinsic axes for {expression!r}: {bad_match!r}"
        )
    linear = np.ravel_multi_index(tuple(index_cols), shape)
    expected = int(np.prod(shape, dtype=np.int64))
    unique = int(np.unique(linear).size)
    if unique != int(table.shape[0]) or unique != expected:
        raise ValueError(
            f"Could not reconstruct a complete far-field grid for {expression!r}: "
            f"rows={int(table.shape[0])}, unique_points={unique}, expected_points={expected}, "
            f"axis_lengths={axis_lengths!r}, match_error={match_error!r}"
        )
    data = np.empty(shape, dtype=float)
    data[tuple(index_cols)] = table[:, len(axes)]
    return {
        "data": data,
        "axes": list(axes),
        "axis_arrays": axis_arrays,
        "axis_units": axis_units,
        "primary_sweep_variable": None,
        "data_contract": "grid",
        "source": "SolutionData.full_matrix_real_imag",
        "active_intrinsic": _active_intrinsic(sd, axes, axis_arrays),
    }


def _axis_descriptors(
    axes: list[str],
    axis_arrays: dict[str, np.ndarray],
    axis_units: dict[str, str],
    shape: tuple[int, ...],
) -> list[dict[str, object]]:
    if len(axes) != len(shape):
        return [{"index": index, "size": int(size)} for index, size in enumerate(shape)]

    descriptors: list[dict[str, object]] = []
    for index, axis_name in enumerate(axes):
        descriptor: dict[str, object] = {
            "index": int(index),
            "size": int(shape[index]),
            "name": str(axis_name),
        }
        values = np.asarray(axis_arrays.get(axis_name, ()), dtype=float).ravel()
        if values.size == int(shape[index]):
            descriptor["values_key"] = f"axis_{axis_name}"
        unit = str(axis_units.get(axis_name, "") or "")
        if unit:
            descriptor["unit"] = unit
            descriptor["unit_key"] = f"unit_{axis_name}"
        descriptors.append(descriptor)
    return descriptors


def _export_solution_data_npz(
    hfss: Any,
    *,
    expression: str,
    report_category: str | None = None,
    context: Any = None,
    variations: dict[str, str | list[str]] | None = None,
    primary_sweep_variable: str | None = None,
    setup: str | None = None,
    sweep: str | None = None,
    out_dir: str = "rawData",
) -> str:
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{_sanitize_filename(expression)}.npz")
    setup_sweep_name = _build_setup_sweep_name(hfss, setup, sweep)
    vrs = None if not variations else {
        str(k): [str(x) for x in (v if isinstance(v, (list, tuple, np.ndarray)) else [v])]
        for k, v in variations.items()
    }
    is_far_field = str(report_category or "") == "Far Fields"
    wants_trace_contract = bool(str(primary_sweep_variable or "").strip())
    sd = hfss.post.get_solution_data(
        expressions=expression,
        setup_sweep_name=setup_sweep_name,
        report_category=report_category,
        context=context,
        variations=vrs,
        primary_sweep_variable=primary_sweep_variable,
    )
    if sd is None or sd is False:
        raise RuntimeError(f"get_solution_data returned {sd!r} for {expression!r}")
    contract = (
        _full_matrix_contract(sd, expression)
        if is_far_field and not wants_trace_contract
        else _trace_contract(sd, expression, primary_sweep_variable)
    )
    data = np.asarray(contract["data"], dtype=float)
    axis_names = list(contract["axes"])
    meta = {
        "schema_version": RAWDATA_SCHEMA_VERSION,
        "rawdata_name": _sanitize_filename(expression),
        "expression": expression,
        "report_category": report_category,
        "context": context,
        "setup_sweep_name": setup_sweep_name,
        "primary_sweep_variable": contract.get("primary_sweep_variable"),
        "axis_names": axis_names,
        "axes": _axis_descriptors(
            axis_names,
            contract["axis_arrays"],
            contract["axis_units"],
            tuple(int(x) for x in data.shape),
        ),
        "shape": [int(x) for x in data.shape],
        "data_contract": contract["data_contract"],
        "source": contract["source"],
    }
    if contract.get("active_intrinsic"):
        meta["active_intrinsic"] = contract["active_intrinsic"]
    save_kw = {
        "data": data,
        "metadata": json.dumps(meta, ensure_ascii=True, default=str),
        "meta": json.dumps(meta, ensure_ascii=True, default=str),
    }
    for ax in contract["axes"]:
        save_kw[f"axis_{ax}"] = np.asarray(contract["axis_arrays"][ax], dtype=float)
        save_kw[f"unit_{ax}"] = np.asarray(str(contract["axis_units"].get(ax, "")))
    tmp = path + ".tmp.npz"
    np.savez_compressed(tmp, **save_kw)
    os.replace(tmp, path)
    return path


def set_hfss_temp_directory(hfssApp: Any, path: str | Path | None = None) -> bool:
    temp = Path(path or os.environ.get("TEMP") or os.environ.get("TMP") or "").resolve()
    os.makedirs(temp, exist_ok=True)
    return bool(hfssApp.set_temporary_directory(str(temp)))


def get_desktop_pid(hfssApp: Any) -> int | None:
    seen, queue = set(), [hfssApp]
    while queue:
        obj = queue.pop(0)
        if obj is None or id(obj) in seen:
            continue
        seen.add(id(obj))
        for name in ("aedt_process_id", "process_id", "pid", "GetProcessID"):
            pid = _positive_int(_value_or_call(obj, name))
            if pid is not None:
                return pid
        for name in ("desktop_class", "_desktop_class", "odesktop", "_odesktop", "_desktop"):
            queue.append(getattr(obj, name, None))
    return None


def solver_init(
    projectName: str | None = None,
    designName: str | None = None,
    *,
    non_graphical: bool = True,
    new_desktop: bool = True,
    close_on_exit: bool = False,
    remove_lock: bool = True,
) -> list[Any]:
    from ansys.aedt.core import Hfss

    projectName = projectName or sorted(glob.glob("*.aedt"))[0]
    hfss = Hfss(
        project=projectName,
        design=designName,
        non_graphical=non_graphical,
        new_desktop=new_desktop,
        close_on_exit=close_on_exit,
        remove_lock=remove_lock,
    )
    if designName is None:
        designs = hfss.design_list or []
        if len(designs) != 1:
            raise RuntimeError(f"Expected 1 design, found {len(designs)}: {designs}")
        designName = designs[0]
    return [hfss, projectName, designName]


def _load_parameters_py_value_only(path: str) -> dict[str, str]:
    import math
    import runpy
    import sys

    folder = os.path.abspath(os.path.dirname(path))
    sys.path.insert(0, folder)
    try:
        params = runpy.run_path(path).get("PARAMETERS")
    finally:
        try:
            sys.path.remove(folder)
        except ValueError:
            pass
    if params is None:
        raise ValueError(f"{path!r} does not define PARAMETERS")
    out = {}
    for p in params:
        name, unit, value = str(p.name), str(getattr(p, "unit", "") or ""), float(p.value)
        if math.isnan(value):
            raise ValueError(f"Parameter {name!r} value is NaN")
        out[name] = f"{value:g}{unit}" if unit else f"{value:g}"
    return out


def set_variables(hfssApp: Any, name_to_value) -> bool:
    values = {str(k): str(v) for k, v in dict(name_to_value or {}).items()}
    if not values:
        return True
    proj = {k: v for k, v in values.items() if k.startswith("$")}
    local = {k: v for k, v in values.items() if not k.startswith("$")}
    if proj:
        _set_variables_low_level(hfssApp._oproject, "ProjectVariableTab", "ProjectVariables", proj)
    if local:
        _set_variables_low_level(hfssApp._odesign, "LocalVariableTab", "LocalVariables", local)
    return True


def set_para(hfssApp: Any, paraFile: str = "parameters_constraints.py") -> bool:
    return set_variables(hfssApp, _load_parameters_py_value_only(paraFile))


def analyze(
    hfssApp: Any,
    analyzeSetup: str | None = None,
    CPUcores: int = 4,
    ParallelTasks: int = 1,
    allocGPUs: int | None = None,
) -> bool:
    if analyzeSetup is None:
        setups = hfssApp.get_setups()
        if len(setups) != 1:
            raise RuntimeError(f"Expected 1 setup, found {len(setups)}: {setups}")
        analyzeSetup = setups[0]
    ok = hfssApp.analyze_setup(
        name=analyzeSetup,
        cores=CPUcores,
        tasks=ParallelTasks,
        gpus=allocGPUs,
        use_auto_settings=False,
    )
    if not ok:
        raise RuntimeError(f"analyze_setup returned False for '{analyzeSetup}'")
    return True


def save_modal(
    hfssApp: Any,
    expression: str,
    *,
    variations: dict[str, str | list[str]] | None = None,
    primary_sweep_variable: str | None = None,
    setup: str | None = None,
    sweep: str | None = None,
    out_dir: str = "rawData",
) -> str:
    return _export_solution_data_npz(
        hfssApp,
        expression=expression,
        report_category="Modal Solution Data",
        variations=variations or {"Freq": ["All"]},
        primary_sweep_variable=primary_sweep_variable,
        setup=setup,
        sweep=sweep,
        out_dir=out_dir,
    )


def save_nearField(
    hfssApp: Any,
    expression: str,
    *,
    context: str = "Line1",
    variations: dict[str, str | list[str]] | None = None,
    primary_sweep_variable: str | None = None,
    setup: str | None = None,
    sweep: str | None = None,
    out_dir: str = "rawData",
) -> str:
    return _export_solution_data_npz(
        hfssApp,
        expression=expression,
        report_category="Near Fields",
        context=context,
        variations=variations or {"NormalizedDistance": ["All"], "Freq": ["All"]},
        primary_sweep_variable=primary_sweep_variable,
        setup=setup,
        sweep=sweep,
        out_dir=out_dir,
    )


def save_farField(
    hfssApp: Any,
    expression: str,
    *,
    context: str = "3D",
    variations: dict[str, str | list[str]] | None = None,
    primary_sweep_variable: str | None = None,
    setup: str | None = None,
    sweep: str | None = None,
    out_dir: str = "rawData",
) -> str:
    return _export_solution_data_npz(
        hfssApp,
        expression=expression,
        report_category="Far Fields",
        context=context,
        variations=variations or {"Theta": ["All"], "Phi": ["All"], "Freq": ["All"]},
        primary_sweep_variable=primary_sweep_variable,
        setup=setup,
        sweep=sweep,
        out_dir=out_dir,
    )


def save_antPara(
    hfssApp: Any,
    expression: str,
    *,
    variations: dict[str, str | list[str]] | None = None,
    primary_sweep_variable: str | None = None,
    setup: str | None = None,
    sweep: str | None = None,
    out_dir: str = "rawData",
) -> str:
    return _export_solution_data_npz(
        hfssApp,
        expression=expression,
        report_category="Antenna Parameters",
        variations=variations or {"Freq": ["All"]},
        primary_sweep_variable=primary_sweep_variable,
        setup=setup,
        sweep=sweep,
        out_dir=out_dir,
    )


def solver_exit(
    hfssApp: Any,
    *,
    save_project: bool = True,
    cleanup_results: bool = True,
    project_path: str | Path | None = None,
) -> bool:
    if hfssApp is None:
        return False
    project_file = str(project_path or getattr(hfssApp, "project_file", "") or "")
    cleanup_targets = _project_cleanup_targets(project_file) if project_file else []
    try:
        if save_project and hasattr(hfssApp, "save_project"):
            hfssApp.save_project()
    finally:
        try:
            release_desktop = getattr(hfssApp, "release_desktop", None)
            if callable(release_desktop):
                release_desktop()
        finally:
            if cleanup_results:
                for target in cleanup_targets:
                    _delete_path(target)
    return True


__all__ = [
    "set_hfss_temp_directory",
    "get_desktop_pid",
    "solver_init",
    "set_variables",
    "set_para",
    "analyze",
    "save_modal",
    "save_nearField",
    "save_farField",
    "save_antPara",
    "solver_exit",
]
