from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import time
from typing import Mapping, Sequence

from .config import (
    CONDOR_CLUSTER_ID_FILE_NAME,
    CONDOR_LOG_FILE_NAME,
    CONDOR_STDERR_FILE_NAME,
    CONDOR_STDOUT_FILE_NAME,
    CONDOR_SUBMIT_FILE_NAME,
    CONDOR_SUBMIT_STDERR_FILE_NAME,
    CONDOR_SUBMIT_STDOUT_FILE_NAME,
    INDIVIDUAL_METADATA_FILE_NAME,
    RAW_DATA_DIR_NAME,
    WORKFLOW_SCRIPT_NAME,
    htcondor_environment,
    htcondor_load_profile,
    htcondor_poll_sec,
    htcondor_remove_exe,
    htcondor_request_cpus,
    htcondor_request_disk,
    htcondor_request_memory,
    htcondor_requirements,
    htcondor_run_as_owner,
    htcondor_submit_exe,
)
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


_CLUSTER_RE = re.compile(r"submitted to cluster\s+(\d+)", re.IGNORECASE)
_TERMINAL_LOG_MARKERS = {
    "terminated": "Job terminated",
    "held": "Job was held",
    "aborted": "Job was aborted",
    "removed": "Job was removed",
}
_SUBMIT_ARTIFACTS = {
    CONDOR_SUBMIT_FILE_NAME,
    CONDOR_STDOUT_FILE_NAME,
    CONDOR_STDERR_FILE_NAME,
    CONDOR_LOG_FILE_NAME,
    CONDOR_SUBMIT_STDOUT_FILE_NAME,
    CONDOR_SUBMIT_STDERR_FILE_NAME,
    CONDOR_CLUSTER_ID_FILE_NAME,
}
_RUNTIME_ARTIFACTS = {
    INDIVIDUAL_METADATA_FILE_NAME,
    "metadata.json",
    "metaData.json",
    "metadata.json.tmp",
    "metaData.json.tmp",
    "cost.json",
    "calc_cost.py",
}
_SANDBOX_ENV_DIRS = ("._home", "._appdata", "._localappdata", "._tmp")


@dataclass(frozen=True)
class CondorSubmission:
    job: JobSpec
    submit_file: Path
    cluster_id: int | None
    submitted_at: str
    stdout: str
    stderr: str


class CondorSubmitError(RuntimeError):
    def __init__(self, message: str, *, returncode: int | None, stdout: str = "", stderr: str = "") -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def run_condor_jobs(
    jobs: Sequence[JobSpec],
    *,
    timeout_sec: float,
    env: Mapping[str, str] | None = None,
) -> tuple[JobResult, ...]:
    """Submit jobs to HTCondor, wait for job-local outputs, and collect results.

    This function deliberately treats HTCondor as an external backend. If the
    local installation is stale or broken, submit failures are captured as
    per-job metadata; the function does not attempt to repair the pool.
    """

    results_by_name: dict[str, JobResult] = {}
    pending: dict[str, CondorSubmission] = {}
    for job in jobs:
        try:
            submission = submit_condor_job(job, env=env)
        except Exception as exc:  # noqa: BLE001 - preserve per-individual failure isolation.
            results_by_name[job.name] = submit_failure_result(job, exc)
            continue
        pending[job.name] = submission

    deadline = time.monotonic() + float(timeout_sec)
    poll_sec = max(0.1, htcondor_poll_sec())
    while pending and time.monotonic() < deadline:
        for job_name, submission in list(pending.items()):
            terminal_reason = terminal_log_reason(submission.job.directory)
            if terminal_reason is None and not read_individual_metadata(submission.job.directory):
                continue
            results_by_name[job_name] = collect_condor_result(
                submission.job,
                submission=submission,
                timed_out=False,
                terminal_reason=terminal_reason,
            )
            pending.pop(job_name, None)
        if pending:
            time.sleep(poll_sec)

    for job_name, submission in list(pending.items()):
        remove_error = remove_condor_job(submission)
        results_by_name[job_name] = collect_condor_result(
            submission.job,
            submission=submission,
            timed_out=True,
            terminal_reason="timeout",
            remove_error=remove_error,
        )
        pending.pop(job_name, None)

    return tuple(results_by_name[job.name] for job in jobs)


