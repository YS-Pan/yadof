from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Mapping

from .config import INDIVIDUAL_METADATA_FILE_NAME, RAW_DATA_DIR_NAME, WORKFLOW_SCRIPT_NAME
from .types import JobResult, JobSpec


def run_local_job(
    job: JobSpec,
    *,
    timeout_sec: float,
    python_executable: str | Path = sys.executable,
    env: Mapping[str, str] | None = None,
) -> JobResult:
    workflow = job.directory / WORKFLOW_SCRIPT_NAME
    metadata = _base_metadata(job)
    if not workflow.is_file():
        metadata.update(status="error", error=f"Missing {WORKFLOW_SCRIPT_NAME}", runner_detected_at=_now_text())
        _write_metadata(job.directory, metadata)
        return _result(job, metadata)

    metadata.update(status="running", runner_started_at=_now_text())
    _write_metadata(job.directory, metadata)

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

    raw_data_paths = _raw_data_paths(job.directory)
    individual_metadata = _read_individual_metadata(job.directory)
    if timed_out:
        status = "timeout"
        error = f"Workflow exceeded timeout_sec={float(timeout_sec):.3f}"
    elif proc.returncode == 0 and raw_data_paths and str(individual_metadata.get("status", "")).lower() != "error":
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
        runner_finished_at=_now_text(),
        raw_data_files=[p.name for p in raw_data_paths],
        stdout_tail=_tail(stdout),
        stderr_tail=_tail(stderr),
    )
    if error is not None:
        metadata["error"] = error
    _write_metadata(job.directory, metadata)
    return _result(job, metadata, raw_data_paths)


def _result(job: JobSpec, metadata: dict, raw_data_paths=()) -> JobResult:
    return JobResult(
        job_name=job.name,
        job_dir=job.directory,
        status=str(metadata["status"]),
        unnormalized_variables=job.unnormalized_variables,
        raw_data_paths=tuple(Path(p) for p in raw_data_paths),
        metadata=dict(metadata),
    )


def _base_metadata(job: JobSpec) -> dict:
    metadata = _read_existing_metadata(job.directory)
    metadata.update(
        {
            "job_name": job.name,
            "status": "prepared",
            "engine": "local",
            "timed_out": False,
        }
    )
    for key, value in _job_context(job).items():
        metadata.setdefault(key, value)
    return metadata


def _read_existing_metadata(job_dir: Path) -> dict:
    for name in ("metadata.json", "metaData.json"):
        path = job_dir / name
        if not path.is_file():
            continue
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(loaded, dict):
            return dict(loaded)
    return {}


def _raw_data_paths(job_dir: Path) -> tuple[Path, ...]:
    raw_dir = job_dir / RAW_DATA_DIR_NAME
    if not raw_dir.is_dir():
        return ()
    return tuple(sorted((p for p in raw_dir.iterdir() if p.is_file() and p.suffix.lower() == ".npz"), key=lambda p: p.name.lower()))


def _write_metadata(job_dir: Path, metadata: dict) -> None:
    text = json.dumps(metadata, ensure_ascii=True, indent=2)
    for name in ("metadata.json", "metaData.json"):
        (job_dir / name).write_text(text, encoding="utf-8", newline="\n")


def _read_individual_metadata(job_dir: Path) -> dict:
    path = job_dir / INDIVIDUAL_METADATA_FILE_NAME
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "individual_metadata_error": f"could not read {INDIVIDUAL_METADATA_FILE_NAME}",
        }
    return dict(loaded) if isinstance(loaded, dict) else {}


def _job_context(job: JobSpec) -> dict[str, object]:
    context: dict[str, object] = {}
    if job.run_id is not None:
        context["run_id"] = str(job.run_id)
    if job.optimization_index is not None:
        context["optimization_index"] = int(job.optimization_index)
    if job.generation_index is not None:
        context["generation_index"] = int(job.generation_index)
    if job.population_index is not None:
        context["population_index"] = int(job.population_index)
    return context


def _now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def _tail(text: str | None, limit: int = 4000) -> str:
    text = text or ""
    return text[-int(limit) :]


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
