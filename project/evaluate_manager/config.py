from __future__ import annotations

from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_JOBS_DIR = PROJECT_DIR / "jobs"
DEFAULT_JOB_TEMPLATE_DIR = PROJECT_DIR / "job_template"

DEFAULT_TIMEOUT_SEC = 60.0 * 60.0
FINAL_STATUSES = {"done", "error", "timeout"}
WORKFLOW_SCRIPT_NAME = "workflow.py"
RAW_DATA_DIR_NAME = "rawData"
