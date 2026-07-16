from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Callable, Mapping, Sequence

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
    RAW_DATA_TRANSFER_ZIP_NAME,
    WORKFLOW_SCRIPT_NAME,
    htcondor_environment,
    htcondor_history_exe,
    htcondor_load_profile,
    htcondor_poll_sec,
    htcondor_remove_exe,
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
from .resource_requests import HTCondorResourceRequest, request_for_job
from .time_limits import HTCondorTimeLimit, time_limit_for_job
from .types import JobResult, JobSpec


_CLUSTER_RE = re.compile(r"submitted to cluster\s+(\d+)", re.IGNORECASE)
_RETURN_VALUE_RE = re.compile(r"Normal termination \(return value ([^)]+)\)", re.IGNORECASE)
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
    "metadata.json",
    "metaData.json",
    "metadata.json.tmp",
    "metaData.json.tmp",
    INDIVIDUAL_METADATA_FILE_NAME,
    f"{INDIVIDUAL_METADATA_FILE_NAME}.tmp",
    "cost.json",
    "calc_cost.py",
    RAW_DATA_DIR_NAME,
    RAW_DATA_TRANSFER_ZIP_NAME,
    f"{RAW_DATA_TRANSFER_ZIP_NAME}.tmp",
}
_SANDBOX_ENV_DIRS = ("._home", "._appdata", "._localappdata", "._tmp")
_BATCH_LOG_FILE_NAME = "batch.log"
_WINDOWS_STATUS_MESSAGES = {
    0xC0000022: (
        "STATUS_ACCESS_DENIED",
        "Windows denied starting the transferred workflow.py executable or loading one of its DLLs on the worker. "
        "Check ACLs for the HTCondor slot account on workflow.py, transferred inputs, and the Python "
        "environment reached by the worker's .py file association.",
    ),
}


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
    timeout_sec: float | None,
    env: Mapping[str, str] | None = None,
    after_jobs_submitted: Callable[[], object] | None = None,
) -> tuple[JobResult, ...]:
    """Submit jobs to HTCondor, wait for job-local outputs, and collect results.

    This function deliberately treats HTCondor as an external backend. If the
    local installation is stale or broken, submit failures are captured as
    per-job metadata; the function does not attempt to repair the pool.
    """

    results_by_name: dict[str, JobResult] = {}
    pending: dict[str, CondorSubmission] = {}
    total = len(jobs)
    submit_failures = 0
    _progress(f"htcondor: submitting {total} jobs")
    _progress(f"htcondor: submit progress 0/{total}; queued=0; submit_failures=0; last_cluster=none")
    for index, job in enumerate(jobs, start=1):
        try:
            submission = submit_condor_job(job, env=env)
        except Exception as exc:  # noqa: BLE001 - preserve per-individual failure isolation.
            results_by_name[job.name] = submit_failure_result(job, exc)
            submit_failures += 1
            _progress(f"htcondor: submit failed {index}/{total}: {job.name}")
            continue
        pending[job.name] = submission
        if index == 1 or index % 25 == 0 or index == total:
            cluster = submission.cluster_id if submission.cluster_id is not None else "unknown"
            _progress(
                f"htcondor: submit progress {index}/{total}; queued={len(pending)}; "
                f"submit_failures={submit_failures}; last_cluster={cluster}"
            )

    if pending:
        _run_after_jobs_submitted(after_jobs_submitted)

    deadline = None if timeout_sec is None else time.monotonic() + float(timeout_sec)
    poll_sec = max(0.1, htcondor_poll_sec())
    last_report = 0.0
    if pending:
        _progress(f"htcondor: waiting for {len(pending)} jobs")
    while pending and (deadline is None or time.monotonic() < deadline):
        completed_now = 0
        for job_name, submission in list(pending.items()):
            terminal_reason = terminal_log_reason(submission.job.directory)
            individual_metadata = read_individual_metadata(submission.job.directory)
            if terminal_reason is None and not _job_local_outputs_ready(submission.job.directory, individual_metadata):
                continue
            try:
                results_by_name[job_name] = collect_condor_result(
                    submission.job,
                    submission=submission,
                    timed_out=False,
                    terminal_reason=terminal_reason,
                )
            except Exception as exc:  # noqa: BLE001 - isolate one bad returned payload.
                results_by_name[job_name] = collect_failure_result(
                    submission.job,
                    submission=submission,
                    exc=exc,
                    terminal_reason=terminal_reason,
                )
            pending.pop(job_name, None)
            completed_now += 1
        now = time.monotonic()
        if completed_now or now >= last_report + poll_sec:
            _progress(f"htcondor: pending={len(pending)}/{total}")
            last_report = now
        if pending:
            time.sleep(poll_sec)

    timed_out_count = len(pending)
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
    if timed_out_count:
        _progress(f"htcondor: timed out {timed_out_count} jobs")
    _progress(f"htcondor: collected {len(results_by_name)}/{total} results")

    return tuple(results_by_name[job.name] for job in jobs)


