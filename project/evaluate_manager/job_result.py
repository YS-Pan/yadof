from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .config import INDIVIDUAL_METADATA_FILE_NAME, RAW_DATA_DIR_NAME
from .types import JobResult, JobSpec


def base_metadata(job: JobSpec, *, engine: str) -> dict:
    metadata = read_existing_metadata(job.directory)
    metadata.update(
        {
            "job_name": job.name,
            "status": "prepared",
            "engine": str(engine),
            "timed_out": False,
        }
    )
    for key, value in job_context(job).items():
        metadata.setdefault(key, value)
    return metadata


def result_from_metadata(job: JobSpec, metadata: dict, raw_data_paths=()) -> JobResult:
    return JobResult(
        job_name=job.name,
        job_dir=job.directory,
        status=str(metadata["status"]),
        unnormalized_variables=job.unnormalized_variables,
        raw_data_paths=tuple(Path(p) for p in raw_data_paths),
        metadata=dict(metadata),
    )


def read_existing_metadata(job_dir: Path) -> dict:
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


def raw_data_paths(job_dir: Path) -> tuple[Path, ...]:
    raw_dir = job_dir / RAW_DATA_DIR_NAME
    if not raw_dir.is_dir():
        return ()
    return tuple(sorted((p for p in raw_dir.iterdir() if p.is_file() and p.suffix.lower() == ".npz"), key=lambda p: p.name.lower()))


def write_metadata(job_dir: Path, metadata: dict) -> None:
    text = json.dumps(metadata, ensure_ascii=True, indent=2)
    for name in ("metadata.json", "metaData.json"):
        (job_dir / name).write_text(text, encoding="utf-8", newline="\n")


def read_individual_metadata(job_dir: Path) -> dict:
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


def job_context(job: JobSpec) -> dict[str, object]:
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


def now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def tail(text: str | None, limit: int = 4000) -> str:
    text = text or ""
    return text[-int(limit) :]
