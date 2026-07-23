"""Workspace-scoped configuration helpers for evaluation backends."""

from __future__ import annotations

from typing import Any

from ..config import LoadedConfig


FINAL_STATUSES = {"done", "error", "timeout"}
WORKFLOW_SCRIPT_NAME = "workflow.py"
RAW_DATA_DIR_NAME = "rawData"
RAW_DATA_TRANSFER_ZIP_NAME = "rawData.zip"
INDIVIDUAL_METADATA_FILE_NAME = "individual_metadata.json"
CONDOR_SUBMIT_FILE_NAME = "job.sub"
CONDOR_STDOUT_FILE_NAME = "stdout.txt"
CONDOR_STDERR_FILE_NAME = "stderr.txt"
CONDOR_LOG_FILE_NAME = "condor.log"
CONDOR_SUBMIT_STDOUT_FILE_NAME = "condor_submit.stdout.txt"
CONDOR_SUBMIT_STDERR_FILE_NAME = "condor_submit.stderr.txt"
CONDOR_CLUSTER_ID_FILE_NAME = "cluster.id"


def htcondor_submit_exe(config: LoadedConfig) -> str:
    return str(config.HTCONDOR_SUBMIT_EXE)


def htcondor_remove_exe(config: LoadedConfig) -> str:
    return str(config.HTCONDOR_REMOVE_EXE)


def htcondor_history_exe(config: LoadedConfig) -> str:
    return str(config.HTCONDOR_HISTORY_EXE)


def htcondor_poll_sec(config: LoadedConfig) -> float:
    return float(config.HTCONDOR_POLL_SEC)


def htcondor_request_cpus(config: LoadedConfig) -> int:
    return int(config.HTCONDOR_REQUEST_CPUS)


def htcondor_request_memory(config: LoadedConfig) -> str:
    return str(config.HTCONDOR_REQUEST_MEMORY)


def htcondor_request_disk(config: LoadedConfig) -> str:
    return str(config.HTCONDOR_REQUEST_DISK)


def htcondor_environment(config: LoadedConfig) -> str:
    return str(config.HTCONDOR_ENVIRONMENT)


def htcondor_load_profile(config: LoadedConfig) -> bool:
    return _as_bool(config.HTCONDOR_LOAD_PROFILE)


def htcondor_run_as_owner(config: LoadedConfig) -> bool:
    return _as_bool(config.HTCONDOR_RUN_AS_OWNER)


def htcondor_requirements(config: LoadedConfig) -> str:
    parts: list[str] = []
    base = str(config.HTCONDOR_REQUIREMENTS).strip()
    if base:
        parts.append(base)
    allowed = _string_tuple(config.HTCONDOR_ALLOWED_MACHINES)
    excluded = _string_tuple(config.HTCONDOR_EXCLUDED_MACHINES)
    if allowed:
        choices = " || ".join(
            f'Machine =?= "{_classad_string(machine)}"' for machine in allowed
        )
        parts.append(f"({choices})")
    for machine in excluded:
        parts.append(f'(Machine =!= "{_classad_string(machine)}")')
    return " && ".join(parts)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _string_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        text = value.strip()
        if not text or text.lower() in {"*", "all", "none"}:
            return ()
        return tuple(item.strip() for item in text.split(",") if item.strip())
    return tuple(str(item).strip() for item in value if str(item).strip())


def _classad_string(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')