def _run_after_jobs_submitted(callback: Callable[[], object] | None) -> None:
    if callback is None:
        return
    try:
        callback()
    except Exception as exc:  # noqa: BLE001 - keep submitted jobs alive if training scheduling fails.
        _progress(f"htcondor: after-submit callback failed: {exc.__class__.__name__}: {exc}")

def submit_condor_job(job: JobSpec, *, env: Mapping[str, str] | None = None) -> CondorSubmission:
    clear_stale_runtime_artifacts(job.directory)
    resource_request = request_for_job(job)
    time_limit = time_limit_for_job(job)
    submit_file = write_condor_submit_file(
        job,
        env=env,
        resource_request=resource_request,
        time_limit=time_limit,
    )
    metadata = base_metadata(job, engine="htcondor")
    metadata.update(
        status="submitting",
        condor_submit_file=submit_file.name,
        condor_submitted_at=now_text(),
        condor_requested_cpus=resource_request.cpus,
        condor_requested_memory_mib=resource_request.memory_mib,
        condor_requested_disk_kib=resource_request.disk_kib,
        condor_resource_request_source=resource_request.source,
        condor_resource_calibration_sample_count=resource_request.sample_count,
        condor_allowed_execute_duration_sec=time_limit.seconds,
        condor_time_limit_source=time_limit.source,
        condor_time_calibration_sample_count=time_limit.sample_count,
    )
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


def write_condor_submit_file(
    job: JobSpec,
    *,
    env: Mapping[str, str] | None = None,
    resource_request: HTCondorResourceRequest | None = None,
    time_limit: HTCondorTimeLimit | None = None,
) -> Path:
    if htcondor_run_as_owner() and htcondor_load_profile():
        raise ValueError("HTCondor Windows config cannot combine run_as_owner=True with load_profile=True")

    resource_request = resource_request or request_for_job(job)
    time_limit = time_limit or time_limit_for_job(job)
    prepare_sandbox_env_dirs(job.directory)
    inputs = transfer_input_files(job.directory, executable_name=WORKFLOW_SCRIPT_NAME)
    requirements = htcondor_requirements().strip()
    submit_environment = condor_environment_string()
    lines: list[str] = [
        "# Auto-generated by project.evaluate_manager.condor_runner",
        "universe = vanilla",
        f"executable = {_quote_submit_atom(WORKFLOW_SCRIPT_NAME)}",
        "initialdir = .",
        "getenv = False",
    ]
    if submit_environment:
        lines.append(f'environment = "{submit_environment}"')
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
            f"request_cpus = {resource_request.cpus}",
            f"request_memory = {resource_request.memory_text}",
            f"request_disk = {resource_request.disk_text}",
            "notification = never",
        ]
    )
    if resource_request.memory_retry_mib:
        lines.append(f"retry_request_memory = {resource_request.memory_retry_text}")
    if resource_request.disk_retry_kib:
        lines.append(f"retry_request_disk = {resource_request.disk_retry_text}")
    if time_limit.seconds is not None:
        lines.append(f"allowed_execute_duration = {time_limit.seconds}")
    lines.extend(("queue 1", ""))
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
        if path.name == "__pycache__":
            continue
        files.append(_quote_submit_atom(path.name))
    return tuple(files)


def prepare_sandbox_env_dirs(job_dir: Path) -> None:
    for name in _SANDBOX_ENV_DIRS:
        (job_dir / name).mkdir(parents=True, exist_ok=True)


def clear_stale_runtime_artifacts(job_dir: Path) -> None:
    for name in (
        INDIVIDUAL_METADATA_FILE_NAME,
        f"{INDIVIDUAL_METADATA_FILE_NAME}.tmp",
        RAW_DATA_TRANSFER_ZIP_NAME,
        f"{RAW_DATA_TRANSFER_ZIP_NAME}.tmp",
        "cost.json",
    ):
        (job_dir / name).unlink(missing_ok=True)


