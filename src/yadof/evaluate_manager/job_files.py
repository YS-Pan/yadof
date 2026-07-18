"""Compose package worker support with one workspace's mutable task payload."""

from __future__ import annotations

import hashlib
from importlib import resources
import json
import os
import re
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping

from .._version import __version__
from ..config import LoadedConfig, load_config
from ..job_template import get_parameter_definition_signature, materialize_job_parameters
from ..workspace import WorkspaceContext, resolve_workspace
from ..workspace_manifest import WorkspaceMarkerError, read_workspace_marker
from .types import JobSpec


RAW_DATA_DIR_NAME = "rawData"
WORKER_CONFIG_FILE_NAME = "yadof_worker_config.json"
PACKAGE_WORKER_FILES = ("worker_misc.py", "sitecustomize.py")
RESERVED_WORKER_FILE_NAMES = frozenset(
    (*PACKAGE_WORKER_FILES, WORKER_CONFIG_FILE_NAME)
)

EXCLUDED_TASK_NAMES = {
    "__pycache__",
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
    "parameters_constraints.py",
}
EXCLUDED_TASK_DIRS = {
    "__pycache__",
    ".pytest_cache",
    "._appdata",
    "._home",
    "._localappdata",
    "._tmp",
    "_tmp",
    "history",
    RAW_DATA_DIR_NAME,
}
RECURSIVE_EXCLUDED_TASK_DIRS = {"__pycache__", ".pytest_cache"}
HASH_EXCLUDED_NAMES = {
    "cost.json",
    "metadata.json",
    "metadata.json.tmp",
    "metaData.json",
    "individual_metadata.json",
    "individual_metadata.json.tmp",
    WORKER_CONFIG_FILE_NAME,
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


class JobPreparationError(RuntimeError):
    """Raised when package support and workspace task content cannot be composed."""


def new_job_name(prefix: str = "job") -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return f"{_sanitize_name(prefix)}_{stamp}"


def validate_task_payload(config: LoadedConfig) -> None:
    """Reject task files that would overwrite package-owned job support."""

    reserved = {name.casefold(): name for name in RESERVED_WORKER_FILE_NAMES}
    collisions = []
    for path in config.workspace.job_template_dir.iterdir():
        if not path.is_file():
            continue
        canonical = reserved.get(path.name.casefold())
        if canonical is not None:
            collisions.append((path, canonical))
    if collisions:
        details = "; ".join(
            f"{path} conflicts with reserved job filename {canonical!r}"
            for path, canonical in collisions
        )
        raise JobPreparationError(
            "workspace task payload collides with package worker support: "
            f"{details}. Rename or remove the task file; yadof never overwrites it."
        )


def prepare_job(
    workspace: WorkspaceContext | str | os.PathLike[str],
    variables: Iterable[float],
    *,
    config: LoadedConfig | None = None,
    job_name: str | None = None,
    mode: str = "local",
    timeout_sec: float | None,
    run_id: str | None = None,
    optimization_index: int | None = None,
    generation_index: int | None = None,
    population_index: int | None = None,
) -> JobSpec:
    """Prepare one workspace-owned job from package and task inputs."""

    selected_workspace = resolve_workspace(workspace)
    effective = load_config(selected_workspace) if config is None else config
    if effective.workspace.root != selected_workspace.root:
        raise JobPreparationError(
            "prepared-job config belongs to a different workspace: "
            f"{effective.workspace.root} != {selected_workspace.root}"
        )
    validate_task_payload(effective)
    jobs_dir = effective.workspace.jobs_dir
    jobs_dir.mkdir(parents=True, exist_ok=True)
    name, job_dir = _create_unique_job_dir(jobs_dir, job_name or new_job_name())

    normalized_values = tuple(float(value) for value in variables)
    _copy_task_payload(effective.workspace.job_template_dir, job_dir)
    values = materialize_job_parameters(
        effective.workspace,
        normalized_values,
        job_dir=job_dir,
    )

    workspace_identity = _workspace_identity(effective.workspace)
    config_summary = effective_worker_config_summary(
        effective,
        mode=mode,
        timeout_sec=timeout_sec,
    )
    worker_config = {
        "schema_version": 1,
        "yadof_version": __version__,
        "workspace_identity": workspace_identity,
        "effective_config": config_summary,
    }
    _copy_package_worker_files(job_dir)
    _write_json(job_dir / WORKER_CONFIG_FILE_NAME, worker_config)
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
        "yadof_version": __version__,
        "workspace_identity": workspace_identity,
        "effective_config_summary": config_summary,
        "worker_config_file": WORKER_CONFIG_FILE_NAME,
        **evaluation_context,
    }
    _write_json(job_dir / "metadata.json", metadata)
    _write_json(job_dir / "metaData.json", metadata)
    return JobSpec(
        name=name,
        directory=job_dir,
        unnormalized_variables=tuple(float(value) for value in values),
        normalized_variables=normalized_values,
        run_id=run_id,
        optimization_index=optimization_index,
        generation_index=generation_index,
        population_index=population_index,
    )


