"""Render the best completed trebuchet individual into one video and poster."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys
import tempfile

import numpy as np

from yadof.job_template import materialize_job_parameters
from yadof.recorded_data import (
    get_historical_results,
    get_raw_variables,
    get_rawdata_samples,
    list_records,
)


SCRIPT_DIR = Path(__file__).resolve().parent
RENDERER = SCRIPT_DIR / "visualization" / "render_trebuchet_animation.py"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Select the finite completed individual with minimum average cost and "
            "render its trebuchet replay."
        )
    )
    parser.add_argument("--workspace", type=Path, default=SCRIPT_DIR)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path.cwd() / "temp" / "postprocess" / "trebuchet",
    )
    parser.add_argument(
        "--output-prefix",
        default="",
        help="Safe filename prefix used when several results share one output directory.",
    )
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--dpi", type=int, default=120)
    parser.add_argument("--continuation-timeout", type=float, default=180.0)
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
        average_cost = math.fsum(costs) / len(costs)
        # The task emits exactly 1.0 for every objective when dynamic ground
        # clearance is invalid.  Never turn such an error sentinel into a human
        # review video even if a pathological cell contains only invalid rows.
        if average_cost >= 1.0 - 1.0e-12:
            continue
        candidates.append(
            {
                "source_job_name": str(job_name),
                "normalized_variables": [float(value) for value in normalized],
                "raw_variables": [float(value) for value in variables],
                "costs": list(costs),
                "average_cost": average_cost,
                "generation_index": int(record["generation_index"]),
                "population_index": record.get("population_index"),
                "recorded_at": record.get("recorded_at"),
            }
        )
    if not candidates:
        raise RuntimeError(f"no finite completed optimization individual in {workspace}")
    return min(
        candidates,
        key=lambda row: (float(row["average_cost"]), str(row["source_job_name"])),
    )


def _save_npz(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".part")
    with partial.open("wb") as stream:
        np.savez_compressed(stream, **payload)
    os.replace(partial, path)


def _expected_rawdata(workspace: Path) -> set[str]:
    module = runpy.run_path(str(workspace / "job_template" / "task_spec.py"))
    return {f"{field[0]}.npz" for field in module["ALL_RAWDATA_FIELDS"]}


def _stage_snapshot(
    workspace: Path,
    output_dir: Path,
    selection: dict[str, object],
) -> Path:
    snapshot = output_dir / "selected_job"
    materialize_job_parameters(
        workspace,
        tuple(float(value) for value in selection["normalized_variables"]),
        job_dir=snapshot,
    )
    source_job = str(selection["source_job_name"])
    samples = get_rawdata_samples(
        workspace,
        job_names=(source_job,),
        status="completed",
    )
    if len(samples) != 1 or samples[0][0] != source_job:
        raise RuntimeError(f"could not load recorded rawData for {source_job!r}")
    filenames: set[str] = set()
    for item in samples[0][1]:
        payload = dict(item)
        metadata = json.loads(str(np.asarray(payload["metadata"]).item()))
        filename = f"{metadata['rawdata_name']}.npz"
        filenames.add(filename)
        _save_npz(snapshot / "rawData" / filename, payload)
    expected = _expected_rawdata(workspace)
    if filenames != expected:
        raise RuntimeError(
            f"recorded rawData names are {sorted(filenames)}, expected {sorted(expected)}"
        )
    return snapshot


def _write_manifest(path: Path, payload: dict[str, object]) -> None:
    partial = path.with_name(path.name + ".part")
    partial.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(partial, path)


def _copy_file_atomic(source: Path, destination: Path) -> None:
    partial = destination.with_name(destination.name + ".part")
    shutil.copy2(source, partial)
    os.replace(partial, destination)


def main() -> int:
    args = _parse_args()
    if (
        args.fps <= 0
        or args.dpi <= 0
        or not math.isfinite(args.continuation_timeout)
        or args.continuation_timeout <= 0.0
    ):
        raise ValueError("fps, dpi, and continuation timeout must be positive")
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
    video = output_dir / f"{output_prefix}trebuchet_best.mp4"
    poster = output_dir / f"{output_prefix}trebuchet_best_poster.png"
    snapshot_archive = output_dir / f"{output_prefix}trebuchet_selected_job.zip"
    diagnostics = output_dir / f"{output_prefix}trebuchet_continuation_diagnostics.json"
    trajectory = output_dir / f"{output_prefix}trebuchet_animation_trajectory.npz"
    manifest_path = output_dir / f"{output_prefix}postprocess_manifest.json"
    for path in (
        video,
        poster,
        snapshot_archive,
        diagnostics,
        trajectory,
        manifest_path,
    ):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite output: {path}")
    output_dir.mkdir(parents=True, exist_ok=True)

    selection = _select_best(workspace)
    title = (
        "King Arthur trebuchet — minimum average cost "
        f"{float(selection['average_cost']):.6f}"
    )
    with tempfile.TemporaryDirectory(prefix="yadof-trebuchet-visualization-") as temporary:
        scratch_root = Path(temporary)
        snapshot = _stage_snapshot(workspace, scratch_root, selection)
        work_dir = scratch_root / "animation_work"
        subprocess.run(
            [
                sys.executable,
                str(RENDERER),
                "--workspace",
                str(workspace),
                "--job",
                str(snapshot),
                "--output",
                str(video),
                "--poster",
                str(poster),
                "--work-dir",
                str(work_dir),
                "--title",
                title,
                "--fps",
                str(args.fps),
                "--dpi",
                str(args.dpi),
                "--continuation-timeout",
                str(args.continuation_timeout),
            ],
            cwd=str(workspace),
            check=True,
        )
        diagnostics_source = work_dir / "continuation_diagnostics.json"
        trajectory_source = work_dir / "trebuchet_animation_trajectory.npz"
        for path in (video, poster, diagnostics_source, trajectory_source):
            if not path.is_file():
                raise FileNotFoundError(f"renderer did not create expected output: {path}")
        archive_source = Path(
            shutil.make_archive(
                str(scratch_root / "trebuchet_selected_job"),
                "zip",
                root_dir=snapshot.parent,
                base_dir=snapshot.name,
            )
        )
        _copy_file_atomic(archive_source, snapshot_archive)
        _copy_file_atomic(diagnostics_source, diagnostics)
        _copy_file_atomic(trajectory_source, trajectory)
    manifest = {
        "schema_version": 1,
        "workspace": str(workspace),
        "output_prefix": output_prefix,
        "selection_rule": (
            "minimum arithmetic mean of all finite objective costs among "
            "completed optimization individuals"
        ),
        "selection": selection,
        "snapshot_archive": str(snapshot_archive),
        "video": str(video),
        "poster": str(poster),
        "continuation_diagnostics": str(diagnostics),
        "animation_trajectory": str(trajectory),
        "visualization_only": True,
        "optimization_evaluations_added": 0,
    }
    _write_manifest(manifest_path, manifest)
    print(f"selected: {selection['source_job_name']}")
    print(f"average cost: {float(selection['average_cost']):.9f}")
    print(f"video: {video}")
    print(f"poster: {poster}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
