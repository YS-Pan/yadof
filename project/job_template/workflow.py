from __future__ import annotations

import shutil
import sys
import traceback
from collections.abc import Mapping, Sequence
from pathlib import Path

from hfss_com import analyze, save_farField, save_modal, set_hfss_temp_directory, set_para, set_variables, solver_exit, solver_init
from parameters_constraints import get_parameters

try:
    import config as job_config
except ImportError:
    try:
        from project import config as job_config
    except ImportError:
        job_config = None
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
PROJECT_NAME = "Newchoke20260620"
PROJECT_PATH = BASE_DIR / f"{PROJECT_NAME}.aedt"
DESIGN_NAME = "HFSSDesign4"
SETUP_NAME = "Setup1"
SWEEP_NAME = "Sweep"
S11_SOLUTION_NAME = f"{SETUP_NAME} : {SWEEP_NAME}"
FAR_FIELD_SOLUTION_NAME = f"{SETUP_NAME} : LastAdaptive"
AXIAL_RATIO_SOLUTION_NAME = f"{SETUP_NAME} : {SWEEP_NAME}"
FAR_FIELD_CONTEXT = "Infinite Sphere1"

PIN_STATE_VAR = "pinState"
PIN_STATES = (1, 2, 3)

S11_EXPR = "dB(S(1,1))"
GAIN_LHCP_EXPR = "dB(RealizedGainLHCP)"
AXIAL_RATIO_EXPR = "dB(AxialRatioValue)"
TARGET_FREQ_GHZ = 2.44
TARGET_PHI_DEG = 90.0

RAW_DATA_DIR = BASE_DIR / "rawData"
RAW_DATA_TRANSFER_ZIP = BASE_DIR / "rawData_outputs.zip"
TEMP_DIR = BASE_DIR / "_tmp"
INDIVIDUAL_METADATA = BASE_DIR / "individual_metadata.json"
PARAMETER_VALUES_FILE = BASE_DIR / "parameters_values.py"

CONFIG_JOB_CPUCORE = int(getattr(job_config, "HFSS_JOB_CPUCORE", 1)) if job_config is not None else 1
CONFIG_PARALLEL_TASKS = int(getattr(job_config, "HFSS_PARALLEL_TASKS", 1)) if job_config is not None else 1
CONFIG_NON_GRAPHICAL = bool(getattr(job_config, "HFSS_NON_GRAPHICAL", True)) if job_config is not None else True

# The job-local config and generated HTCondor environment share this setting.
JOB_CPUCORE = env_int("YADOF_HFSS_JOB_CPUCORE", CONFIG_JOB_CPUCORE, minimum=1)
PARALLEL_TASKS = env_int("YADOF_HFSS_PARALLEL_TASKS", CONFIG_PARALLEL_TASKS, minimum=1)
NON_GRAPHICAL = env_bool("YADOF_HFSS_NON_GRAPHICAL", CONFIG_NON_GRAPHICAL)


def _hfss_variables(variables: Mapping[str, float] | Sequence[float]) -> dict[str, str]:
    """Format the current individual variables for HFSS.

    Parameter names and units come from parameters_constraints.py. Values come
    from the job input written by evaluate_manager for this individual.
    """

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


def _write_parameter_values_file(variables: Mapping[str, float] | Sequence[float]) -> Path:
    """Materialize current values in the format consumed by set_para."""

    values = _hfss_variables(variables)
    lines = [
        "class _Parameter:",
        "    def __init__(self, name, unit, value):",
        "        self.name = name",
        "        self.unit = unit",
        "        self.value = value",
        "",
        "PARAMETERS = (",
    ]
    for parameter in get_parameters():
        name = parameter.name
        unit = str(getattr(parameter, "unit", "") or "")
        raw_value = values[name][: -len(unit)] if unit else values[name]
        lines.append(f"    _Parameter({name!r}, {unit!r}, {float(raw_value)!r}),")
    lines.extend((")", ""))
    PARAMETER_VALUES_FILE.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return PARAMETER_VALUES_FILE


def _start_hfss(parameter_values_file: Path):
    hfss_app, *_ = solver_init(projectName=str(PROJECT_PATH), designName=DESIGN_NAME, non_graphical=NON_GRAPHICAL)
    set_hfss_temp_directory(hfss_app, TEMP_DIR)
    set_para(hfss_app, str(parameter_values_file))
    return hfss_app


def _save_pin_state_rawdata(hfss_app, pin_state: int) -> None:
    set_variables(hfss_app, {PIN_STATE_VAR: str(int(pin_state))})
    analyze(hfss_app, analyzeSetup=SETUP_NAME, CPUcores=JOB_CPUCORE, ParallelTasks=PARALLEL_TASKS)

    save_modal(
        hfss_app,
        S11_EXPR,
        variations={"Freq": ["All"]},
        setup=S11_SOLUTION_NAME,
        out_dir=str(RAW_DATA_DIR),
        output_name=f"s11_pinState{pin_state}",
        metadata={"pin_state": pin_state, "hfss_quantity": "s11"},
    )
    save_farField(
        hfss_app,
        GAIN_LHCP_EXPR,
        context=FAR_FIELD_CONTEXT,
        variations={
            "Theta": ["All"],
            "Phi": ["All"],
            "Freq": [f"{TARGET_FREQ_GHZ:g}GHz"],
        },
        setup=FAR_FIELD_SOLUTION_NAME,
        out_dir=str(RAW_DATA_DIR),
        output_name=f"gain_lhcp_pinState{pin_state}",
        metadata={"pin_state": pin_state, "hfss_quantity": "realized_gain_lhcp"},
    )
    save_farField(
        hfss_app,
        AXIAL_RATIO_EXPR,
        context=FAR_FIELD_CONTEXT,
        variations={
            "Theta": ["All"],
            "Phi": ["All"],
            "Freq": ["All"],
        },
        setup=AXIAL_RATIO_SOLUTION_NAME,
        out_dir=str(RAW_DATA_DIR),
        output_name=f"axial_ratio_pinState{pin_state}",
        metadata={"pin_state": pin_state, "hfss_quantity": "axial_ratio"},
    )


def main() -> None:
    hfssApp = None
    started_at = now_text()
    failed = False

    bootstrap_home_dirs(BASE_DIR, TEMP_DIR)
    runtime_info = runtime_identity(
        BASE_DIR,
        environment={"runtime_ansys_license": "ANSYSLMD_LICENSE_FILE"},
        extra={"runtime_hfss_job_cpucore": JOB_CPUCORE, "runtime_hfss_parallel_tasks": PARALLEL_TASKS, "runtime_hfss_non_graphical": bool(NON_GRAPHICAL)},
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
        parameter_values_file = _write_parameter_values_file(load_variables(BASE_DIR))
        hfssApp = _start_hfss(parameter_values_file)
        for pin_state in PIN_STATES:
            _save_pin_state_rawdata(hfssApp, pin_state)

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
        shutil.rmtree(PROJECT_PATH.with_name(PROJECT_PATH.stem + ".aedtresults"), ignore_errors=True)
        shutil.rmtree(TEMP_DIR, ignore_errors=True)
        PARAMETER_VALUES_FILE.unlink(missing_ok=True)
    #========================================================Simulation Workflow End========================================================


if __name__ == "__main__":
    main()
