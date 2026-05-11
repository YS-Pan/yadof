from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from project import config as project_config
except ImportError:  # Allows running from inside the project package directory.
    from .. import config as project_config

PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_JOBS_DIR = PROJECT_DIR / "jobs"
DEFAULT_JOB_TEMPLATE_DIR = PROJECT_DIR / "job_template"

DEFAULT_TIMEOUT_SEC = 60.0 * 60.0
DEFAULT_MODE = "local"
FINAL_STATUSES = {"done", "error", "timeout"}
WORKFLOW_SCRIPT_NAME = "workflow.py"
RAW_DATA_DIR_NAME = "rawData"


def default_jobs_dir() -> Path:
    return Path(getattr(project_config, "JOBS_DIR", DEFAULT_JOBS_DIR))


def default_timeout_sec() -> float:
    return float(_first_config_value(("EVALUATION_TIMEOUT_SEC", "EVALUATE_TIMEOUT_SEC"), DEFAULT_TIMEOUT_SEC))


def default_mode() -> str:
    return str(getattr(project_config, "EVALUATION_MODE", DEFAULT_MODE))


def _first_config_value(names: tuple[str, ...], fallback: Any) -> Any:
    for name in names:
        if hasattr(project_config, name):
            return getattr(project_config, name)
    return fallback