def effective_worker_config_summary(
    config: LoadedConfig,
    *,
    mode: str,
    timeout_sec: float | None,
) -> dict[str, dict[str, object]]:
    """Return only local worker settings needed for execution and diagnosis."""

    summary: dict[str, dict[str, object]] = {}
    runtime_values: Mapping[str, object] = {
        "EVALUATION_MODE": str(mode),
        "EVALUATION_TIMEOUT_SEC": timeout_sec,
        "LOCAL_EVALUATION_MAX_WORKERS": int(config.LOCAL_EVALUATION_MAX_WORKERS),
    }
    if str(mode).strip().lower() == "distributed":
        runtime_values = {
            **runtime_values,
            **{
                name: config[name]
                for name in config.values
                if name.startswith("HTCONDOR_")
                or name == "YADOF_RESOURCE_RETRY_DOUBLINGS"
            },
        }
    for name, value in runtime_values.items():
        source = config.source_for(name)
        if name == "EVALUATION_MODE" and value != config[name]:
            source = "runtime override"
        elif name == "EVALUATION_TIMEOUT_SEC" and value is None:
            source = "no-timeout smoke-test override"
        elif name == "EVALUATION_TIMEOUT_SEC" and value != config[name]:
            source = "runtime override"
        summary[name] = {"value": _json_value(value), "source": source}
    return summary


def prepared_job_static_hash(job_dir: str | Path) -> str:
    """Return a stable static-input hash that ignores assigned parameter values."""

    root = Path(job_dir).resolve()
    digest = hashlib.sha256()
    files = sorted(
        (path for path in root.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(root).as_posix().lower(),
    )
    for path in files:
        rel_path = path.relative_to(root)
        if _is_hash_excluded(rel_path):
            continue
        data = _static_file_bytes(path, rel_path, root)
        digest.update(b"FILE\n")
        digest.update(rel_path.as_posix().encode("utf-8"))
        digest.update(b"\n")
        digest.update(hashlib.sha256(data).digest())
        digest.update(b"\n")
    return digest.hexdigest()


def _copy_task_payload(template_dir: Path, job_dir: Path) -> None:
    for source in template_dir.iterdir():
        if _is_excluded(source):
            continue
        target = job_dir / source.name
        if source.is_dir():
            shutil.copytree(source, target, ignore=_ignore_task_items)
        elif source.is_file():
            shutil.copy2(source, target)


def _copy_package_worker_files(job_dir: Path) -> None:
    root = resources.files("yadof.evaluate_manager.worker_files")
    for name in PACKAGE_WORKER_FILES:
        destination = job_dir / name
        if destination.exists():
            raise JobPreparationError(
                f"refusing to overwrite package-reserved job file: {destination}"
            )
        destination.write_bytes(root.joinpath(name).read_bytes())


def _ignore_task_items(_directory: str, names: list[str]) -> set[str]:
    return {
        name
        for name in names
        if name in RECURSIVE_EXCLUDED_TASK_DIRS
        or name.endswith((".pyc", ".pyo"))
    }


def _is_excluded(path: Path) -> bool:
    return path.name in EXCLUDED_TASK_NAMES or (
        path.is_dir() and path.name in EXCLUDED_TASK_DIRS
    )


def _is_hash_excluded(rel_path: Path) -> bool:
    parts = tuple(part.lower() for part in rel_path.parts)
    if any(part in HASH_EXCLUDED_DIRS for part in parts[:-1]):
        return True
    return parts[-1] in {name.lower() for name in HASH_EXCLUDED_NAMES}


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


def _static_file_bytes(path: Path, rel_path: Path, root: Path) -> bytes:
    if rel_path.as_posix().lower() != "parameters_constraints.py":
        return path.read_bytes()
    job_workspace = WorkspaceContext.from_path(root, job_template_dir=".")
    signature = get_parameter_definition_signature(job_workspace)
    return json.dumps(
        signature,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _workspace_identity(workspace: WorkspaceContext) -> dict[str, object]:
    identity: dict[str, object] = {"root": str(workspace.root)}
    try:
        marker = read_workspace_marker(workspace.root)
    except WorkspaceMarkerError as exc:
        identity["marker"] = None
        identity["marker_error"] = str(exc)
    else:
        identity["marker"] = marker.to_dict()
    return identity


def _json_value(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    return value


def _write_json(path: Path, data: Mapping[str, object]) -> None:
    path.write_text(
        json.dumps(dict(data), ensure_ascii=True, indent=2),
        encoding="utf-8",
        newline="\n",
    )


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


__all__ = [
    "JobPreparationError",
    "PACKAGE_WORKER_FILES",
    "RESERVED_WORKER_FILE_NAMES",
    "WORKER_CONFIG_FILE_NAME",
    "effective_worker_config_summary",
    "new_job_name",
    "prepare_job",
    "prepared_job_static_hash",
    "validate_task_payload",
]