def condor_environment_string() -> str:
    environment = htcondor_environment().strip()
    if not environment:
        return ""
    if any(char in environment for char in "\r\n"):
        raise ValueError("HTCONDOR_ENVIRONMENT must be a single-line HTCondor environment string")
    return environment.replace('"', '""')


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
    individual_metadata = read_individual_metadata(job.directory)
    hold_info = condor_hold_info(submission) if terminal_reason == "held" else {}
    timeout_hold = terminal_reason == "held" and _is_timeout_hold(hold_info)
    raw_paths = raw_data_paths(job.directory)
    zip_restore_error = None
    if not raw_paths:
        zip_restore_error = restore_rawdata_transfer_zip(job.directory)
        raw_paths = raw_data_paths(job.directory)
    log_info = condor_log_info(job.directory)
    resource_usage = condor_resource_usage(submission)
    if timeout_hold:
        timeout_remove_error = remove_condor_job(submission)
        if remove_error is None:
            remove_error = timeout_remove_error
    metadata = base_metadata(job, engine="htcondor")
    metadata.update(individual_metadata)

    effective_timed_out = bool(timed_out or timeout_hold)
    if timed_out:
        status = "timeout"
        error = f"HTCondor job exceeded timeout_sec while waiting for job-local outputs"
    elif timeout_hold:
        status = "timeout"
        error = "HTCondor job exceeded allowed_execute_duration and was not retried"
    elif terminal_reason in {"held", "aborted", "removed"}:
        status = "error"
        hold_reason = str(hold_info.get("condor_hold_reason") or "")
        error = (
            f"HTCondor reported terminal state: {terminal_reason}: {hold_reason}"
            if hold_reason
            else f"HTCondor reported terminal state: {terminal_reason}"
        )
    elif raw_paths and str(individual_metadata.get("status", "")).lower() != "error":
        status = "done"
        error = None
    elif str(individual_metadata.get("status", "")).lower() == "error":
        status = "error"
        error = str(individual_metadata.get("error_message") or "workflow reported error")
    else:
        status = "error"
        return_value = log_info.get("condor_return_value")
        if isinstance(return_value, int) and return_value != 0:
            error = (
                f"HTCondor job exited with return value {return_value}"
                f"{_return_value_summary(log_info)} and wrote no .npz files under {RAW_DATA_DIR_NAME}/"
            )
        elif _workflow_reported_rawdata(individual_metadata):
            error = (
                "Workflow reported done and listed rawData files, but no .npz files were returned under "
                f"{RAW_DATA_DIR_NAME}/. This usually means the job used the legacy Windows transfer contract "
                f"that did not return nested {RAW_DATA_DIR_NAME}/*.npz files, or {RAW_DATA_TRANSFER_ZIP_NAME} "
                "was not created/transferred."
            )
        else:
            error = f"HTCondor job finished without .npz files under {RAW_DATA_DIR_NAME}/"

    metadata.update(
        status=status,
        timed_out=effective_timed_out,
        runner_finished_at=now_text(),
        raw_data_files=[path.name for path in raw_paths],
        stdout_tail=_read_tail(job.directory / CONDOR_STDOUT_FILE_NAME),
        stderr_tail=_read_tail(job.directory / CONDOR_STDERR_FILE_NAME),
        batch_log_tail=_read_tail(job.directory / _BATCH_LOG_FILE_NAME),
        condor_cluster_id=submission.cluster_id,
        condor_submit_file=submission.submit_file.name,
        condor_log_file=CONDOR_LOG_FILE_NAME,
        condor_log_tail=_read_tail(job.directory / CONDOR_LOG_FILE_NAME),
        condor_terminal_reason=terminal_reason,
        condor_submit_stdout_tail=tail(submission.stdout),
        condor_submit_stderr_tail=tail(submission.stderr),
    )
    metadata.update(log_info)
    metadata.update(resource_usage)
    metadata.update(hold_info)
    if timeout_hold:
        metadata["condor_timeout_enforced_by"] = "allowed_execute_duration"
    if error is not None:
        metadata["error"] = error
    if zip_restore_error is not None:
        metadata["rawdata_transfer_zip_error"] = zip_restore_error
    if remove_error is not None:
        metadata["condor_remove_error"] = remove_error
    write_metadata(job.directory, metadata)
    return result_from_metadata(job, metadata, raw_paths)


def condor_log_info(job_dir: Path) -> dict[str, object]:
    log_path = job_dir / CONDOR_LOG_FILE_NAME
    if not log_path.is_file():
        return {}
    text = log_path.read_text(encoding="utf-8", errors="ignore")
    matches = _RETURN_VALUE_RE.findall(text)
    if not matches:
        return {}
    raw_value = str(matches[-1]).strip()
    try:
        value = int(raw_value, 0)
    except ValueError:
        return {"condor_return_value": raw_value}
    info: dict[str, object] = {"condor_return_value": value}
    info.update(windows_return_code_details(value))
    return info


