"""Visualization-only PyChrono child that continues the released mechanism."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from collections.abc import Mapping

import numpy as np


SCRIPT_DIR = Path(__file__).resolve().parent
_workspace_text = os.environ.get("YADOF_ANIMATION_WORKSPACE")
WORKSPACE = (
    Path(_workspace_text).expanduser().resolve()
    if _workspace_text
    else SCRIPT_DIR.parents[1]
)
TASK_DIR = WORKSPACE / "job_template"
sys.path.insert(0, str(TASK_DIR))

from chrono_com import worker_main  # noqa: E402
from chrono_worker import run_task_model  # noqa: E402
from task_spec import (  # noqa: E402
    MODEL_NAME,
    TRAJECTORY_CHANNEL_NAMES,
    TRAJECTORY_CHANNEL_UNITS,
    trajectory_time_axis,
)


def _save_npz(rawdata_dir: Path, filename: str, **payload: object) -> None:
    target = rawdata_dir / filename
    partial = target.with_name(target.name + ".part")
    with partial.open("wb") as stream:
        np.savez_compressed(stream, **payload)
    os.replace(partial, target)


def simulate(
    request: Mapping[str, object],
    rawdata_dir: Path,
) -> Mapping[str, object]:
    """Run the same launch while retaining post-release mechanism motion."""

    import pychrono as chrono

    assigned = request["parameters"]["assigned"]
    result = run_task_model(
        chrono,
        assigned,
        continue_mechanism_after_release=True,
    )
    trajectory = np.asarray(result["animation_trajectory"], dtype=np.float64)
    diagnostics = dict(result["diagnostics"])
    time_axis = np.asarray(trajectory_time_axis(), dtype=np.float64)
    metadata = {
        "schema_version": 1,
        "rawdata_name": "trebuchet_animation_trajectory",
        "shape": list(trajectory.shape),
        "axes": [
            {
                "index": 0,
                "size": int(trajectory.shape[0]),
                "name": "time_s",
                "values_key": "axis_time_s",
            },
            {
                "index": 1,
                "size": int(trajectory.shape[1]),
                "name": "channel",
                "values_key": "axis_channel",
            },
        ],
        "channel_names": list(TRAJECTORY_CHANNEL_NAMES),
        "channel_units": list(TRAJECTORY_CHANNEL_UNITS),
        "model": MODEL_NAME,
        "visualization_only": True,
        "mechanism_continued_after_release": True,
    }
    _save_npz(
        rawdata_dir,
        "trebuchet_animation_trajectory.npz",
        values=trajectory,
        axis_time_s=time_axis,
        axis_channel=np.arange(trajectory.shape[1], dtype=np.float64),
        metadata=np.asarray(json.dumps(metadata, separators=(",", ":"))),
    )
    return {
        **dict(diagnostics),
        "visualization_only": True,
        "pychrono_module": str(Path(chrono.__file__).resolve()),
    }


if __name__ == "__main__":
    raise SystemExit(worker_main(simulate))
