"""HFSS workflow entry point for the Metal_recon_ant task.

The workflow owns only ``variables -> rawData``. Objective calculation lives in
``calc_cost.py`` after rawData has been recorded.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

BASE_DIR = Path(__file__).resolve().parent

try:
    from .hfss_com import (
        analyze,
        get_desktop_pid,
        save_farField,
        save_modal,
        set_hfss_temp_directory,
        set_variables,
        solver_exit,
        solver_init,
    )
except ImportError:  # Allows copied job folders to run workflow.py directly.
    from hfss_com import (
        analyze,
        get_desktop_pid,
        save_farField,
        save_modal,
        set_hfss_temp_directory,
        set_variables,
        solver_exit,
        solver_init,
    )

try:
    from .parameters_constraints import get_parameters
    from .rawdata_contract import RAWDATA_SCHEMA_VERSION, validate_rawdata_directory
except ImportError:  # Allows copied job folders to run workflow.py directly.
    from parameters_constraints import get_parameters
    from rawdata_contract import RAWDATA_SCHEMA_VERSION, validate_rawdata_directory


RAWDATA_DIR = BASE_DIR / "rawData"
INDIVIDUAL_METADATA_PATH = BASE_DIR / "individual_metadata.json"
INDIVIDUAL_METADATA_SCHEMA_VERSION = 1

PROJECT_NAME = "Metal_recon_ant.aedt"
PROJECT_PATH = BASE_DIR / PROJECT_NAME
DESIGN_NAME = "HFSSDesign1"
SETUP_NAME = "Setup1"
SWEEP_NAME = "Sweep"
S11_SOLUTION_NAME = f"{SETUP_NAME} : {SWEEP_NAME}"
GAIN_SOLUTION_NAME = f"{SETUP_NAME} : LastAdaptive"
GAIN_CONTEXT = "3D"
PIN_STATE_VAR = "pinState"

PIN_STATES = (1, 2, 3, 4)
S11_EXPR = "dB(S(1,1))"
GAIN_EXPR = "dB(RealizedGainTotal)"
TARGET_FREQ_GHZ = 2.44
TARGET_PHI_DEG = 90.0
CHILD_ENV = "WORKFLOW_CHILD_MODE"

JOB_CPUCORE = int(os.environ.get("YADOT_HFSS_JOB_CPUCORE", "4"))
JOB_TIMEOUT_SEC = float(os.environ.get("YADOT_HFSS_WORKFLOW_TIMEOUT_SEC", str(60.0 * 60.0)))
NON_GRAPHICAL = os.environ.get("YADOT_HFSS_NON_GRAPHICAL", "1").strip().lower() not in {"0", "false", "no"}


def _variables_mapping(variables: Mapping[str, float] | Sequence[float]) -> dict[str, float]:
    if isinstance(variables, Mapping):
        return {str(name): float(value) for name, value in variables.items()}
    names = [parameter.name for parameter in get_parameters()]
    values = tuple(float(value) for value in variables)
    if len(names) != len(values):
        raise ValueError(f"expected {len(names)} variables, got {len(values)}")
    return dict(zip(names, values))


def _hfss_variable_values(variable_map: Mapping[str, float]) -> dict[str, str]:
    units = {parameter.name: str(getattr(parameter, "unit", "") or "") for parameter in get_parameters()}
    out: dict[str, str] = {}
    for name, value in variable_map.items():
        unit = units.get(name, "")
        out[name] = f"{float(value):.17g}{unit}" if unit else f"{float(value):.17g}"
    return out


def _metadata_json(metadata: Mapping[str, object]) -> np.ndarray:
    return np.asarray(json.dumps(dict(metadata), ensure_ascii=False), dtype=np.str_)


def run_workflow(
    variables: Mapping[str, float] | Sequence[float],
    output_dir: str | Path | None = None,
    job_metadata: Mapping[str, object] | None = None,
) -> tuple[Path, ...]:
    rawdata_dir = Path(output_dir) if output_dir is not None else RAWDATA_DIR
    _prepare_rawdata_dir(rawdata_dir)
    variable_map = _variables_mapping(variables)

    bootstrap_home_dirs(BASE_DIR)
    hfss_app = None
    try:
        hfss_app, *_ = solver_init(
            projectName=str(PROJECT_PATH),
            designName=DESIGN_NAME,
            non_graphical=bool(NON_GRAPHICAL),
        )
        _update_individual_metadata(desktop_pid=get_desktop_pid(hfss_app))
        set_hfss_temp_directory(hfss_app, os.environ["TEMP"])
        _simulate(hfss_app, variable_map, rawdata_dir)
    finally:
        if hfss_app is not None:
            solver_exit(hfss_app, save_project=False, cleanup_results=True, project_path=PROJECT_PATH)
            _update_individual_metadata(desktop_pid=None)
        cleanup_tmp_dir(BASE_DIR)

    return validate_rawdata_directory(rawdata_dir)


def _prepare_rawdata_dir(rawdata_dir: Path) -> None:
    rawdata_dir.mkdir(parents=True, exist_ok=True)
    subdirs = [path for path in rawdata_dir.iterdir() if path.is_dir()]
    if subdirs:
        names = ", ".join(path.name for path in sorted(subdirs, key=lambda p: p.name.lower()))
        raise ValueError(f"rawData directory must be flat; found subdirectories: {names}")
    for path in rawdata_dir.glob("*.npz"):
        path.unlink()


def _simulate(hfss_app, variable_map: Mapping[str, float], rawdata_dir: Path) -> None:
    set_variables(hfss_app, _hfss_variable_values(variable_map))
    for pin_state in PIN_STATES:
        _run_state(hfss_app, pin_state, rawdata_dir)


def _run_state(hfss_app, pin_state: int, rawdata_dir: Path) -> tuple[Path, Path]:
    set_variables(hfss_app, {PIN_STATE_VAR: str(int(pin_state))})
    analyze(hfss_app, analyzeSetup=SETUP_NAME, CPUcores=int(JOB_CPUCORE))

    s11_source = Path(save_modal(hfss_app, S11_EXPR, setup=S11_SOLUTION_NAME, out_dir=str(rawdata_dir)))
    s11_path = _rewrite_rawdata_file(
        s11_source,
        rawdata_dir / f"s11_pinState{pin_state}.npz",
        rawdata_name=f"s11_pinState{pin_state}",
        pin_state=pin_state,
        hfss_quantity="s11",
    )

    gain_source = Path(
        save_farField(
            hfss_app,
            GAIN_EXPR,
            context=GAIN_CONTEXT,
            variations={"Theta": ["All"], "Phi": [f"{TARGET_PHI_DEG:g}deg"], "Freq": [f"{TARGET_FREQ_GHZ:g}GHz"]},
            primary_sweep_variable="Theta",
            setup=GAIN_SOLUTION_NAME,
            out_dir=str(rawdata_dir),
        )
    )
    gain_path = _rewrite_rawdata_file(
        gain_source,
        rawdata_dir / f"gain_pinState{pin_state}.npz",
        rawdata_name=f"gain_pinState{pin_state}",
        pin_state=pin_state,
        hfss_quantity="realized_gain_total",
    )
    return s11_path, gain_path


def _rewrite_rawdata_file(source: Path, target: Path, **metadata_updates: object) -> Path:
    with np.load(source, allow_pickle=False) as npz:
        payload = {key: npz[key].copy() for key in npz.files}

    metadata = _metadata_from_payload(payload)
    data_key = "data" if "data" in payload else "values"
    if data_key not in payload:
        raise ValueError(f"rawData file {source} has no data or values array")
    data_shape = tuple(int(value) for value in np.asarray(payload[data_key]).shape)
    axis_names = _axis_names_from_metadata(metadata)
    metadata.update(metadata_updates)
    metadata.update(
        {
            "schema_version": RAWDATA_SCHEMA_VERSION,
            "shape": list(data_shape),
            "axis_names": axis_names,
            "axes": _axis_descriptors(payload, axis_names, data_shape),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    payload["metadata"] = _metadata_json(metadata)
    payload["meta"] = _metadata_json(metadata)

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target.with_name(target.name + ".tmp.npz")
    np.savez_compressed(tmp_path, **payload)
    os.replace(tmp_path, target)
    if source.resolve() != target.resolve() and source.exists():
        source.unlink()
    return target


def _metadata_from_payload(payload: Mapping[str, object]) -> dict[str, object]:
    raw = payload.get("metadata", payload.get("meta"))
    if raw is None:
        return {}
    if isinstance(raw, np.ndarray):
        if raw.shape != ():
            return {}
        raw = raw.item()
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    if isinstance(raw, str):
        try:
            loaded = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return dict(loaded) if isinstance(loaded, Mapping) else {}
    return dict(raw) if isinstance(raw, Mapping) else {}


def _axis_names_from_metadata(metadata: Mapping[str, object]) -> list[str]:
    raw_names = metadata.get("axis_names")
    if isinstance(raw_names, Sequence) and not isinstance(raw_names, (str, bytes, Mapping)):
        return [str(name) for name in raw_names]
    raw_axes = metadata.get("axes")
    if isinstance(raw_axes, Sequence) and not isinstance(raw_axes, (str, bytes, Mapping)):
        names: list[str] = []
        for item in raw_axes:
            if isinstance(item, Mapping):
                names.append(str(item.get("name", item.get("values_key", len(names)))))
            else:
                names.append(str(item))
        return names
    return []


def _axis_descriptors(payload: Mapping[str, object], axis_names: Sequence[str], shape: Sequence[int]) -> list[dict[str, object]]:
    names = [str(name) for name in axis_names]
    if len(names) != len(shape):
        return [{"index": index, "size": int(size)} for index, size in enumerate(shape)]
    descriptors: list[dict[str, object]] = []
    for index, name in enumerate(names):
        descriptor: dict[str, object] = {"index": int(index), "size": int(shape[index]), "name": name}
        values_key = f"axis_{name}"
        values = np.asarray(payload.get(values_key, ())).ravel()
        if values.size == int(shape[index]):
            descriptor["values_key"] = values_key
        unit_key = f"unit_{name}"
        if unit_key in payload:
            unit = _scalar_text(payload[unit_key])
            if unit:
                descriptor["unit"] = unit
                descriptor["unit_key"] = unit_key
        descriptors.append(descriptor)
    return descriptors


def _scalar_text(value: object) -> str:
    array = np.asarray(value)
    if array.shape == ():
        return str(array.item())
    return str(value)


def _load_job_payload() -> tuple[Mapping[str, float] | Sequence[float], str, dict[str, object]]:
    variables_path = BASE_DIR / "variables.json"
    job_input_path = BASE_DIR / "job_input.json"
    job_name = BASE_DIR.name
    context: dict[str, object] = {}
    if variables_path.exists():
        variables = json.loads(variables_path.read_text(encoding="utf-8"))
    elif job_input_path.exists():
        payload = json.loads(job_input_path.read_text(encoding="utf-8"))
        job_name = str(payload.get("job_name") or job_name)
        raw_context = payload.get("evaluation_context", {})
        if isinstance(raw_context, Mapping):
            context = {str(key): value for key, value in raw_context.items()}
        variables = payload.get("unnormalized_variables", payload.get("raw_variables"))
        if variables is None:
            raise ValueError(f"{job_input_path} must contain unnormalized_variables")
    else:
        raise FileNotFoundError(f"missing variables file: {variables_path} or {job_input_path}")
    return variables, job_name, context


def _run_child() -> int:
    variables, _job_name, _context = _load_job_payload()
    _update_individual_metadata(
        status="running",
        engine="hfss",
        is_surrogate=False,
        surrogate_uncertainty=None,
        non_graphical=bool(NON_GRAPHICAL),
        workflow_child_pid=os.getpid(),
        desktop_pid=None,
        timed_out=False,
    )
    try:
        saved_paths = run_workflow(variables)
    except Exception as exc:
        _update_individual_metadata(
            status="error",
            ended_at=_now_text(),
            error_type=type(exc).__name__,
            error_message=str(exc),
            timed_out=False,
        )
        raise
    _update_individual_metadata(
        status="done",
        ended_at=_now_text(),
        raw_data_files=[path.name for path in saved_paths],
        timed_out=False,
    )
    return 0


def _run_supervisor() -> int:
    env = os.environ.copy()
    env[CHILD_ENV] = "1"
    proc = subprocess.Popen([sys.executable, "-u", Path(__file__).name], cwd=str(BASE_DIR), env=env)
    _update_individual_metadata(workflow_pid=os.getpid(), workflow_child_pid=int(proc.pid), timed_out=False)

    try:
        rc = proc.wait(timeout=float(JOB_TIMEOUT_SEC))
    except subprocess.TimeoutExpired:
        _kill_pid_tree(proc.pid)
        _kill_pid_tree(_desktop_pid_from_metadata())
        _cleanup_runtime_files()
        _update_individual_metadata(status="timeout", ended_at=_now_text(), timed_out=True)
        return 1

    if rc != 0:
        _cleanup_runtime_files(attempts=1)
        if any(target.exists() for target in _runtime_leftovers()):
            _kill_pid_tree(_desktop_pid_from_metadata())
            _cleanup_runtime_files()
        metadata = _read_individual_metadata()
        if "ended_at" not in metadata:
            _update_individual_metadata(status="error", ended_at=_now_text(), timed_out=False)
        return rc or 1

    _cleanup_runtime_files()
    return 0


def main() -> int:
    if os.environ.get(CHILD_ENV) == "1":
        return _run_child()

    _variables, job_name, context = _load_job_payload()
    _update_individual_metadata(
        schema_version=INDIVIDUAL_METADATA_SCHEMA_VERSION,
        job_name=job_name,
        status="running",
        started_at=_now_text(),
        **context,
    )
    return _run_supervisor()


def bootstrap_home_dirs(base: Path) -> None:
    tmp = base / "_tmp"
    for key, path in {
        "USERPROFILE": base / "_home",
        "HOME": base / "_home",
        "APPDATA": base / "_appdata",
        "LOCALAPPDATA": base / "_localappdata",
        "TEMP": tmp,
        "TMP": tmp,
        "TMPDIR": tmp,
    }.items():
        os.environ[key] = str(path)
        path.mkdir(parents=True, exist_ok=True)


def cleanup_tmp_dir(base: str | Path) -> None:
    shutil.rmtree(Path(base) / "_tmp", ignore_errors=True)


def _project_cleanup_targets() -> list[Path]:
    return [
        PROJECT_PATH.with_name(PROJECT_PATH.stem + ".aedtresults"),
        PROJECT_PATH.with_name(PROJECT_PATH.stem + ".aedtresult"),
        PROJECT_PATH.with_name(PROJECT_PATH.stem.replace(" ", "_") + ".pyaedt"),
        PROJECT_PATH.with_name(PROJECT_PATH.name + ".lock"),
    ]


def _runtime_leftovers() -> list[Path]:
    return [BASE_DIR / "_tmp", *_project_cleanup_targets()]


def _cleanup_runtime_files(attempts: int = 3, delay_sec: float = 0.5) -> None:
    for index in range(max(1, int(attempts))):
        cleanup_tmp_dir(BASE_DIR)
        for target in _project_cleanup_targets():
            _delete_path(target)
        if not any(target.exists() for target in _runtime_leftovers()):
            return
        if index + 1 < int(attempts):
            time.sleep(float(delay_sec))


def _delete_path(path: str | Path) -> None:
    path = Path(path)
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists():
        try:
            path.unlink()
        except OSError:
            pass


def _desktop_pid_from_metadata() -> int | None:
    return _maybe_int(_read_individual_metadata().get("desktop_pid"))


def _process_exists(pid) -> bool:
    pid = _maybe_int(pid)
    if pid is None:
        return False
    if os.name != "nt":
        return True
    out = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    return str(pid) in out


def _kill_pid_tree(pid) -> None:
    pid = _maybe_int(pid)
    if pid is None or not _process_exists(pid):
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    else:
        try:
            os.kill(pid, 9)
        except OSError:
            pass


def _maybe_int(value) -> int | None:
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _update_individual_metadata(**update: object) -> None:
    metadata = _read_individual_metadata()
    metadata.update(dict(update))
    temp_path = INDIVIDUAL_METADATA_PATH.with_suffix(INDIVIDUAL_METADATA_PATH.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(metadata, ensure_ascii=True, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    temp_path.replace(INDIVIDUAL_METADATA_PATH)


def _read_individual_metadata() -> dict[str, object]:
    if not INDIVIDUAL_METADATA_PATH.is_file():
        return {}
    try:
        loaded = json.loads(INDIVIDUAL_METADATA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(loaded) if isinstance(loaded, dict) else {}


def _now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


if __name__ == "__main__":
    raise SystemExit(main())