def condor_resource_usage(submission: CondorSubmission) -> dict[str, object]:
    """Read final HTCondor resource measurements without changing job state."""

    if submission.cluster_id is None:
        return {}
    job_id = f"{submission.cluster_id}.0"
    errors: list[str] = []
    for source, command in (
        ("condor_history", [htcondor_history_exe(), job_id, "-limit", "1", "-json"]),
        ("condor_q", ["condor_q", job_id, "-json"]),
    ):
        try:
            completed = subprocess.run(
                command,
                cwd=str(submission.job.directory),
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            errors.append(f"{source}: {exc}")
            continue
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or f"exit {completed.returncode}").strip()
            errors.append(f"{source}: {detail}")
            continue
        ad = _first_condor_json_ad(completed.stdout or "")
        if ad is None:
            continue
        info = _resource_usage_from_ad(ad)
        if info:
            info["condor_resource_usage_source"] = source
            return info
    return {"condor_resource_usage_query_error": "; ".join(errors)} if errors else {}


def _first_condor_json_ad(text: str) -> Mapping[str, object] | None:
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(decoded, list):
        return decoded[0] if decoded and isinstance(decoded[0], Mapping) else None
    return decoded if isinstance(decoded, Mapping) else None


def _resource_usage_from_ad(ad: Mapping[str, object]) -> dict[str, object]:
    field_map = {
        "MemoryUsage": "condor_memory_usage_mib",
        "DiskUsage": "condor_disk_usage_kib",
        "ResidentSetSize": "condor_resident_set_size_kib",
        "CpusUsage": "condor_cpus_usage",
        "RequestMemory": "condor_reported_request_memory_mib",
        "RequestDisk": "condor_reported_request_disk_kib",
        "RequestCpus": "condor_reported_request_cpus",
        "RemoteWallClockTime": "condor_remote_wall_clock_sec",
        "CumulativeSuspensionTime": "condor_cumulative_suspension_sec",
    }
    info: dict[str, object] = {}
    for ad_name, metadata_name in field_map.items():
        value = _finite_resource_value(ad.get(ad_name))
        if value is not None:
            info[metadata_name] = value
    return info


def _finite_resource_value(value: object) -> int | float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not parsed >= 0.0 or parsed == float("inf"):
        return None
    return int(parsed) if parsed.is_integer() else parsed


def collect_failure_result(
    job: JobSpec,
    *,
    submission: CondorSubmission,
    exc: BaseException,
    terminal_reason: str | None,
) -> JobResult:
    raw_paths = raw_data_paths(job.directory)
    metadata = base_metadata(job, engine="htcondor")
    metadata.update(read_individual_metadata(job.directory))
    metadata.update(
        status="error",
        failure_stage="collect",
        error_type=type(exc).__name__,
        error_message=str(exc),
        error=f"HTCondor result collection failed: {type(exc).__name__}: {exc}",
        runner_finished_at=now_text(),
        raw_data_files=[path.name for path in raw_paths],
        stdout_tail=_read_tail(job.directory / CONDOR_STDOUT_FILE_NAME),
        stderr_tail=_read_tail(job.directory / CONDOR_STDERR_FILE_NAME),
        batch_log_tail=_read_tail(job.directory / _BATCH_LOG_FILE_NAME),
        condor_cluster_id=submission.cluster_id,
        condor_submit_file=submission.submit_file.name,
        condor_log_file=CONDOR_LOG_FILE_NAME,
        condor_log_tail=_read_tail(job.directory / CONDOR_LOG_FILE_NAME),
        condor_terminal_reason=terminal_reason,
        condor_submit_stdout_tail=tail(submission.stdout),
        condor_submit_stderr_tail=tail(submission.stderr),
    )
    metadata.update(condor_log_info(job.directory))
    write_metadata(job.directory, metadata)
    return result_from_metadata(job, metadata, raw_paths)


def restore_rawdata_transfer_zip(job_dir: Path) -> str | None:
    archive_path = job_dir / RAW_DATA_TRANSFER_ZIP_NAME
    if not archive_path.is_file():
        return None
    import zipfile

    raw_dir = job_dir / RAW_DATA_DIR_NAME
    raw_dir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            for member in archive.infolist():
                member_name = member.filename.replace("\\", "/")
                if member.is_dir() or "/" in member_name or not member_name.endswith(".npz"):
                    continue
                target = raw_dir / Path(member_name).name
                with archive.open(member, "r") as source, target.open("wb") as dest:
                    dest.write(source.read())
    except (OSError, zipfile.BadZipFile) as exc:
        return f"could not restore {RAW_DATA_TRANSFER_ZIP_NAME}: {exc}"
    return None


