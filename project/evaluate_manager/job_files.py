from __future__ import annotations

import importlib
import hashlib
import json
import re
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .config import PROJECT_CONFIG_DIR_NAME, PROJECT_DIR, RAW_DATA_DIR_NAME
from .types import JobSpec

EXCLUDED_TEMPLATE_NAMES = {
    "__pycache__",
    "__init__.py",
    "api.py",
    "calc_cost.py",
    "cost.json",
    "rawData_outputs.zip",
    "metadata.json",
    "metaData.json",
    "individual_metadata.json",
    "individual_metadata.json.tmp",
    "job.sub",
    "stdout.txt",
    "stderr.txt",
    "condor.log",
    "condor_submit.stdout.txt",
    "condor_submit.stderr.txt",
    "cluster.id",
}
EXCLUDED_TEMPLATE_DIRS = {"__pycache__", "._appdata", "._home", "._localappdata", "._tmp", "_tmp", "history", RAW_DATA_DIR_NAME}
HASH_EXCLUDED_NAMES = {
    "cost.json",
    "metadata.json",
    "metadata.json.tmp",
    "metaData.json",
    "individual_metadata.json",
    "individual_metadata.json.tmp",
}
HASH_EXCLUDED_DIRS = {
    "__pycache__",
    ".pytest_cache",
    ".tmp",
    "_tmp",
    "rawdata",
    "temp",
    "tmp",
}
_JOB_NAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def new_job_name(prefix: str = "job") -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return f"{_sanitize_name(prefix)}_{stamp}"


def prepare_job(
    variables: Iterable[float],
    *,
    jobs_dir: str | Path,
    job_template_dir: str | Path,
    job_name: str | None = None,
    run_id: str | None = None,
    optimization_index: int | None = None,
    generation_index: int | None = None,
    population_index: int | None = None,
) -> JobSpec:
    jobs_dir = Path(jobs_dir)
    template_dir = Path(job_template_dir)
    if not template_dir.is_dir():
        raise FileNotFoundError(f"job_template directory does not exist: {template_dir}")

    jobs_dir.mkdir(parents=True, exist_ok=True)
    name, job_dir = _create_unique_job_dir(jobs_dir, job_name or new_job_name())

    normalized_values = tuple(float(x) for x in variables)
    _copy_template(template_dir, job_dir)
    values = _materialize_parameters(template_dir, job_dir, normalized_values)
    _copy_project_config(job_dir)
    (job_dir / RAW_DATA_DIR_NAME).mkdir(exist_ok=True)
    job_static_hash = prepared_job_static_hash(job_dir)

    evaluation_context = _evaluation_context(
        run_id=run_id,
        optimization_index=optimization_index,
        generation_index=generation_index,
        population_index=population_index,
    )
    metadata = {
        "job_name": name,
        "status": "prepared",
        "job_static_hash": job_static_hash,
        **evaluation_context,
    }
    _write_json(job_dir / "metadata.json", metadata)
    _write_json(job_dir / "metaData.json", metadata)
    return JobSpec(
        name=name,
        directory=job_dir,
        unnormalized_variables=values,
        normalized_variables=normalized_values,
        run_id=run_id,
        optimization_index=optimization_index,
        generation_index=generation_index,
        population_index=population_index,
    )


