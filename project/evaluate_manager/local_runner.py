from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Mapping

from .config import RAW_DATA_DIR_NAME, WORKFLOW_SCRIPT_NAME
from .job_result import (
    base_metadata,
    now_text,
    raw_data_paths,
    read_individual_metadata,
    result_from_metadata,
    tail,
    write_metadata,
)
from .types import JobResult, JobSpec


def run_local_job(
    job: JobSpec,
    *,
    timeout_sec: float,
    python_executable: str | Path = sys.executable,
    env: Mapping[str, str] | None = None,
) -> JobResult:
    workflow = job.directory / WORKFLOW_SCRIPT_NAME
    metadata = base_metadata(job, engine="local")
    if not workflow.is_file():
        metadata.update(status="error", error=f"Missing {WORKFLOW_SCRIPT_NAME}", runner_detected_at=now_text())
        write_metadata(job.directory, metadata)
        return result_from_metadata(job, metadata)

    metadata.update(status="running", runner_started_at=now_text())
    write_metadata(job.directory, metadata)

    run_env = os.environ.copy()
    if env:
        run_env.update({str(k): str(v) for k, v in env.items()})

    proc = subprocess.Popen(
        [str(python_executable), "-u", WORKFLOW_SCRIPT_NAME],
        cwd=str(job.directory),
        env=run_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    timed_out = False
    try:
        stdout, stderr = proc.communicate(timeout=float(timeout_sec))
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate_process_tree(proc)
        stdout, stderr = proc.communicate()

    raw_paths = raw_data_paths(job.directory)
    individual_metadata = read_individual_metadata(job.directory)
    if timed_out:
        status = "timeout"
        error = f"Workflow exceeded timeout_sec={float(timeout_sec):.3f}"
    elif proc.returncode == 0 and raw_paths and str(individual_metadata.get("status", "")).lower() != "error":
        status = "done"
        error = None
    elif proc.returncode == 0:
        status = "error"
        error = f"Workflow completed but wrote no .npz files under {RAW_DATA_DIR_NAME}/"
    else:
        status = "error"
        error = f"Workflow exited with return code {proc.returncode}"

    metadata.update(individual_metadata)
    metadata.update(
        status=status,
        timed_out=timed_out,
        returncode=None if timed_out else int(proc.returncode),
        runner_finished_at=now_text(),
        raw_data_files=[p.name for p in raw_paths],
        stdout_tail=tail(stdout),
        stderr_tail=tail(stderr),
    )
    if error is not None:
        metadata["error"] = error
    write_metadata(job.directory, metadata)
    return result_from_metadata(job, metadata, raw_paths)


def _terminate_process_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        proc.kill()
