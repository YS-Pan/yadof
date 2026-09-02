"""Shared fast/prepared ngspice kernel for the ninth-order SAW ladder."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import shutil
import time

import numpy as np

from ngspice_com import analyze, save_result, set_variables, solver_init, NgspiceSimulationError

PHYSICAL_FAILURE_TYPES = (NgspiceSimulationError,)


BASE_DIR = Path(__file__).resolve().parent
NETLIST_NAME = "saw_ladder.cir"
FREQUENCY_PARAMETERS = {
    "fs_s_outer",
    "fs_s_inner",
    "fs_s_center",
    "fs_p_outer",
    "fs_p_inner",
}


def _ngspice_parameters(parameters: Mapping[str, object]) -> dict[str, str]:
    output: dict[str, str] = {}
    for raw_name, raw_value in parameters.items():
        name = str(raw_name)
        value = float(raw_value)
        suffix = "Meg" if name in FREQUENCY_PARAMETERS else "p"
        output[name] = f"{value:.12g}{suffix}"
    return output


def _memory_payload(path: Path) -> dict[str, object]:
    with np.load(path, allow_pickle=False) as data:
        return {name: data[name].copy() for name in data.files}


def evaluate_rawdata(parameters, context):
    """Run one isolated AC analysis and return S21/S11 dB curves in memory."""

    scratch_dir = Path(context["scratch_dir"]).resolve()
    scratch_dir.mkdir(parents=True, exist_ok=True)
    source_netlist = scratch_dir / NETLIST_NAME
    shutil.copy2(BASE_DIR / NETLIST_NAME, source_netlist)

    session = solver_init(source_netlist, work_dir=scratch_dir)
    set_variables(session, _ngspice_parameters(parameters))
    configured_timeout = context.get("timeout_sec")
    simulator_timeout = (
        min(45.0, float(configured_timeout))
        if configured_timeout is not None
        else 45.0
    )

    started = time.monotonic()
    result = analyze(
        session,
        vectors=("frequency", "v(s21)", "v(s11)"),
        timeout=simulator_timeout,
        rawfile=scratch_dir / "saw.raw",
        logfile=scratch_dir / "saw.log",
        driver_netlist=scratch_dir / "saw_yadof.cir",
    )
    common_metadata = {
        "task_quantity": "two_port_scattering_parameter",
        "reference_impedance_ohm": 50.0,
        "center_frequency_hz": 1.0e9,
        "target_fractional_bandwidth": 0.04,
        "bvd_k2": 0.09,
        "bvd_q": 1000.0,
        "ladder_order": 9,
    }
    output_paths = []
    for vector, output_name in (("v(s21)", "s21_db"), ("v(s11)", "s11_db")):
        output_paths.append(
            Path(
                save_result(
                    result,
                    vector,
                    component="db20",
                    out_dir=scratch_dir,
                    output_name=output_name,
                    metadata={**common_metadata, "s_parameter": output_name[:3].upper()},
                )
            )
        )

    return {
        path.name: _memory_payload(path) for path in output_paths
    }, {
        "simulator": "ngspice",
        "simulator_returncode": result.returncode,
        "simulator_elapsed_sec": time.monotonic() - started,
        "simulator_stdout_tail": result.stdout[-2000:],
        "simulator_stderr_tail": result.stderr[-2000:],
    }
