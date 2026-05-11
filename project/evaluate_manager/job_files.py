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

from .config import RAW_DATA_DIR_NAME
from .types import JobSpec

EXCLUDED_TEMPLATE_NAMES = {
    "__pycache__",
    "__init__.py",
    "api.py",
    "calc_cost.py",
    "cost.json",
    "metadata.json",
    "metaData.json",
}
EXCLUDED_TEMPLATE_DIRS = {"__pycache__", RAW_DATA_DIR_NAME}
HASH_EXCLUDED_NAMES = {
    "cost.json",
    "job_input.json",
    "metadata.json",
    "metadata.json.tmp",
    "metaData.json",
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
) -> JobSpec:
    jobs_dir = Path(jobs_dir)
    template_dir = Path(job_template_dir)
    if not template_dir.is_dir():
        raise FileNotFoundError(f"job_template directory does not exist: {template_dir}")

    jobs_dir.mkdir(parents=True, exist_ok=True)
    name = _unique_job_name(jobs_dir, job_name or new_job_name())
    job_dir = jobs_dir / name
    job_dir.mkdir()

    _copy_template(template_dir, job_dir)
    (job_dir / RAW_DATA_DIR_NAME).mkdir(exist_ok=True)
    job_static_hash = prepared_job_static_hash(job_dir)

    normalized_values = tuple(float(x) for x in variables)
    values = _denormalize_variables(normalized_values)
    _write_json(
        job_dir / "job_input.json",
        {
            "job_name": name,
            "normalized_variables": list(normalized_values),
            "unnormalized_variables": list(values),
        },
    )
    metadata = {
        "job_name": name,
        "status": "created",
        "job_static_hash": job_static_hash,
        "normalized_variables": list(normalized_values),
        "unnormalized_variables": list(values),
    }
    _write_json(job_dir / "metadata.json", metadata)
    _write_json(job_dir / "metaData.json", metadata)
    return JobSpec(name=name, directory=job_dir, unnormalized_variables=values)


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
        data_hash = hashlib.sha256(path.read_bytes()).digest()
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


def _unique_job_name(jobs_dir: Path, requested: str) -> str:
    base = _sanitize_name(requested)
    name = base
    counter = 1
    while (jobs_dir / name).exists():
        time.sleep(0.001)
        counter += 1
        name = f"{base}_{counter}"
    return name


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


def _denormalize_variables(normalized_values: tuple[float, ...]) -> tuple[float, ...]:
    try:
        job_template_api = importlib.import_module("project.job_template.api")
    except ModuleNotFoundError:
        return normalized_values

    denormalize = getattr(job_template_api, "denormalize_variables", None)
    if not callable(denormalize):
        return normalized_values
    return tuple(float(value) for value in denormalize(normalized_values))


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8", newline="\n")