def _job_local_outputs_ready(job_dir: Path, individual_metadata: Mapping[str, object]) -> bool:
    if not individual_metadata:
        return False
    status = str(individual_metadata.get("status", "")).strip().lower()
    if status == "done":
        raw_files = individual_metadata.get("raw_data_files")
        raw_paths = raw_data_paths(job_dir)
        if isinstance(raw_files, list) and raw_files:
            reported = {Path(str(name)).name for name in raw_files}
            returned = {path.name for path in raw_paths}
            if reported.issubset(returned):
                return True
        elif raw_paths:
            return True
        return _rawdata_transfer_zip_is_readable(job_dir)
    return status == "error"


def _rawdata_transfer_zip_is_readable(job_dir: Path) -> bool:
    archive_path = job_dir / RAW_DATA_TRANSFER_ZIP_NAME
    if not archive_path.is_file():
        return False
    import zipfile

    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            return archive.testzip() is None
    except (OSError, zipfile.BadZipFile):
        return False


def _workflow_reported_rawdata(individual_metadata: Mapping[str, object]) -> bool:
    status = str(individual_metadata.get("status", "")).strip().lower()
    raw_files = individual_metadata.get("raw_data_files")
    return status == "done" and isinstance(raw_files, list) and bool(raw_files)


def windows_return_code_details(value: int) -> dict[str, object]:
    unsigned = int(value) & 0xFFFFFFFF
    details: dict[str, object] = {"condor_return_value_hex": f"0x{unsigned:08X}"}
    known = _WINDOWS_STATUS_MESSAGES.get(unsigned)
    if known is not None:
        name, explanation = known
        details["condor_return_value_name"] = name
        details["condor_return_value_explanation"] = explanation
    return details


def _return_value_summary(info: Mapping[str, object]) -> str:
    parts: list[str] = []
    hex_value = str(info.get("condor_return_value_hex") or "")
    name = str(info.get("condor_return_value_name") or "")
    explanation = str(info.get("condor_return_value_explanation") or "")
    if hex_value:
        parts.append(hex_value)
    if name:
        parts.append(name)
    if explanation:
        parts.append(explanation)
    return "" if not parts else f" ({'; '.join(parts)})"


def condor_hold_info(submission: CondorSubmission) -> dict[str, object]:
    if submission.cluster_id is None:
        return {}
    try:
        completed = subprocess.run(
            [
                "condor_q",
                f"{submission.cluster_id}.0",
                "-af",
                "HoldReason",
                "HoldReasonCode",
                "HoldReasonSubCode",
            ],
            cwd=str(submission.job.directory),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        return {"condor_hold_query_error": str(exc)}
    text = (completed.stdout or "").strip()
    if completed.returncode != 0:
        return {"condor_hold_query_error": (completed.stderr or completed.stdout or "").strip()}
    if not text:
        return {}
    parts = text.split()
    reason_width = max(0, len(parts) - 2)
    reason = " ".join(parts[:reason_width]) if reason_width else text
    info: dict[str, object] = {"condor_hold_reason": reason}
    if len(parts) >= 2:
        info["condor_hold_reason_code"] = parts[-2]
        info["condor_hold_reason_subcode"] = parts[-1]
    return info


def _is_timeout_hold(hold_info: Mapping[str, object]) -> bool:
    try:
        code = int(hold_info.get("condor_hold_reason_code"))
    except (TypeError, ValueError):
        return False
    return code in {46, 47}


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


def _read_tail(path: Path, limit: int = 4000) -> str:
    if not path.is_file():
        return ""
    data = path.read_bytes()
    for encoding in ("utf-8", "mbcs", "gbk"):
        try:
            return tail(data.decode(encoding), limit=limit)
        except (LookupError, UnicodeDecodeError):
            continue
    return tail(data.decode("utf-8", errors="replace"), limit=limit)


def _quote_submit_atom(value: str) -> str:
    return f'"{value}"' if any(char in value for char in (" ", ",")) else value


def _condor_bool(value: bool) -> str:
    return "True" if value else "False"


def _progress(message: str) -> None:
    if str(os.environ.get("YADOF_PROGRESS", "")).strip().lower() in {"1", "true", "yes", "on"}:
        print(f"[yadof] {message}", flush=True)
