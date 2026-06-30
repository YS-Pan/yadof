from __future__ import annotations

import json
import os
import getpass
import platform
import shutil
import subprocess
import sys
import time
import traceback
import zipfile
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path

import numpy as np

from hfss_com import analyze, save_farField, save_modal, set_hfss_temp_directory, set_variables, solver_exit, solver_init
from parameters_constraints import get_parameters


BASE_DIR = Path(__file__).resolve().parent
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
RAW_DATA_DIR = BASE_DIR / "rawData"
RAW_DATA_TRANSFER_ZIP = BASE_DIR / "rawData_outputs.zip"
TEMP_DIR = BASE_DIR / "_tmp"
INDIVIDUAL_METADATA = BASE_DIR / "individual_metadata.json"

DEFAULT_JOB_CPUCORE = 4
DEFAULT_PARALLEL_TASKS = 1
DEFAULT_NON_GRAPHICAL = True
DEFAULT_PIN_RETRIES = 1
DEFAULT_RETRY_CPUCORE = 1
DEFAULT_RETRY_DELAY_SEC = 5.0


def _env_int(name: str, default: int, *, minimum: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return max(minimum, int(raw))


def _env_float(name: str, default: float, *, minimum: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return max(minimum, float(raw))


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


JOB_CPUCORE = _env_int("YADOT_HFSS_JOB_CPUCORE", DEFAULT_JOB_CPUCORE, minimum=1)
PARALLEL_TASKS = _env_int("YADOT_HFSS_PARALLEL_TASKS", DEFAULT_PARALLEL_TASKS, minimum=1)
NON_GRAPHICAL = _env_bool("YADOT_HFSS_NON_GRAPHICAL", DEFAULT_NON_GRAPHICAL)
PIN_RETRIES = _env_int("YADOT_HFSS_PIN_RETRIES", DEFAULT_PIN_RETRIES, minimum=0)
RETRY_CPUCORE = _env_int("YADOT_HFSS_RETRY_CPUCORE", DEFAULT_RETRY_CPUCORE, minimum=1)
RETRY_DELAY_SEC = _env_float("YADOT_HFSS_RETRY_DELAY_SEC", DEFAULT_RETRY_DELAY_SEC, minimum=0.0)


def _now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def _write_json(path: str | Path, data: Mapping[str, object]) -> None:
    Path(path).write_text(json.dumps(dict(data), ensure_ascii=True, indent=2), encoding="utf-8", newline="\n")


def _raw_data_file_names() -> list[str]:
    return [path.name for path in sorted(RAW_DATA_DIR.glob("*.npz"))]


def _bootstrap_home_dirs() -> None:
    for key, path in {
        "USERPROFILE": BASE_DIR / "_home",
        "HOME": BASE_DIR / "_home",
        "APPDATA": BASE_DIR / "_appdata",
        "LOCALAPPDATA": BASE_DIR / "_localappdata",
        "TEMP": TEMP_DIR,
        "TMP": TEMP_DIR,
        "TMPDIR": TEMP_DIR,
    }.items():
        os.environ[key] = str(path)
        path.mkdir(parents=True, exist_ok=True)


def _runtime_identity() -> dict[str, str]:
    try:
        whoami = subprocess.run(
            ["whoami"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).stdout.strip()
    except Exception:
        whoami = ""
    return {
        "runtime_user": getpass.getuser(),
        "runtime_whoami": whoami,
        "runtime_cwd": str(BASE_DIR),
        "runtime_python_executable": sys.executable,
        "runtime_platform": platform.platform(),
        "runtime_condor_scratch_dir": os.environ.get("_CONDOR_SCRATCH_DIR", ""),
        "runtime_userprofile": os.environ.get("USERPROFILE", ""),
        "runtime_appdata": os.environ.get("APPDATA", ""),
        "runtime_localappdata": os.environ.get("LOCALAPPDATA", ""),
        "runtime_temp": os.environ.get("TEMP", ""),
        "runtime_ansys_license": os.environ.get("ANSYSLMD_LICENSE_FILE", ""),
        "runtime_hfss_job_cpucore": str(JOB_CPUCORE),
        "runtime_hfss_retry_cpucore": str(RETRY_CPUCORE),
        "runtime_hfss_pin_retries": str(PIN_RETRIES),
    }


def _load_variables() -> Mapping[str, float] | Sequence[float]:
    variables_path = BASE_DIR / "variables.json"
    if variables_path.is_file():
        return json.loads(variables_path.read_text(encoding="utf-8"))
    payload = json.loads((BASE_DIR / "job_input.json").read_text(encoding="utf-8"))
    return payload["unnormalized_variables"] if "unnormalized_variables" in payload else payload["raw_variables"]


def _hfss_variables(variables: Mapping[str, float] | Sequence[float]) -> dict[str, str]:
    parameters = get_parameters()
    units = {parameter.name: str(getattr(parameter, "unit", "") or "") for parameter in parameters}
    if isinstance(variables, Mapping):
        values = variables.items()
    else:
        raw_values = tuple(float(value) for value in variables)
        if len(raw_values) != len(parameters):
            raise ValueError(f"expected {len(parameters)} variables, got {len(raw_values)}")
        values = zip((parameter.name for parameter in parameters), raw_values)
    return {str(name): f"{float(value):.17g}{units.get(str(name), '')}" for name, value in values}


def _prepare_rawdata_dir() -> None:
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    for path in RAW_DATA_DIR.glob("*.npz"):
        path.unlink()
    RAW_DATA_TRANSFER_ZIP.unlink(missing_ok=True)


def _write_rawdata_transfer_zip() -> None:
    files = sorted(RAW_DATA_DIR.glob("*.npz"))
    if not files:
        RAW_DATA_TRANSFER_ZIP.unlink(missing_ok=True)
        return
    tmp_path = RAW_DATA_TRANSFER_ZIP.with_name(RAW_DATA_TRANSFER_ZIP.name + ".tmp")
    with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_STORED) as archive:
        for path in files:
            archive.write(path, arcname=path.name)
    os.replace(tmp_path, RAW_DATA_TRANSFER_ZIP)


def _tag_rawdata(source: str | Path, target: str | Path, **metadata_updates: object) -> Path:
    source, target = Path(source), Path(target)
    with np.load(source, allow_pickle=False) as z:
        payload = {key: z[key].copy() for key in z.files}
    metadata = json.loads(str(np.asarray(payload["metadata"]).item()))
    metadata.update(metadata_updates)
    payload["metadata"] = np.asarray(json.dumps(metadata, ensure_ascii=True), dtype=np.str_)
    payload["meta"] = payload["metadata"]
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target.with_name(target.name + ".tmp.npz")
    np.savez_compressed(tmp_path, **payload)
    os.replace(tmp_path, target)
    if source.resolve() != target.resolve():
        source.unlink(missing_ok=True)
    return target


def _save_pin_state_rawdata(hfssApp, pin_state: int, *, cpu_cores: int) -> None:
    set_variables(hfssApp, {PIN_STATE_VAR: str(int(pin_state))})
    analyze(hfssApp, analyzeSetup=SETUP_NAME, CPUcores=cpu_cores, ParallelTasks=PARALLEL_TASKS)
    _tag_rawdata(save_modal(hfssApp, S11_EXPR, setup=S11_SOLUTION_NAME, out_dir=str(RAW_DATA_DIR)), RAW_DATA_DIR / f"s11_pinState{pin_state}.npz", rawdata_name=f"s11_pinState{pin_state}", pin_state=pin_state, hfss_quantity="s11")
    _tag_rawdata(save_farField(hfssApp, GAIN_EXPR, context=GAIN_CONTEXT, variations={"Theta": ["All"], "Phi": [f"{TARGET_PHI_DEG:g}deg"], "Freq": [f"{TARGET_FREQ_GHZ:g}GHz"]}, primary_sweep_variable="Theta", setup=GAIN_SOLUTION_NAME, out_dir=str(RAW_DATA_DIR)), RAW_DATA_DIR / f"gain_pinState{pin_state}.npz", rawdata_name=f"gain_pinState{pin_state}", pin_state=pin_state, hfss_quantity="realized_gain_total")


def _start_hfss(hfss_variables: Mapping[str, str]):
    hfss_app, *_ = solver_init(projectName=str(PROJECT_PATH), designName=DESIGN_NAME, non_graphical=NON_GRAPHICAL)
    set_hfss_temp_directory(hfss_app, TEMP_DIR)
    set_variables(hfss_app, hfss_variables)
    return hfss_app


def _restart_hfss(hfss_app, hfss_variables: Mapping[str, str]):
    try:
        if hfss_app is not None:
            solver_exit(hfss_app, save_project=False, cleanup_results=True, project_path=PROJECT_PATH)
    except Exception as cleanup_exc:
        print(f"WARNING: solver_exit failed before retry: {cleanup_exc}", file=sys.stderr, flush=True)
    shutil.rmtree(TEMP_DIR, ignore_errors=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    if RETRY_DELAY_SEC:
        time.sleep(RETRY_DELAY_SEC)
    return _start_hfss(hfss_variables)


def _save_pin_state_with_retries(hfss_app, pin_state: int, hfss_variables: Mapping[str, str]):
    attempts = PIN_RETRIES + 1
    for attempt_index in range(attempts):
        cpu_cores = JOB_CPUCORE if attempt_index == 0 else RETRY_CPUCORE
        try:
            _save_pin_state_rawdata(hfss_app, pin_state, cpu_cores=cpu_cores)
            return hfss_app
        except Exception as exc:
            if attempt_index >= attempts - 1:
                raise
            print(
                f"WARNING: pinState {pin_state} failed on attempt {attempt_index + 1}/{attempts}: {exc}. "
                f"Restarting AEDT and retrying with {RETRY_CPUCORE} core(s).",
                file=sys.stderr,
                flush=True,
            )
            hfss_app = _restart_hfss(hfss_app, hfss_variables)
    return hfss_app


def main() -> None:
    hfssApp = None
    started_at = _now_text()
    failed = False

    _bootstrap_home_dirs()
    runtime_identity = _runtime_identity()
    _prepare_rawdata_dir()
    _write_json(
        INDIVIDUAL_METADATA,
        {
            "status": "running",
            "started_at": started_at,
            "non_graphical": bool(NON_GRAPHICAL),
            **runtime_identity,
        },
    )

    #========================================================Simulation Workflow Begin========================================================
    try:
        hfss_variables = _hfss_variables(_load_variables())
        hfssApp = _start_hfss(hfss_variables)
        for pin_state in PIN_STATES:
            hfssApp = _save_pin_state_with_retries(hfssApp, pin_state, hfss_variables)
        _write_rawdata_transfer_zip()
        _write_json(
            INDIVIDUAL_METADATA,
            {
                "status": "done",
                "started_at": started_at,
                "ended_at": _now_text(),
                "non_graphical": bool(NON_GRAPHICAL),
                "raw_data_files": _raw_data_file_names(),
                **runtime_identity,
            },
        )
    except Exception as exc:
        failed = True
        _write_rawdata_transfer_zip()
        _write_json(
            INDIVIDUAL_METADATA,
            {
                "status": "error",
                "started_at": started_at,
                "ended_at": _now_text(),
                "non_graphical": bool(NON_GRAPHICAL),
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "traceback_tail": traceback.format_exc()[-4000:],
                "raw_data_files": _raw_data_file_names(),
                **runtime_identity,
            },
        )
        raise
    finally:
        try:
            if hfssApp is not None:
                solver_exit(hfssApp, save_project=True, cleanup_results=True, project_path=PROJECT_PATH)
        except Exception as cleanup_exc:
            if not failed:
                _write_json(
                    INDIVIDUAL_METADATA,
                    {
                        "status": "error",
                        "started_at": started_at,
                        "ended_at": _now_text(),
                        "non_graphical": bool(NON_GRAPHICAL),
                        "error_type": type(cleanup_exc).__name__,
                        "error_message": f"solver_exit failed: {cleanup_exc}",
                        "traceback_tail": traceback.format_exc()[-4000:],
                        "raw_data_files": _raw_data_file_names(),
                        **runtime_identity,
                    },
                )
                raise
            print(f"WARNING: solver_exit failed during cleanup: {cleanup_exc}", file=sys.stderr, flush=True)
        shutil.rmtree(TEMP_DIR, ignore_errors=True)
    #========================================================Simulation Workflow End========================================================


if __name__ == "__main__":
    main()