def submit_condor_job(job: JobSpec, *, env: Mapping[str, str] | None = None) -> CondorSubmission:
    submit_file = write_condor_submit_file(job, env=env)
    metadata = base_metadata(job, engine="htcondor")
    metadata.update(status="submitting", condor_submit_file=submit_file.name, condor_submitted_at=now_text())
    write_metadata(job.directory, metadata)

    try:
        completed = subprocess.run(
            [htcondor_submit_exe(), submit_file.name],
            cwd=str(job.directory),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise CondorSubmitError(str(exc), returncode=None) from exc

    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    (job.directory / CONDOR_SUBMIT_STDOUT_FILE_NAME).write_text(stdout, encoding="utf-8", newline="\n")
    (job.directory / CONDOR_SUBMIT_STDERR_FILE_NAME).write_text(stderr, encoding="utf-8", newline="\n")
    if completed.returncode != 0:
        raise CondorSubmitError(
            f"condor_submit failed with return code {completed.returncode}",
            returncode=int(completed.returncode),
            stdout=stdout,
            stderr=stderr,
        )

    cluster_id = parse_cluster_id(stdout)
    if cluster_id is not None:
        (job.directory / CONDOR_CLUSTER_ID_FILE_NAME).write_text(str(cluster_id), encoding="utf-8", newline="\n")

    metadata.update(
        status="submitted",
        condor_cluster_id=cluster_id,
        condor_submit_stdout_tail=tail(stdout),
        condor_submit_stderr_tail=tail(stderr),
    )
    write_metadata(job.directory, metadata)
    return CondorSubmission(
        job=job,
        submit_file=submit_file,
        cluster_id=cluster_id,
        submitted_at=str(metadata["condor_submitted_at"]),
        stdout=stdout,
        stderr=stderr,
    )


def write_condor_submit_file(job: JobSpec, *, env: Mapping[str, str] | None = None) -> Path:
    if htcondor_run_as_owner() and htcondor_load_profile():
        raise ValueError("HTCondor Windows config cannot combine run_as_owner=True with load_profile=True")

    for dirname in _SANDBOX_ENV_DIRS:
        (job.directory / dirname).mkdir(exist_ok=True)

    inputs = transfer_input_files(job.directory, executable_name=WORKFLOW_SCRIPT_NAME)
    requirements = htcondor_requirements().strip()
    environment = condor_environment_string(env)
    lines: list[str] = [
        "# Auto-generated by project.evaluate_manager.condor_runner",
        "universe = vanilla",
        f"executable = {WORKFLOW_SCRIPT_NAME}",
        "initialdir = .",
        "getenv = False",
    ]
    if environment:
        lines.append(f'environment = "{environment}"')
    lines.append(f"load_profile = {_condor_bool(htcondor_load_profile())}")
    lines.append(f"run_as_owner = {_condor_bool(htcondor_run_as_owner())}")
    if requirements:
        lines.append(f"requirements = {requirements}")
    lines.extend(
        [
            "should_transfer_files = YES",
            "when_to_transfer_output = ON_EXIT",
            "transfer_executable = True",
        ]
    )
    if inputs:
        lines.append(f"transfer_input_files = {','.join(inputs)}")
    lines.extend(
        [
            f"output = {CONDOR_STDOUT_FILE_NAME}",
            f"error = {CONDOR_STDERR_FILE_NAME}",
            f"log = {CONDOR_LOG_FILE_NAME}",
            f"request_cpus = {htcondor_request_cpus()}",
            f"request_memory = {htcondor_request_memory()}",
            f"request_disk = {htcondor_request_disk()}",
            "notification = never",
            f"transfer_output_files = {RAW_DATA_DIR_NAME},{INDIVIDUAL_METADATA_FILE_NAME}",
            "queue 1",
            "",
        ]
    )
    path = job.directory / CONDOR_SUBMIT_FILE_NAME
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return path


def transfer_input_files(job_dir: Path, *, executable_name: str) -> tuple[str, ...]:
    files: list[str] = []
    for path in sorted(job_dir.iterdir(), key=lambda item: item.name.lower()):
        if path.name == executable_name:
            continue
        if path.name in _SUBMIT_ARTIFACTS or path.name in _RUNTIME_ARTIFACTS:
            continue
        if path.name == RAW_DATA_DIR_NAME or path.name == "__pycache__":
            continue
        files.append(_quote_submit_atom(path.name))
    return tuple(files)


def condor_environment_string(extra_env: Mapping[str, str] | None = None) -> str:
    parts: list[str] = []
    configured = htcondor_environment().strip()
    if configured:
        parts.append(configured)
    for key, value in dict(extra_env or {}).items():
        parts.append(f"{key}={value}")
    return ";".join(parts)


def parse_cluster_id(stdout: str) -> int | None:
    match = _CLUSTER_RE.search(stdout or "")
    return int(match.group(1)) if match else None


def terminal_log_reason(job_dir: Path) -> str | None:
    log_path = job_dir / CONDOR_LOG_FILE_NAME
    if not log_path.is_file():
        return None
    text = log_path.read_text(encoding="utf-8", errors="ignore")
    for reason, marker in _TERMINAL_LOG_MARKERS.items():
        if marker in text:
            return reason
    return None


def collect_condor_result(
    job: JobSpec,
    *,
    submission: CondorSubmission,
    timed_out: bool,
    terminal_reason: str | None,
    remove_error: str | None = None,
) -> JobResult:
    raw_paths = raw_data_paths(job.directory)
    individual_metadata = read_individual_metadata(job.directory)
    metadata = base_metadata(job, engine="htcondor")
    metadata.update(individual_metadata)

    if timed_out:
        status = "timeout"
        error = f"HTCondor job exceeded timeout_sec while waiting for job-local outputs"
    elif terminal_reason in {"held", "aborted", "removed"}:
        status = "error"
        error = f"HTCondor reported terminal state: {terminal_reason}"
    elif raw_paths and str(individual_metadata.get("status", "")).lower() != "error":
        status = "done"
        error = None
    elif str(individual_metadata.get("status", "")).lower() == "error":
        status = "error"
        error = str(individual_metadata.get("error_message") or "workflow reported error")
    else:
        status = "error"
        error = f"HTCondor job finished without .npz files under {RAW_DATA_DIR_NAME}/"

    metadata.update(
        status=status,
        timed_out=timed_out,
        runner_finished_at=now_text(),
        raw_data_files=[path.name for path in raw_paths],
        stdout_tail=_read_tail(job.directory / CONDOR_STDOUT_FILE_NAME),
        stderr_tail=_read_tail(job.directory / CONDOR_STDERR_FILE_NAME),
        condor_cluster_id=submission.cluster_id,
        condor_submit_file=submission.submit_file.name,
        condor_log_file=CONDOR_LOG_FILE_NAME,
        condor_terminal_reason=terminal_reason,
        condor_submit_stdout_tail=tail(submission.stdout),
        condor_submit_stderr_tail=tail(submission.stderr),
    )
    if error is not None:
        metadata["error"] = error
    if remove_error is not None:
        metadata["condor_remove_error"] = remove_error
    write_metadata(job.directory, metadata)
    return result_from_metadata(job, metadata, raw_paths)


def submit_failure_result(job: JobSpec, exc: BaseException) -> JobResult:
    metadata = base_metadata(job, engine="htcondor")
    metadata.update(
        status="error",
        failure_stage="submit",
        error_type=type(exc).__name__,
        error_message=str(exc),
        failed_at=now_text(),
        condor_submit_file=CONDOR_SUBMIT_FILE_NAME,
    )
    if isinstance(exc, CondorSubmitError):
        metadata.update(
            condor_submit_returncode=exc.returncode,
            condor_submit_stdout_tail=tail(exc.stdout),
            condor_submit_stderr_tail=tail(exc.stderr),
        )
    write_metadata(job.directory, metadata)
    return result_from_metadata(job, metadata)


def remove_condor_job(submission: CondorSubmission) -> str | None:
    if submission.cluster_id is None:
        return None
    try:
        completed = subprocess.run(
            [htcondor_remove_exe(), str(submission.cluster_id)],
            cwd=str(submission.job.directory),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        return str(exc)
    if completed.returncode == 0:
        return None
    return (completed.stderr or completed.stdout or f"condor_rm exited with {completed.returncode}").strip()


def _read_tail(path: Path) -> str:
    if not path.is_file():
        return ""
    return tail(path.read_text(encoding="utf-8", errors="ignore"))


def _quote_submit_atom(value: str) -> str:
    return f'"{value}"' if any(char in value for char in (" ", ",")) else value


def _condor_bool(value: bool) -> str:
    return "True" if value else "False"
