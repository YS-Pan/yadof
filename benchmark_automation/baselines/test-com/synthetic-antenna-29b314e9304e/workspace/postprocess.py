"""Create a compact human-readable summary of the best synthetic antenna result."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import runpy

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

from yadof.job_template.rawdata_contract import load_rawdata_views
from yadof.recorded_data import (
    get_historical_results,
    get_raw_variables,
    get_rawdata_samples,
    list_records,
)


SCRIPT_DIR = Path(__file__).resolve().parent
TARGET_FREQUENCY_GHZ = 2.44
TARGET_PHI_DEG = 90.0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Plot S11 and angular gain/axial-ratio cuts for the finite completed "
            "test-com result with minimum average cost."
        )
    )
    parser.add_argument("--workspace", type=Path, default=SCRIPT_DIR)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path.cwd() / "temp" / "postprocess" / "test-com",
    )
    return parser.parse_args()


def _select_best(workspace: Path) -> dict[str, object]:
    raw_variables = dict(get_raw_variables(workspace, status="completed"))
    records = {
        str(row["job_name"]): dict(row)
        for row in list_records(workspace)
        if row.get("status") == "completed"
    }
    candidates: list[dict[str, object]] = []
    for job_name, normalized, costs_raw in get_historical_results(workspace):
        costs = tuple(float(value) for value in costs_raw)
        record = records.get(str(job_name))
        variables = raw_variables.get(str(job_name))
        if (
            record is None
            or record.get("generation_index") is None
            or variables is None
            or not costs
            or not all(math.isfinite(value) for value in costs)
        ):
            continue
        candidates.append(
            {
                "source_job_name": str(job_name),
                "normalized_variables": [float(value) for value in normalized],
                "raw_variables": [float(value) for value in variables],
                "costs": list(costs),
                "average_cost": math.fsum(costs) / len(costs),
                "generation_index": int(record["generation_index"]),
                "population_index": record.get("population_index"),
            }
        )
    if not candidates:
        raise RuntimeError(f"no finite completed optimization individual in {workspace}")
    return min(
        candidates,
        key=lambda row: (float(row["average_cost"]), str(row["source_job_name"])),
    )


def _views(workspace: Path, job_name: str):
    samples = get_rawdata_samples(
        workspace,
        job_names=(job_name,),
        status="completed",
    )
    if len(samples) != 1 or samples[0][0] != job_name:
        raise RuntimeError(f"could not load recorded rawData for {job_name!r}")
    return {view.name: view for view in load_rawdata_views(samples[0][1])}


def _nearest(values: np.ndarray, target: float) -> int:
    return int(np.argmin(np.abs(np.asarray(values, dtype=float) - target)))


def _parameter_names(workspace: Path) -> list[str]:
    module = runpy.run_path(
        str(workspace / "job_template" / "parameters_constraints.py")
    )
    return [str(parameter.name) for parameter in module["PARAMETERS"]]


def _write_json(path: Path, payload: dict[str, object]) -> None:
    partial = path.with_name(path.name + ".part")
    partial.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(partial, path)


def main() -> int:
    args = _parse_args()
    workspace = args.workspace.resolve()
    output_dir = args.output_dir.resolve()
    if not workspace.is_dir():
        raise FileNotFoundError(f"workspace does not exist: {workspace}")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite nonempty output: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    selection = _select_best(workspace)
    views = _views(workspace, str(selection["source_job_name"]))
    parameter_names = _parameter_names(workspace)
    raw_variables = np.asarray(selection["raw_variables"], dtype=float)
    if len(parameter_names) != raw_variables.size:
        raise RuntimeError("recorded variables do not match task parameter names")

    plt.style.use("seaborn-v0_8-whitegrid")
    fig, axes = plt.subplots(2, 2, figsize=(13.2, 9.0))
    s11_axis, gain_axis, axial_axis, parameter_axis = axes.ravel()
    colors = ("#2563eb", "#be123c", "#047857")

    cut_summary: dict[str, object] = {}
    for state, color in zip((1, 2, 3), colors, strict=True):
        s11_view = views[f"s11_pinState{state}"]
        frequency = np.asarray(s11_view.axis_coordinates("Freq"), dtype=float)
        s11 = np.asarray(s11_view.data, dtype=float).reshape(-1)
        s11_axis.plot(frequency, s11, color=color, marker="o", label=f"state {state}")

        gain_view = views[f"gain_lhcp_pinState{state}"]
        gain_frequency = np.asarray(gain_view.axis_coordinates("Freq"), dtype=float)
        gain_phi = np.asarray(gain_view.axis_coordinates("Phi"), dtype=float)
        gain_theta = np.asarray(gain_view.axis_coordinates("Theta"), dtype=float)
        gain_cut = np.asarray(gain_view.data, dtype=float)[
            _nearest(gain_frequency, TARGET_FREQUENCY_GHZ),
            _nearest(gain_phi, TARGET_PHI_DEG),
            :,
        ]
        gain_axis.plot(gain_theta, gain_cut, color=color, label=f"state {state}")

        axial_view = views[f"axial_ratio_pinState{state}"]
        axial_frequency = np.asarray(axial_view.axis_coordinates("Freq"), dtype=float)
        axial_phi = np.asarray(axial_view.axis_coordinates("Phi"), dtype=float)
        axial_theta = np.asarray(axial_view.axis_coordinates("Theta"), dtype=float)
        axial_cut = np.asarray(axial_view.data, dtype=float)[
            _nearest(axial_frequency, TARGET_FREQUENCY_GHZ),
            _nearest(axial_phi, TARGET_PHI_DEG),
            :,
        ]
        axial_axis.plot(axial_theta, axial_cut, color=color, label=f"state {state}")
        cut_summary[f"pinState{state}"] = {
            "minimum_s11_db": float(np.min(s11)),
            "maximum_gain_cut_db": float(np.max(gain_cut)),
            "minimum_axial_ratio_cut_db": float(np.min(axial_cut)),
        }

    s11_axis.axvline(TARGET_FREQUENCY_GHZ, color="#111827", linestyle="--", linewidth=0.9)
    s11_axis.set_title("S11 by switch state")
    s11_axis.set_xlabel("frequency (GHz)")
    s11_axis.set_ylabel("S11 (dB)")
    s11_axis.legend(loc="best")

    gain_axis.set_title("LHCP gain cut at 2.44 GHz, phi=90°")
    gain_axis.set_xlabel("theta (deg)")
    gain_axis.set_ylabel("gain (dB)")
    gain_axis.legend(loc="best")

    axial_axis.axhline(3.0, color="#111827", linestyle="--", linewidth=0.9, label="3 dB")
    axial_axis.set_title("Axial-ratio cut at 2.44 GHz, phi=90°")
    axial_axis.set_xlabel("theta (deg)")
    axial_axis.set_ylabel("axial ratio (dB)")
    axial_axis.legend(loc="best")

    indices = np.arange(raw_variables.size)
    parameter_axis.bar(indices, raw_variables, color="#7c3aed", alpha=0.82)
    parameter_axis.set_title("Selected physical design variables")
    parameter_axis.set_xlabel("parameter")
    parameter_axis.set_ylabel("value")
    parameter_axis.set_xticks(indices)
    parameter_axis.set_xticklabels(parameter_names, rotation=75, ha="right", fontsize=7)

    fig.suptitle(
        "Best synthetic antenna response — "
        f"average cost {float(selection['average_cost']):.6f}"
    )
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.96))
    png = output_dir / "test_com_best_response.png"
    fig.savefig(png, dpi=160, bbox_inches="tight")
    plt.close(fig)

    manifest = {
        "schema_version": 1,
        "workspace": str(workspace),
        "selection_rule": (
            "minimum arithmetic mean of all finite objective costs among "
            "completed optimization individuals"
        ),
        "selection": selection,
        "cut_summary": cut_summary,
        "plot": str(png),
    }
    _write_json(output_dir / "postprocess_manifest.json", manifest)
    print(f"selected: {selection['source_job_name']}")
    print(f"plot: {png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
