from __future__ import annotations

import shutil
import sys
import traceback
from collections.abc import Mapping, Sequence
from pathlib import Path

from hfss_com import analyze, save_farField, save_modal, set_hfss_temp_directory, set_variables, solver_exit, solver_init
from parameters_constraints import get_parameters
from worker_misc import (
    bootstrap_home_dirs,
    env_bool,
    env_int,
    load_variables,
    now_text,
    prepare_rawdata_dir,
    raw_data_file_names,
    runtime_identity,
    write_json,
    write_rawdata_transfer_zip,
)


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


JOB_CPUCORE = env_int("YADOT_HFSS_JOB_CPUCORE", DEFAULT_JOB_CPUCORE, minimum=1)
PARALLEL_TASKS = env_int("YADOT_HFSS_PARALLEL_TASKS", DEFAULT_PARALLEL_TASKS, minimum=1)
NON_GRAPHICAL = env_bool("YADOT_HFSS_NON_GRAPHICAL", DEFAULT_NON_GRAPHICAL)


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


def _save_pin_state_rawdata(hfssApp, pin_state: int, *, cpu_cores: int) -> None:
    set_variables(hfssApp, {PIN_STATE_VAR: str(int(pin_state))})
    analyze(hfssApp, analyzeSetup=SETUP_NAME, CPUcores=cpu_cores, ParallelTasks=PARALLEL_TASKS)
    save_modal(
        hfssApp,
        S11_EXPR,
        setup=S11_SOLUTION_NAME,
        out_dir=str(RAW_DATA_DIR),
        output_name=f"s11_pinState{pin_state}",
        metadata={"pin_state": pin_state, "hfss_quantity": "s11"},
    )
    save_farField(
        hfssApp,
        GAIN_EXPR,
        context=GAIN_CONTEXT,
        variations={
            "Theta": ["All"],
            "Phi": [f"{TARGET_PHI_DEG:g}deg"],
            "Freq": [f"{TARGET_FREQ_GHZ:g}GHz"],
        },
        primary_sweep_variable="Theta",
        setup=GAIN_SOLUTION_NAME,
        out_dir=str(RAW_DATA_DIR),
        output_name=f"gain_pinState{pin_state}",
        metadata={"pin_state": pin_state, "hfss_quantity": "realized_gain_total"},
    )


def _start_hfss(hfss_variables: Mapping[str, str]):
    hfss_app, *_ = solver_init(projectName=str(PROJECT_PATH), designName=DESIGN_NAME, non_graphical=NON_GRAPHICAL)
    set_hfss_temp_directory(hfss_app, TEMP_DIR)
    set_variables(hfss_app, hfss_variables)
    return hfss_app


def main() -> None:
    hfssApp = None
    started_at = now_text()
    failed = False

    bootstrap_home_dirs(BASE_DIR, TEMP_DIR)
    runtime_info = runtime_identity(
        BASE_DIR,
        environment={"runtime_ansys_license": "ANSYSLMD_LICENSE_FILE"},
        extra={"runtime_hfss_job_cpucore": JOB_CPUCORE},
    )
    prepare_rawdata_dir(RAW_DATA_DIR, RAW_DATA_TRANSFER_ZIP)
    write_json(
        INDIVIDUAL_METADATA,
        {
            "status": "running",
            "started_at": started_at,
            "non_graphical": bool(NON_GRAPHICAL),
            **runtime_info,
        },
    )

    #========================================================Simulation Workflow Begin========================================================
    try:
        hfss_variables = _hfss_variables(load_variables(BASE_DIR))
        hfssApp = _start_hfss(hfss_variables)
        for pin_state in PIN_STATES:
            _save_pin_state_rawdata(hfssApp, pin_state, cpu_cores=JOB_CPUCORE)
        write_rawdata_transfer_zip(RAW_DATA_DIR, RAW_DATA_TRANSFER_ZIP)
        write_json(
            INDIVIDUAL_METADATA,
            {
                "status": "done",
                "started_at": started_at,
                "ended_at": now_text(),
                "non_graphical": bool(NON_GRAPHICAL),
                "raw_data_files": raw_data_file_names(RAW_DATA_DIR),
                **runtime_info,
            },
        )
    except Exception as exc:
        failed = True
        write_rawdata_transfer_zip(RAW_DATA_DIR, RAW_DATA_TRANSFER_ZIP)
        write_json(
            INDIVIDUAL_METADATA,
            {
                "status": "error",
                "started_at": started_at,
                "ended_at": now_text(),
                "non_graphical": bool(NON_GRAPHICAL),
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "traceback_tail": traceback.format_exc()[-4000:],
                "raw_data_files": raw_data_file_names(RAW_DATA_DIR),
                **runtime_info,
            },
        )
        raise
    finally:
        try:
            if hfssApp is not None:
                solver_exit(hfssApp, save_project=True, cleanup_results=True, project_path=PROJECT_PATH)
        except Exception as cleanup_exc:
            if not failed:
                write_json(
                    INDIVIDUAL_METADATA,
                    {
                        "status": "error",
                        "started_at": started_at,
                        "ended_at": now_text(),
                        "non_graphical": bool(NON_GRAPHICAL),
                        "error_type": type(cleanup_exc).__name__,
                        "error_message": f"solver_exit failed: {cleanup_exc}",
                        "traceback_tail": traceback.format_exc()[-4000:],
                        "raw_data_files": raw_data_file_names(RAW_DATA_DIR),
                        **runtime_info,
                    },
                )
                raise
            print(f"WARNING: solver_exit failed during cleanup: {cleanup_exc}", file=sys.stderr, flush=True)
        shutil.rmtree(TEMP_DIR, ignore_errors=True)
    #========================================================Simulation Workflow End========================================================


if __name__ == "__main__":
    main()