def prepared_job_static_hash(job_dir: str | Path) -> str:
    """Return a stable hash for static files copied into a prepared job."""

    root = Path(job_dir)
    digest = hashlib.sha256()
    files = sorted(
        (path for path in root.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(root).as_posix().lower(),
    )
    for path in files:
        rel_path = path.relative_to(root)
        if _is_hash_excluded(rel_path):
            continue
        data = _static_file_bytes(path, rel_path)
        data_hash = hashlib.sha256(data).digest()
        digest.update(b"FILE\n")
        digest.update(rel_path.as_posix().encode("utf-8"))
        digest.update(b"\n")
        digest.update(data_hash)
        digest.update(b"\n")
    return digest.hexdigest()


def _copy_template(template_dir: Path, job_dir: Path) -> None:
    copied_via_api = _copy_template_via_api(template_dir, job_dir)
    if copied_via_api:
        return

    for path in template_dir.iterdir():
        if _is_excluded(path):
            continue
        target = job_dir / path.name
        if path.is_dir():
            shutil.copytree(path, target, ignore=_ignore_template_items)
        elif path.is_file():
            shutil.copy2(path, target)


def _copy_project_config(job_dir: Path) -> None:
    source = PROJECT_DIR / PROJECT_CONFIG_DIR_NAME
    if source.is_dir():
        shutil.copytree(
            source,
            job_dir / PROJECT_CONFIG_DIR_NAME,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )

def _ignore_template_items(_dir: str, names: list[str]) -> set[str]:
    return {name for name in names if name in EXCLUDED_TEMPLATE_NAMES or name in EXCLUDED_TEMPLATE_DIRS}


def _is_excluded(path: Path) -> bool:
    return path.name in EXCLUDED_TEMPLATE_NAMES or (path.is_dir() and path.name in EXCLUDED_TEMPLATE_DIRS)


def _is_hash_excluded(rel_path: Path) -> bool:
    parts = tuple(part.lower() for part in rel_path.parts)
    if any(part in HASH_EXCLUDED_DIRS for part in parts[:-1]):
        return True
    excluded_names = {name.lower() for name in HASH_EXCLUDED_NAMES}
    return parts[-1] in excluded_names


def _create_unique_job_dir(jobs_dir: Path, requested: str) -> tuple[str, Path]:
    base = _sanitize_name(requested)
    counter = 1
    while True:
        name = base if counter == 1 else f"{base}_{counter}"
        job_dir = jobs_dir / name
        try:
            job_dir.mkdir()
            return name, job_dir
        except FileExistsError:
            time.sleep(0.001)
            counter += 1


def _sanitize_name(value: str) -> str:
    name = _JOB_NAME_RE.sub("_", str(value).strip()).strip("._")
    return name or "job"


def _copy_template_via_api(template_dir: Path, job_dir: Path) -> bool:
    try:
        job_template_api = importlib.import_module("project.job_template.api")
    except ModuleNotFoundError:
        return False

    api_template_dir = Path(getattr(job_template_api, "TEMPLATE_DIR", "")).resolve()
    if template_dir.resolve() != api_template_dir:
        return False

    copy_job_files = getattr(job_template_api, "copy_job_files", None)
    if not callable(copy_job_files):
        return False
    copy_job_files(job_dir)
    return True


def _materialize_parameters(
    template_dir: Path,
    job_dir: Path,
    normalized_values: tuple[float, ...],
) -> tuple[float, ...]:
    job_template_api = importlib.import_module("project.job_template.api")
    materialize = getattr(job_template_api, "materialize_job_parameters", None)
    if not callable(materialize):
        raise RuntimeError("project.job_template.api.materialize_job_parameters is required")
    values = materialize(
        normalized_values,
        source_dir=template_dir,
        job_dir=job_dir,
    )
    return tuple(float(value) for value in values)


def _static_file_bytes(path: Path, rel_path: Path) -> bytes:
    if rel_path.as_posix().lower() != "parameters_constraints.py":
        return path.read_bytes()
    job_template_api = importlib.import_module("project.job_template.api")
    signature = job_template_api.get_parameter_definition_signature(path)
    return json.dumps(
        signature,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8", newline="\n")


def _evaluation_context(
    *,
    run_id: str | None,
    optimization_index: int | None,
    generation_index: int | None,
    population_index: int | None,
) -> dict[str, object]:
    context: dict[str, object] = {}
    if run_id is not None:
        context["run_id"] = str(run_id)
    if optimization_index is not None:
        context["optimization_index"] = int(optimization_index)
    if generation_index is not None:
        context["generation_index"] = int(generation_index)
    if population_index is not None:
        context["population_index"] = int(population_index)
    return context
