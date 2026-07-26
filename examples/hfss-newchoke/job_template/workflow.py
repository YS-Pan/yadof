from __future__ import annotations

import shutil
from pathlib import Path

from hfss_com import analyze, save_farField, save_modal, set_hfss_temp_directory, set_para, set_variables, solver_exit, solver_init

import hfss_settings as job_config


PROJECT_NAME = "Newchoke20260620"
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

CONFIG_JOB_CPUCORE = int(job_config.HFSS_JOB_CPUCORE)
CONFIG_PARALLEL_TASKS = int(job_config.HFSS_PARALLEL_TASKS)
CONFIG_NON_GRAPHICAL = bool(job_config.HFSS_NON_GRAPHICAL)

def _start_hfss(
    parameter_file: Path,
    project_path: Path,
    temp_dir: Path,
    *,
    non_graphical: bool,
):
    hfss_app, *_ = solver_init(
        projectName=str(project_path),
        designName=DESIGN_NAME,
        non_graphical=non_graphical,
    )
    set_hfss_temp_directory(hfss_app, temp_dir)
    set_para(hfss_app, str(parameter_file))
    return hfss_app


def _save_pin_state_rawdata(
    hfss_app,
    pin_state: int,
    raw_data_dir: Path,
    *,
    job_cpucore: int,
    parallel_tasks: int,
) -> None:
    set_variables(hfss_app, {PIN_STATE_VAR: str(int(pin_state))})
    analyze(
        hfss_app,
        analyzeSetup=SETUP_NAME,
        CPUcores=job_cpucore,
        ParallelTasks=parallel_tasks,
    )

    save_modal(
        hfss_app,
        S11_EXPR,
        variations={"Freq": ["All"]},
        setup=S11_SOLUTION_NAME,
        out_dir=str(raw_data_dir),
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
        out_dir=str(raw_data_dir),
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
        out_dir=str(raw_data_dir),
        output_name=f"axial_ratio_pinState{pin_state}",
        metadata={"pin_state": pin_state, "hfss_quantity": "axial_ratio"},
    )


def main() -> None:
    from worker_misc import env_bool, env_int, run_workflow

    job_cpucore = env_int(
        "YADOF_HFSS_JOB_CPUCORE",
        CONFIG_JOB_CPUCORE,
        minimum=1,
    )
    parallel_tasks = env_int(
        "YADOF_HFSS_PARALLEL_TASKS",
        CONFIG_PARALLEL_TASKS,
        minimum=1,
    )
    non_graphical = env_bool(
        "YADOF_HFSS_NON_GRAPHICAL",
        CONFIG_NON_GRAPHICAL,
    )
    hfss_app = None

    def evaluate(context) -> None:
        nonlocal hfss_app
        hfss_app = _start_hfss(
            context.base_dir / "parameters_constraints.py",
            context.base_dir / f"{PROJECT_NAME}.aedt",
            context.temp_dir,
            non_graphical=non_graphical,
        )
        for pin_state in PIN_STATES:
            _save_pin_state_rawdata(
                hfss_app,
                pin_state,
                context.raw_data_dir,
                job_cpucore=job_cpucore,
                parallel_tasks=parallel_tasks,
            )

    def cleanup(context) -> None:
        project_path = context.base_dir / f"{PROJECT_NAME}.aedt"
        try:
            if hfss_app is not None:
                solver_exit(
                    hfss_app,
                    save_project=True,
                    cleanup_results=True,
                    project_path=project_path,
                )
        finally:
            shutil.rmtree(
                project_path.with_name(project_path.stem + ".aedtresults"),
                ignore_errors=True,
            )

    run_workflow(
        evaluate,
        cleanup=cleanup,
        metadata={"non_graphical": bool(non_graphical)},
        runtime_environment={
            "runtime_ansys_license": "ANSYSLMD_LICENSE_FILE",
        },
        runtime_extra={
            "runtime_hfss_job_cpucore": job_cpucore,
            "runtime_hfss_parallel_tasks": parallel_tasks,
            "runtime_hfss_non_graphical": bool(non_graphical),
        },
    )


if __name__ == "__main__":
    main()
