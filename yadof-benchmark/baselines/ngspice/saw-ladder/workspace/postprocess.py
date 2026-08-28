"""Plot the best completed SAW ladder frequency response."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
from pathlib import Path
import re

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

from yadof.job_template.rawdata_contract import load_rawdata_views
from yadof.recorded_data import (
    get_historical_results,
    get_rawdata_samples,
    list_records,
)


SCRIPT_DIR = Path(__file__).resolve().parent


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot S21 and S11 for the finite completed SAW result with minimum average cost."
    )
    parser.add_argument("--workspace", type=Path, default=SCRIPT_DIR)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path.cwd() / "temp" / "postprocess" / "saw",
    )
    parser.add_argument(
        "--output-prefix",
        default="",
        help="Safe filename prefix used when several results share one output directory.",
    )
    return parser.parse_args()


def _select_best(workspace: Path) -> dict[str, object]:
    records = {
        str(row["job_name"]): dict(row)
        for row in list_records(workspace)
        if row.get("status") == "completed"
    }
    candidates: list[dict[str, object]] = []
    for job_name, normalized, costs_raw in get_historical_results(workspace):
        costs = tuple(float(value) for value in costs_raw)
        record = records.get(str(job_name))
        if (
            record is None
            or record.get("generation_index") is None
            or not costs
            or not all(math.isfinite(value) for value in costs)
        ):
            continue
        candidates.append(
            {
                "source_job_name": str(job_name),
                "normalized_variables": [float(value) for value in normalized],
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


def _response(
    workspace: Path,
    job_name: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    samples = get_rawdata_samples(
        workspace,
        job_names=(job_name,),
        status="completed",
    )
    if len(samples) != 1 or samples[0][0] != job_name:
        raise RuntimeError(f"could not load recorded rawData for {job_name!r}")
    views = {view.name: view for view in load_rawdata_views(samples[0][1])}
    frequency = np.asarray(
        views["s21_db"].axis_coordinates("frequency"),
        dtype=float,
    ).reshape(-1)
    s21_db = np.asarray(views["s21_db"].data, dtype=float).reshape(-1)
    s11_frequency = np.asarray(
        views["s11_db"].axis_coordinates("frequency"),
        dtype=float,
    ).reshape(-1)
    s11_db = np.asarray(views["s11_db"].data, dtype=float).reshape(-1)
    if (
        frequency.shape != s21_db.shape
        or s11_frequency.shape != s11_db.shape
        or not np.array_equal(frequency, s11_frequency)
    ):
        raise RuntimeError("SAW S21/S11 frequency grids are inconsistent")
    return frequency, s21_db, s11_db


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
    output_prefix = str(args.output_prefix)
    if not workspace.is_dir():
        raise FileNotFoundError(f"workspace does not exist: {workspace}")
    if output_prefix and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", output_prefix) is None:
        raise ValueError(
            "output prefix must contain only letters, digits, dot, underscore, or hyphen"
        )
    if not output_prefix and output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite nonempty output: {output_dir}")
    png = output_dir / f"{output_prefix}saw_best_response.png"
    svg = output_dir / f"{output_prefix}saw_best_response.svg"
    csv_path = output_dir / f"{output_prefix}saw_best_response.csv"
    manifest_path = output_dir / f"{output_prefix}postprocess_manifest.json"
    for path in (png, svg, csv_path, manifest_path):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite output: {path}")
    output_dir.mkdir(parents=True, exist_ok=True)

    selection = _select_best(workspace)
    frequency, s21_db, s11_db = _response(
        workspace,
        str(selection["source_job_name"]),
    )
    frequency_mhz = frequency / 1.0e6

    plt.style.use("seaborn-v0_8-whitegrid")
    fig, (s21_axis, s11_axis) = plt.subplots(2, 1, figsize=(11.5, 8.0), sharex=True)
    fig.suptitle(
        "Best SAW ladder response — "
        f"average cost {float(selection['average_cost']):.6f}"
    )
    for axis in (s21_axis, s11_axis):
        axis.axvspan(980.0, 1020.0, color="#93c5fd", alpha=0.18, label="target passband")
        axis.axvline(980.0, color="#2563eb", linewidth=0.9, linestyle="--")
        axis.axvline(1020.0, color="#2563eb", linewidth=0.9, linestyle="--")
        axis.set_ylabel("magnitude (dB)")
    s21_axis.plot(frequency_mhz, s21_db, color="#be123c", linewidth=1.8, label="S21")
    s21_axis.set_title("Transmission")
    s21_axis.legend(loc="best")
    s11_axis.plot(frequency_mhz, s11_db, color="#047857", linewidth=1.8, label="S11")
    s11_axis.set_title("Input reflection")
    s11_axis.set_xlabel("frequency (MHz)")
    s11_axis.legend(loc="best")
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.95))

    fig.savefig(png, dpi=160, bbox_inches="tight")
    fig.savefig(svg, bbox_inches="tight")
    plt.close(fig)

    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("frequency_hz", "s21_db", "s11_db"))
        writer.writerows(zip(frequency, s21_db, s11_db, strict=True))

    manifest = {
        "schema_version": 1,
        "workspace": str(workspace),
        "output_prefix": output_prefix,
        "selection_rule": (
            "minimum arithmetic mean of all finite objective costs among "
            "completed optimization individuals"
        ),
        "selection": selection,
        "outputs": {
            "png": str(png),
            "svg": str(svg),
            "csv": str(csv_path),
        },
    }
    _write_json(manifest_path, manifest)
    print(f"selected: {selection['source_job_name']}")
    print(f"plot: {png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
