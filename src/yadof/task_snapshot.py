"""Generation-scoped immutable task-source snapshots and fingerprints."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
from types import MappingProxyType
import shutil
import tempfile
from typing import Mapping

from .config import LoadedConfig
from .job_template import api as job_template_api
from .workspace import WorkspaceContext


RECORDER_CONFIG_NAMES = frozenset(
    {
        "RECORDED_DATA_DIR",
        "HISTORY_SEGMENT_MAX_CANDIDATES",
        "HISTORY_SEGMENT_TARGET_BYTES",
        "HISTORY_MAX_CANDIDATE_BYTES",
        "HISTORY_UNPUBLISHED_MAX_CANDIDATES",
        "HISTORY_UNPUBLISHED_MAX_BYTES",
        "HISTORY_WRITER_MAX_CONSECUTIVE_FAILURES",
    }
)


@dataclass(frozen=True, slots=True)
class GenerationTaskSnapshot:
    """One coherent task/config definition used by a complete generation."""

    config: LoadedConfig
    snapshot_root: Path
    submit_directory: Path
    job_template_directory: Path
    source_directory: Path
    interpretation_fingerprint: str
    evaluation_fingerprint: str
    optimization_fingerprint: str
    task_snapshot_id: str
    parameter_names: tuple[str, ...]
    objective_names: tuple[str, ...]
    source_hashes: Mapping[str, str]

    def close(self) -> None:
        shutil.rmtree(self.snapshot_root, ignore_errors=True)


def create_generation_snapshot(
    config: LoadedConfig,
    *,
    program_source_hashes: Mapping[str, str] | None = None,
    program_fingerprint: str | None = None,
) -> GenerationTaskSnapshot:
    """Capture complete submit and evaluate trees before generation work starts."""

    source_submit = config.workspace.submit_dir.resolve()
    source_job_template = config.workspace.job_template_dir.resolve()
    frozen_program_hashes = _program_source_hashes(program_source_hashes)
    excluded_submit_sources = frozenset(
        key.removeprefix("submit/") for key in frozen_program_hashes
    )
    snapshot_root = Path(tempfile.mkdtemp(prefix="yadof-task-snapshot-"))
    snapshot_submit = snapshot_root / "submit"
    snapshot_job_template = snapshot_root / "job_template"
    try:
        _copy_source_tree(
            source_submit,
            snapshot_submit,
            evaluate_side=False,
            excluded_relatives=excluded_submit_sources,
        )
        _copy_source_tree(
            source_job_template,
            snapshot_job_template,
            evaluate_side=True,
            excluded_relatives=frozenset(),
        )
        snapshot_workspace = replace(
            config.workspace,
            submit_dir=snapshot_submit,
            job_template_dir=snapshot_job_template,
            requires_optimization_source=program_fingerprint is None,
        )
        values = dict(config.values)
        values["JOB_TEMPLATE_DIR"] = snapshot_job_template
        snapshot_config = replace(
            config,
            workspace=snapshot_workspace,
            values=MappingProxyType(values),
        )
        submit_hashes = _source_hashes(snapshot_submit, prefix="submit")
        job_hashes = _source_hashes(snapshot_job_template, prefix="job_template")
        hashes = {**submit_hashes, **job_hashes, **frozen_program_hashes}
        semantic_config = _semantic_config(config)
        interpretation_fingerprint = _hash_json(
            {
                "parameter_source": hashes.get(
                    "job_template/parameters_constraints.py",
                    "",
                ),
                "submit_sources": submit_hashes,
            }
        )
        evaluation_fingerprint = _hash_json(
            {
                "job_template_sources": job_hashes,
                "config": semantic_config,
            }
        )
        optimization_fingerprint = (
            _sha256(program_fingerprint, "program_fingerprint")
            if program_fingerprint is not None
            else _hash_json(
                {
                    "submit_sources": submit_hashes,
                    "config": semantic_config,
                }
            )
        )
        task_snapshot_id = _hash_json(
            {
                "sources": dict(hashes),
                "config": semantic_config,
            }
        )
        parameter_names = tuple(
            job_template_api.get_parameter_names(snapshot_workspace)
        )
        objective_names = tuple(
            job_template_api.get_objective_names(snapshot_workspace)
        )
        return GenerationTaskSnapshot(
            config=snapshot_config,
            snapshot_root=snapshot_root,
            submit_directory=snapshot_submit,
            job_template_directory=snapshot_job_template,
            source_directory=snapshot_job_template,
            interpretation_fingerprint=interpretation_fingerprint,
            evaluation_fingerprint=evaluation_fingerprint,
            optimization_fingerprint=optimization_fingerprint,
            task_snapshot_id=task_snapshot_id,
            parameter_names=parameter_names,
            objective_names=objective_names,
            source_hashes=MappingProxyType(hashes),
        )
    except Exception:
        shutil.rmtree(snapshot_root, ignore_errors=True)
        raise


def _copy_source_tree(
    source_root: Path,
    destination_root: Path,
    *,
    evaluate_side: bool,
    excluded_relatives: frozenset[str],
) -> None:
    if not source_root.is_dir():
        raise FileNotFoundError(source_root)
    destination_root.mkdir(parents=True, exist_ok=True)
    for source in sorted(source_root.rglob("*"), key=lambda item: item.as_posix().casefold()):
        relative = source.relative_to(source_root)
        relative_text = relative.as_posix()
        if relative_text in excluded_relatives:
            continue
        if any(
            relative_text.startswith(f"{excluded.rstrip('/')}/")
            for excluded in excluded_relatives
        ):
            continue
        if any(part in {"__pycache__", ".pytest_cache"} for part in relative.parts):
            continue
        if evaluate_side and "rawData" in relative.parts:
            continue
        if (
            evaluate_side
            and len(relative.parts) == 1
            and source.name.lower().endswith((".aedtresults", ".aedt.lock"))
        ):
            continue
        destination = destination_root / relative
        if source.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        if not source.is_file():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def _source_hashes(root: Path, *, prefix: str) -> dict[str, str]:
    output: dict[str, str] = {}
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        output[f"{prefix}/{relative}"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return output


def _program_source_hashes(
    value: Mapping[str, str] | None,
) -> dict[str, str]:
    output: dict[str, str] = {}
    for key, digest in ({} if value is None else value).items():
        name = str(key).replace("\\", "/")
        if not name.startswith("submit/") or name.endswith("/"):
            raise ValueError("program source hashes must use submit/<file> keys")
        relative = Path(name.removeprefix("submit/"))
        if relative.is_absolute() or not relative.parts or ".." in relative.parts:
            raise ValueError("program source hash path must stay below submit/")
        output[name] = _sha256(digest, f"program source hash {name}")
    return output


def _semantic_config(config: LoadedConfig) -> dict[str, object]:
    return {
        name: _json_value(value)
        for name, value in sorted(config.values.items())
        if name not in RECORDER_CONFIG_NAMES
    }


def _json_value(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


def _hash_json(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _sha256(value: object, label: str) -> str:
    text = str(value).strip().lower()
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ValueError(f"{label} must be a SHA-256 hex digest")
    return text


__all__ = [
    "GenerationTaskSnapshot",
    "RECORDER_CONFIG_NAMES",
    "create_generation_snapshot",
]
