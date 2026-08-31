from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
from typing import Callable, Mapping, Sequence

from ..config import LoadedConfig, load_config
from ..job_template import RawDataContractError, validate_rawdata_directory
from ..recorded_data.session import RecordingError
from ..workspace import WorkspaceContext
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
from .resource_retries import (
    YadofResourceRetryState,
    decide_resource_retry,
    new_resource_retry_state,
    reset_job_for_resource_retry,
    resource_hold_kind,
    resource_retry_metadata,
)
from .time_limits import HTCondorTimeLimit, time_limit_for_job
from .types import JobResult, JobSpec


_CLUSTER_RE = re.compile(r"submitted to cluster\s+(\d+)", re.IGNORECASE)
_RETURN_VALUE_RE = re.compile(r"Normal termination \(return value ([^)]+)\)", re.IGNORECASE)
_CONDOR_EVENT_RE = re.compile(
    r"^(?P<code>\d{3}) \([^)]+\) "
    r"(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<message>[^\r\n]*)",
    re.MULTILINE,
)
_CONDOR_SLOT_NAME_RE = re.compile(
    r"^\s*SlotName:\s*(?P<slot>[^\s]+)\s*$",
    re.MULTILINE,
)
_CONDOR_ALIAS_RE = re.compile(r"[?&]alias=(?P<machine>[^&>\s]+)")
_CONDOR_EXECUTE_HOST_RE = re.compile(
    r"Job executing on host:\s*<(?P<host>[^>]+)>",
    re.IGNORECASE,
)
_TERMINAL_LOG_MARKERS = {
    "terminated": "Job terminated",
    "held": "Job was held",
    "aborted": "Job was aborted",
    "removed": "Job was removed",
}
_EXECUTION_STOP_EVENT_CODES = {"004", "005", "009", "012"}
_EXECUTION_STOP_MARKERS = (
    "Job was evicted",
    "Job terminated",
    "Job was held",
    "Job was aborted",
    "Job was removed",
)
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
_MATCH_DIAGNOSTIC_MIN_DELAY_SEC = 5.0
_MATCH_DIAGNOSTIC_MAX_DELAY_SEC = 60.0
_CONDOR_REMOVE_COMMAND_TIMEOUT_SEC = 5.0


@dataclass(frozen=True)
class CondorExecutionSite:
    machine: str | None
    slot_name: str | None


@dataclass(frozen=True)
class CondorExecutionClock:
    started_at: str
    elapsed_sec: float
    suspended: bool
    execute_machine: str | None = None
    slot_name: str | None = None


@dataclass(frozen=True)
class CondorSubmission:
    job: JobSpec
    submit_file: Path
    cluster_id: int | None
    submitted_at: str
    stdout: str
    stderr: str
    resource_request: HTCondorResourceRequest | None = None
    time_limit: HTCondorTimeLimit | None = None


class CondorSubmitError(RuntimeError):
    def __init__(self, message: str, *, returncode: int | None, stdout: str = "", stderr: str = "") -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def run_condor_jobs(
    workspace: WorkspaceContext | str | Path,
    jobs: Sequence[JobSpec],
    *,
    config: LoadedConfig | None = None,
    timeout_sec: float | None,
    env: Mapping[str, str] | None = None,
    on_result: Callable[[JobResult], object] | None = None,
    history_records: Sequence[Mapping[str, object]] | None = None,
    cancel_event: threading.Event | None = None,
) -> tuple[JobResult, ...]:
    """Submit jobs to HTCondor, wait for job-local outputs, and collect results.

    This function deliberately treats HTCondor as an external backend. If the
    local installation is stale or broken, submit failures are captured as
    per-job metadata; the function does not attempt to repair the pool.
    """

    effective = load_config(workspace) if config is None else config
    results_by_name: dict[str, JobResult] = {}
    pending: dict[str, CondorSubmission] = {}
    retry_states: dict[str, YadofResourceRetryState] = {}
    total = len(jobs)
    submit_failures = 0

    def store_result(job_name: str, result: JobResult) -> None:
        results_by_name[job_name] = result
        if on_result is None:
            return
        try:
            on_result(result)
        except RecordingError:
            raise
        except Exception as exc:  # noqa: BLE001 - progress cannot alter outcomes.
            _progress(
                "htcondor: result callback failed for "
                f"{job_name}: {exc.__class__.__name__}: {exc}"
            )

    _progress(f"htcondor: submitting {total} jobs")
    _progress(f"htcondor: submit progress 0/{total}; queued=0; submit_failures=0; last_cluster=none")
    for index, job in enumerate(jobs, start=1):
        if cancel_event is not None and cancel_event.is_set():
            store_result(
                job.name,
                cancelled_condor_result(
                    job,
                    submission=None,
                    stage="before_submit",
                    remove_error=None,
                ),
            )
            continue
        try:
            submission = submit_condor_job(
                effective.workspace,
                job,
                config=effective,
                env=env,
                history_records=history_records,
            )
        except Exception as exc:  # noqa: BLE001 - preserve per-individual failure isolation.
            store_result(job.name, submit_failure_result(job, exc))
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

    deadline = None if timeout_sec is None else time.monotonic() + float(timeout_sec)
    poll_sec = max(0.1, htcondor_poll_sec(effective))
    last_report = 0.0
    match_diagnostic_at = time.monotonic() + min(
        _MATCH_DIAGNOSTIC_MAX_DELAY_SEC,
        max(_MATCH_DIAGNOSTIC_MIN_DELAY_SEC, poll_sec * 2.0),
    )
    match_diagnostic_reported = False
    if pending:
        _progress(f"htcondor: waiting for {len(pending)} jobs")
    while pending and (deadline is None or time.monotonic() < deadline):
        if cancel_event is not None and cancel_event.is_set():
            break
        completed_now = 0
        for job_name, submission in list(pending.items()):
            terminal_reason = terminal_log_reason(submission.job.directory)
            individual_metadata = read_individual_metadata(submission.job.directory)
            outputs_ready = _job_local_outputs_ready(
                submission.job.directory, individual_metadata
            )
            if terminal_reason is None and not outputs_ready:
                timeout_metadata = _yadof_execution_timeout_metadata(submission)
                if timeout_metadata is None:
                    continue
                remove_error = remove_condor_job(
                    effective.workspace, submission, config=effective
                )
                store_result(
                    job_name,
                    collect_condor_result(
                        effective.workspace,
                        submission.job,
                        config=effective,
                        submission=submission,
                        timed_out=True,
                        terminal_reason="yadof_job_timeout",
                        remove_error=remove_error,
                        preloaded_resource_usage={},
                        extra_metadata=timeout_metadata,
                    ),
                )
                pending.pop(job_name, None)
                completed_now += 1
                _progress(
                    f"htcondor: yadof timeout {job_name}; "
                    f"execution={float(timeout_metadata['condor_execution_elapsed_sec']):.1f}s; "
                    f"limit={timeout_metadata['condor_timeout_limit_sec']}s"
                )
                continue
            preloaded_hold_info: Mapping[str, object] | None = None
            preloaded_resource_usage: Mapping[str, object] | None = None
            extra_metadata: Mapping[str, object] | None = None
            remove_error: str | None = None
            if terminal_reason == "held":
                preloaded_hold_info = condor_hold_info(submission)
                exhausted_resource = resource_hold_kind(preloaded_hold_info)
                if exhausted_resource is not None:
                    preloaded_resource_usage = condor_resource_usage(
                        effective.workspace, submission, config=effective
                    )
                    state = retry_states.get(job_name)
                    if state is None:
                        state = new_resource_retry_state(
                            submission.resource_request
                            or request_for_job(
                                effective.workspace,
                                submission.job,
                                config=effective,
                                history_records=history_records,
                            ),
                            config=effective,
                        )
                    remove_error = (
                        "cannot retry a resource-held job without a Condor cluster id"
                        if submission.cluster_id is None
                        else remove_condor_job(
                            effective.workspace, submission, config=effective
                        )
                    )
                    if remove_error is None:
                        decision = decide_resource_retry(
                            state,
                            hold_info=preloaded_hold_info,
                            resource_usage=preloaded_resource_usage,
                            cluster_id=submission.cluster_id,
                        )
                        if decision is not None:
                            retry_states[job_name] = decision.state
                            extra_metadata = resource_retry_metadata(decision.state)
                            if decision.should_retry:
                                try:
                                    reset_job_for_resource_retry(submission.job.directory)
                                except Exception as exc:  # noqa: BLE001 - isolate one retry cleanup failure.
                                    store_result(
                                        job_name,
                                        collect_failure_result(
                                            submission.job,
                                            submission=submission,
                                            exc=exc,
                                            terminal_reason=terminal_reason,
                                            extra_metadata=extra_metadata,
                                        ),
                                    )
                                    pending.pop(job_name, None)
                                    completed_now += 1
                                    continue
                                try:
                                    pending[job_name] = submit_condor_job(
                                        effective.workspace,
                                        submission.job,
                                        config=effective,
                                        env=env,
                                        resource_request=decision.state.request,
                                        resource_retry_metadata=extra_metadata,
                                        history_records=history_records,
                                    )
                                except Exception as exc:  # noqa: BLE001 - preserve per-individual isolation.
                                    store_result(
                                        job_name,
                                        submit_failure_result(submission.job, exc),
                                    )
                                    pending.pop(job_name, None)
                                    submit_failures += 1
                                    completed_now += 1
                                    _progress(f"htcondor: resource retry submit failed: {job_name}")
                                    continue
                                _progress(
                                    f"htcondor: yadof retry {job_name}; resource={decision.resource}; "
                                    f"memory={decision.state.request.memory_text}; "
                                    f"disk={decision.state.request.disk_text}"
                                )
                                continue
                else:
                    remove_error = remove_condor_job(
                        effective.workspace, submission, config=effective
                    )
            collection_options: dict[str, object] = {}
            if remove_error is not None:
                collection_options["remove_error"] = remove_error
            if preloaded_hold_info is not None:
                collection_options["preloaded_hold_info"] = preloaded_hold_info
            if preloaded_resource_usage is not None:
                collection_options["preloaded_resource_usage"] = preloaded_resource_usage
            if extra_metadata is not None:
                collection_options["extra_metadata"] = extra_metadata
            try:
                store_result(
                    job_name,
                    collect_condor_result(
                        effective.workspace,
                        submission.job,
                        config=effective,
                        submission=submission,
                        timed_out=False,
                        terminal_reason=terminal_reason,
                        **collection_options,
                    ),
                )
            except Exception as exc:  # noqa: BLE001 - isolate one bad returned payload.
                store_result(
                    job_name,
                    collect_failure_result(
                        submission.job,
                        submission=submission,
                        exc=exc,
                        terminal_reason=terminal_reason,
                        extra_metadata=extra_metadata,
                    ),
                )
            pending.pop(job_name, None)
            completed_now += 1
        now = time.monotonic()
        if completed_now or now >= last_report + poll_sec:
            _progress(f"htcondor: pending={len(pending)}/{total}")
            last_report = now
        if (
            pending
            and not match_diagnostic_reported
            and now >= match_diagnostic_at
        ):
            representative = next(iter(pending.values()))
            diagnostic = condor_matchmaking_diagnostic(representative)
            if diagnostic:
                job_id = (
                    f"{representative.cluster_id}.0"
                    if representative.cluster_id is not None
                    else representative.job.name
                )
                _progress(
                    f"htcondor: scheduling diagnostic for {job_id}: {diagnostic}"
                )
            match_diagnostic_reported = True
        if pending:
            if cancel_event is None:
                time.sleep(poll_sec)
            else:
                cancel_event.wait(poll_sec)

    cancellation_requested = bool(cancel_event is not None and cancel_event.is_set())
    timed_out_count = 0 if cancellation_requested else len(pending)
    cancelled_count = 0
    for job_name, submission in list(pending.items()):
        if cancellation_requested:
            terminal_reason = terminal_log_reason(submission.job.directory)
            individual_metadata = read_individual_metadata(submission.job.directory)
            outputs_ready = _job_local_outputs_ready(
                submission.job.directory,
                individual_metadata,
            )
            if terminal_reason is not None or outputs_ready:
                try:
                    result = collect_condor_result(
                        effective.workspace,
                        submission.job,
                        config=effective,
                        submission=submission,
                        timed_out=False,
                        terminal_reason=terminal_reason,
                    )
                except Exception as exc:  # Preserve a completed-but-bad payload.
                    result = collect_failure_result(
                        submission.job,
                        submission=submission,
                        exc=exc,
                        terminal_reason=terminal_reason,
                    )
                store_result(job_name, result)
                pending.pop(job_name, None)
                continue
            remove_error = remove_condor_job(
                effective.workspace,
                submission,
                config=effective,
            )
            store_result(
                job_name,
                cancelled_condor_result(
                    submission.job,
                    submission=submission,
                    stage="scheduler_cancel",
                    remove_error=remove_error,
                ),
            )
            cancelled_count += 1
            pending.pop(job_name, None)
            continue
        active_clock = condor_execution_clock(submission.job.directory)
        timeout_site_metadata = (
            {}
            if active_clock is None
            else _condor_execution_site_metadata(
                CondorExecutionSite(
                    machine=active_clock.execute_machine,
                    slot_name=active_clock.slot_name,
                )
            )
        )
        remove_error = remove_condor_job(
            effective.workspace, submission, config=effective
        )
        store_result(
            job_name,
            collect_condor_result(
                effective.workspace,
                submission.job,
                config=effective,
                submission=submission,
                timed_out=True,
                terminal_reason="timeout",
                remove_error=remove_error,
                preloaded_resource_usage={},
                extra_metadata=timeout_site_metadata,
            ),
        )
        pending.pop(job_name, None)
    if timed_out_count:
        _progress(f"htcondor: timed out {timed_out_count} jobs")
    if cancelled_count:
        _progress(f"htcondor: cancelled {cancelled_count} jobs")
    _progress(f"htcondor: collected {len(results_by_name)}/{total} results")

    return tuple(results_by_name[job.name] for job in jobs)


def submit_condor_job(
    workspace: WorkspaceContext | str | Path,
    job: JobSpec,
    *,
    config: LoadedConfig | None = None,
    env: Mapping[str, str] | None = None,
    resource_request: HTCondorResourceRequest | None = None,
    resource_retry_metadata: Mapping[str, object] | None = None,
    history_records: Sequence[Mapping[str, object]] | None = None,
) -> CondorSubmission:
    effective = load_config(workspace) if config is None else config
    clear_stale_runtime_artifacts(job.directory)
    resource_request = resource_request or request_for_job(
        effective.workspace,
        job,
        config=effective,
        history_records=history_records,
    )
    time_limit = time_limit_for_job(
        effective.workspace,
        job,
        config=effective,
        history_records=history_records,
    )
    submit_file = write_condor_submit_file(
        effective.workspace,
        job,
        config=effective,
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
    if resource_retry_metadata is not None:
        metadata.update(resource_retry_metadata)
    write_metadata(job.directory, metadata)

    try:
        completed = subprocess.run(
            [htcondor_submit_exe(effective), submit_file.name],
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
        resource_request=resource_request,
        time_limit=time_limit,
    )


def write_condor_submit_file(
    workspace: WorkspaceContext | str | Path,
    job: JobSpec,
    *,
    config: LoadedConfig | None = None,
    env: Mapping[str, str] | None = None,
    resource_request: HTCondorResourceRequest | None = None,
    time_limit: HTCondorTimeLimit | None = None,
) -> Path:
    effective = load_config(workspace) if config is None else config
    if htcondor_run_as_owner(effective) and htcondor_load_profile(effective):
        raise ValueError("HTCondor Windows config cannot combine run_as_owner=True with load_profile=True")

    resource_request = resource_request or request_for_job(
        effective.workspace, job, config=effective
    )
    time_limit = time_limit or time_limit_for_job(
        effective.workspace, job, config=effective
    )
    prepare_sandbox_env_dirs(job.directory)
    inputs = transfer_input_files(
        job.directory, executable_name=WORKFLOW_SCRIPT_NAME
    )
    requirements = htcondor_requirements(effective).strip()
    submit_environment = condor_environment_string(effective)
    lines: list[str] = [
        "# Auto-generated by yadof.evaluate_manager.condor_runner",
        "universe = vanilla",
        f"executable = {_quote_submit_atom(WORKFLOW_SCRIPT_NAME)}",
        "initialdir = .",
        "getenv = False",
    ]
    if submit_environment:
        lines.append(f'environment = "{submit_environment}"')
    lines.append(f"load_profile = {_condor_bool(htcondor_load_profile(effective))}")
    lines.append(f"run_as_owner = {_condor_bool(htcondor_run_as_owner(effective))}")
    if requirements:
        lines.append(f"requirements = {requirements}")
    lines.extend(
        [
            "should_transfer_files = YES",
            "when_to_transfer_output = ON_EXIT",
            "transfer_executable = True",
            f"transfer_output_files = {RAW_DATA_TRANSFER_ZIP_NAME},{INDIVIDUAL_METADATA_FILE_NAME}",
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


def condor_environment_string(config: LoadedConfig) -> str:
    environment = htcondor_environment(config).strip()
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


def _normalized_condor_machine(value: object) -> str | None:
    text = str(value or "").strip().strip('"<>')
    if not text:
        return None
    if "@" in text:
        text = text.rsplit("@", 1)[1].strip()
    return text or None


def _condor_execute_site_for_event(
    text: str,
    matches: Sequence[re.Match[str]],
    index: int,
) -> CondorExecutionSite | None:
    match = matches[index]
    block_end = (
        matches[index + 1].start()
        if index + 1 < len(matches)
        else len(text)
    )
    block = text[match.start() : block_end]
    slot_match = _CONDOR_SLOT_NAME_RE.search(block)
    slot_name = (
        None
        if slot_match is None
        else str(slot_match.group("slot")).strip() or None
    )
    machine = (
        _normalized_condor_machine(slot_name)
        if slot_name is not None and "@" in slot_name
        else None
    )
    if machine is None:
        alias_match = _CONDOR_ALIAS_RE.search(match.group("message"))
        if alias_match is not None:
            machine = _normalized_condor_machine(alias_match.group("machine"))
    if machine is None:
        host_match = _CONDOR_EXECUTE_HOST_RE.search(match.group("message"))
        if host_match is not None:
            host = str(host_match.group("host")).strip()
            if all(marker not in host for marker in ("?", "=", ":")):
                machine = _normalized_condor_machine(host)
    if machine is None and slot_name is None:
        return None
    return CondorExecutionSite(machine=machine, slot_name=slot_name)


def condor_last_execution_site(job_dir: Path) -> CondorExecutionSite | None:
    """Return the most recent execute site recorded in the job's event log."""

    log_path = job_dir / CONDOR_LOG_FILE_NAME
    if not log_path.is_file():
        return None
    text = log_path.read_text(encoding="utf-8", errors="ignore")
    matches = tuple(_CONDOR_EVENT_RE.finditer(text))
    for index in reversed(range(len(matches))):
        match = matches[index]
        if (
            match.group("code") == "001"
            and "Job executing" in match.group("message")
        ):
            return _condor_execute_site_for_event(text, matches, index)
    return None


def condor_timeout_execution_site_from_text(
    text: str,
) -> CondorExecutionSite | None:
    """Return the execution site associated with a recorded timeout."""

    text = str(text or "")
    matches = tuple(_CONDOR_EVENT_RE.finditer(text))
    active_site: CondorExecutionSite | None = None
    timeout_site: CondorExecutionSite | None = None
    for index, match in enumerate(matches):
        code = match.group("code")
        message = match.group("message")
        if code == "001" and "Job executing" in message:
            active_site = _condor_execute_site_for_event(
                text,
                matches,
                index,
            )
            timeout_site = None
            continue
        if code == "004":
            block_end = (
                matches[index + 1].start()
                if index + 1 < len(matches)
                else len(text)
            )
            event_block = text[match.start() : block_end]
            timeout_site = (
                active_site
                if active_site is not None
                and "via condor_rm" in event_block.lower()
                else None
            )
            active_site = None
            continue
        if code == "005":
            if active_site is not None:
                timeout_site = active_site
            active_site = None
            continue
        if code in {"009", "012"}:
            if active_site is not None:
                timeout_site = active_site
            active_site = None
    return active_site if active_site is not None else timeout_site


def _condor_execution_site_metadata(
    site: CondorExecutionSite | None,
) -> dict[str, object]:
    if site is None:
        return {}
    metadata: dict[str, object] = {}
    if site.machine is not None:
        metadata["condor_execute_machine"] = site.machine
    if site.slot_name is not None:
        metadata["condor_slot_name"] = site.slot_name
    if metadata:
        metadata["condor_execute_machine_source"] = "condor_user_log"
    return metadata


def condor_execution_clock(
    job_dir: Path,
    *,
    now_epoch: float | None = None,
) -> CondorExecutionClock | None:
    """Return the current Condor execution segment's submit-side wall clock."""

    log_path = job_dir / CONDOR_LOG_FILE_NAME
    if not log_path.is_file():
        return None
    text = log_path.read_text(encoding="utf-8", errors="ignore")
    matches = tuple(_CONDOR_EVENT_RE.finditer(text))
    active_started_epoch: float | None = None
    segment_started_epoch: float | None = None
    elapsed_sec = 0.0
    suspended = False
    active_site: CondorExecutionSite | None = None
    for index, match in enumerate(matches):
        try:
            event_epoch = datetime.strptime(
                match.group("timestamp"), "%Y-%m-%d %H:%M:%S"
            ).timestamp()
        except (OSError, ValueError):
            continue
        code = match.group("code")
        message = match.group("message")
        if code == "001" and "Job executing" in message:
            active_started_epoch = event_epoch
            segment_started_epoch = event_epoch
            elapsed_sec = 0.0
            suspended = False
            active_site = _condor_execute_site_for_event(
                text,
                matches,
                index,
            )
            continue
        if active_started_epoch is None:
            continue
        if code == "010":
            if segment_started_epoch is not None:
                elapsed_sec += max(0.0, event_epoch - segment_started_epoch)
            segment_started_epoch = None
            suspended = True
            continue
        if code == "011":
            if suspended:
                segment_started_epoch = event_epoch
            suspended = False
            continue
        if code in _EXECUTION_STOP_EVENT_CODES or any(
            marker in message for marker in _EXECUTION_STOP_MARKERS
        ):
            active_started_epoch = None
            segment_started_epoch = None
            elapsed_sec = 0.0
            suspended = False
            active_site = None

    if active_started_epoch is None:
        return None
    current_epoch = time.time() if now_epoch is None else float(now_epoch)
    if segment_started_epoch is not None:
        elapsed_sec += max(0.0, current_epoch - segment_started_epoch)
    started_at = (
        datetime.fromtimestamp(active_started_epoch)
        .astimezone()
        .isoformat(timespec="seconds")
    )
    return CondorExecutionClock(
        started_at=started_at,
        elapsed_sec=elapsed_sec,
        suspended=suspended,
        execute_machine=(
            None if active_site is None else active_site.machine
        ),
        slot_name=None if active_site is None else active_site.slot_name,
    )


def _yadof_execution_timeout_metadata(
    submission: CondorSubmission,
) -> dict[str, object] | None:
    time_limit = submission.time_limit
    if time_limit is None or time_limit.seconds is None:
        return None
    clock = condor_execution_clock(submission.job.directory)
    if clock is None or clock.elapsed_sec < time_limit.seconds:
        return None
    metadata = {
        "condor_timeout_enforced_by": "yadof_submit_watchdog",
        "condor_timeout_limit_sec": time_limit.seconds,
        "condor_execution_started_at": clock.started_at,
        "condor_execution_elapsed_sec": clock.elapsed_sec,
        "condor_execution_suspended": clock.suspended,
    }
    metadata.update(
        _condor_execution_site_metadata(
            CondorExecutionSite(
                machine=clock.execute_machine,
                slot_name=clock.slot_name,
            )
        )
    )
    return metadata


def collect_condor_result(
    workspace: WorkspaceContext | str | Path,
    job: JobSpec,
    *,
    config: LoadedConfig | None = None,
    submission: CondorSubmission,
    timed_out: bool,
    terminal_reason: str | None,
    remove_error: str | None = None,
    preloaded_hold_info: Mapping[str, object] | None = None,
    preloaded_resource_usage: Mapping[str, object] | None = None,
    extra_metadata: Mapping[str, object] | None = None,
) -> JobResult:
    effective = load_config(workspace) if config is None else config
    individual_metadata = read_individual_metadata(job.directory)
    hold_info = (
        dict(preloaded_hold_info)
        if preloaded_hold_info is not None
        else condor_hold_info(submission) if terminal_reason == "held" else {}
    )
    timeout_hold = terminal_reason == "held" and _is_timeout_hold(hold_info)
    zip_restore_error = restore_rawdata_transfer_zip(job.directory)
    raw_paths = raw_data_paths(job.directory)
    if zip_restore_error is None and raw_paths:
        try:
            raw_paths = validate_rawdata_directory(
                job.directory / RAW_DATA_DIR_NAME
            )
        except RawDataContractError as exc:
            zip_restore_error = f"invalid restored rawData: {exc}"
            raw_paths = ()
    log_info = condor_log_info(job.directory)
    resource_usage = (
        dict(preloaded_resource_usage)
        if preloaded_resource_usage is not None
        else condor_resource_usage(
            effective.workspace, submission, config=effective
        )
    )
    if timeout_hold:
        timeout_remove_error = remove_condor_job(
            effective.workspace, submission, config=effective
        )
        if remove_error is None:
            remove_error = timeout_remove_error
    metadata = base_metadata(job, engine="htcondor")
    metadata.update(individual_metadata)
    if extra_metadata is not None:
        metadata.update(extra_metadata)

    effective_timed_out = bool(timed_out or timeout_hold)
    if timeout_hold:
        for key, value in _condor_execution_site_metadata(
            condor_last_execution_site(job.directory)
        ).items():
            metadata.setdefault(key, value)
    if timed_out:
        status = "timeout"
        if terminal_reason == "yadof_job_timeout":
            limit_sec = metadata.get("condor_timeout_limit_sec")
            error = "HTCondor job exceeded yadof submit-side execution limit"
            if limit_sec is not None:
                error += f" of {limit_sec} seconds"
        else:
            error = "HTCondor job exceeded timeout_sec while waiting for job-local outputs"
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
                "Workflow reported done and listed rawData files, but the required flat "
                f"{RAW_DATA_TRANSFER_ZIP_NAME} output was missing, invalid, or contained no .npz files."
            )
        else:
            error = (
                f"HTCondor job finished without valid .npz files in "
                f"{RAW_DATA_TRANSFER_ZIP_NAME}"
            )

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


def condor_resource_usage(
    workspace: WorkspaceContext | str | Path,
    submission: CondorSubmission,
    *,
    config: LoadedConfig | None = None,
) -> dict[str, object]:
    """Read final HTCondor resource measurements without changing job state."""

    effective = load_config(workspace) if config is None else config
    if submission.cluster_id is None:
        return {}
    job_id = f"{submission.cluster_id}.0"
    errors: list[str] = []
    for source, command in (
        (
            "condor_history",
            [htcondor_history_exe(effective), job_id, "-limit", "1", "-json"],
        ),
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


def condor_matchmaking_diagnostic(submission: CondorSubmission) -> str:
    """Summarize why one representative queued job has not matched a slot."""

    if submission.cluster_id is None:
        return ""
    job_id = f"{submission.cluster_id}.0"
    try:
        completed = subprocess.run(
            ["condor_q", job_id, "-better-analyze:nouserprios"],
            cwd=str(submission.job.directory),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        return f"condor_q -better-analyze unavailable: {exc}"
    output = (completed.stdout or completed.stderr or "").strip()
    if completed.returncode != 0:
        detail = tail(output.replace("\r", " ").replace("\n", " "), limit=500)
        return (
            f"condor_q -better-analyze exited {completed.returncode}"
            f"{f': {detail}' if detail else ''}"
        )
    return _summarize_matchmaking_analysis(output)


def _summarize_matchmaking_analysis(output: str) -> str:
    details: list[str] = []
    failed_conditions = re.findall(
        r"^\[\d+\]\s+0\s+(.+?)\s*$",
        output,
        flags=re.MULTILINE,
    )
    for condition in failed_conditions:
        details.append(f"failed requirement: {condition.strip()}")
    if "No machines matched the job's constraints" in output:
        details.append("no machines matched the job's constraints")
    reason_match = re.search(
        r"^Reason for last match failure:\s*(.+?)\s*$",
        output,
        flags=re.MULTILINE,
    )
    if reason_match is not None:
        details.append(f"last match failure: {reason_match.group(1).strip()}")
    if not details:
        return ""
    return "; ".join(dict.fromkeys(details))


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
    for backend_name, shared_name in (
        ("condor_cpus_usage", "resource_cpu_usage_cores"),
        ("condor_memory_usage_mib", "resource_memory_usage_mib"),
        ("condor_disk_usage_kib", "resource_disk_usage_kib"),
    ):
        if backend_name in info:
            info[shared_name] = info[backend_name]
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
    extra_metadata: Mapping[str, object] | None = None,
) -> JobResult:
    raw_paths = raw_data_paths(job.directory)
    metadata = base_metadata(job, engine="htcondor")
    metadata.update(read_individual_metadata(job.directory))
    if extra_metadata is not None:
        metadata.update(extra_metadata)
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
        return f"required HTCondor output is missing: {RAW_DATA_TRANSFER_ZIP_NAME}"
    import zipfile

    raw_dir = job_dir / RAW_DATA_DIR_NAME
    raw_dir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            members = _flat_rawdata_zip_members(archive)
            for existing in raw_dir.iterdir():
                if existing.is_dir():
                    return (
                        f"cannot restore {RAW_DATA_TRANSFER_ZIP_NAME}: "
                        f"{RAW_DATA_DIR_NAME} already contains nested directory {existing.name!r}"
                    )
                existing.unlink()
            for member in members:
                target = raw_dir / member.filename
                with archive.open(member, "r") as source, target.open("wb") as dest:
                    dest.write(source.read())
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        return f"could not restore {RAW_DATA_TRANSFER_ZIP_NAME}: {exc}"
    return None


def _flat_rawdata_zip_members(archive) -> tuple[object, ...]:
    members = tuple(archive.infolist())
    names: set[str] = set()
    for member in members:
        name = str(member.filename)
        if member.is_dir() or not name or "/" in name or "\\" in name:
            raise ValueError(
                f"archive member must be a direct .npz file, got {name!r}"
            )
        if Path(name).suffix.casefold() != ".npz":
            raise ValueError(f"archive member is not .npz: {name!r}")
        key = name.casefold()
        if key in names:
            raise ValueError(f"archive contains duplicate member name: {name!r}")
        names.add(key)
    return members


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
    return status == "error" and _rawdata_transfer_zip_is_readable(job_dir)


def _rawdata_transfer_zip_is_readable(job_dir: Path) -> bool:
    archive_path = job_dir / RAW_DATA_TRANSFER_ZIP_NAME
    if not archive_path.is_file():
        return False
    import zipfile

    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            _flat_rawdata_zip_members(archive)
            return archive.testzip() is None
    except (OSError, ValueError, zipfile.BadZipFile):
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


def cancelled_condor_result(
    job: JobSpec,
    *,
    submission: CondorSubmission | None,
    stage: str,
    remove_error: str | None,
) -> JobResult:
    metadata = base_metadata(job, engine="htcondor")
    metadata.update(
        status="cancelled",
        failure_stage=stage,
        error_type="EvaluationCancelled",
        error_message="evaluation cancellation was requested",
        cancelled_at=now_text(),
        condor_submit_file=CONDOR_SUBMIT_FILE_NAME,
    )
    if submission is not None:
        metadata.update(
            condor_cluster_id=submission.cluster_id,
            condor_submitted_at=submission.submitted_at,
        )
    if remove_error is not None:
        metadata["condor_remove_error"] = str(remove_error)[:4000]
        metadata["scheduler_cancellation_unconfirmed"] = True
    write_metadata(job.directory, metadata)
    return result_from_metadata(job, metadata)


def remove_condor_job(
    workspace: WorkspaceContext | str | Path,
    submission: CondorSubmission,
    *,
    config: LoadedConfig | None = None,
) -> str | None:
    effective = load_config(workspace) if config is None else config
    if submission.cluster_id is None:
        return None
    try:
        completed = subprocess.run(
            [htcondor_remove_exe(effective), str(submission.cluster_id)],
            cwd=str(submission.job.directory),
            capture_output=True,
            text=True,
            check=False,
            timeout=_CONDOR_REMOVE_COMMAND_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return (
            "condor_rm timed out after "
            f"{_CONDOR_REMOVE_COMMAND_TIMEOUT_SEC:g} seconds"
        )
    except OSError as exc:
        return str(exc)
    except Exception as exc:  # noqa: BLE001 - cleanup failure cannot defeat timeout finalization.
        return f"{type(exc).__name__}: {exc}"
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
    text = str(value)
    if any(char in text for char in ("\r", "\n", ",")):
        raise ValueError(
            "HTCondor transferred filenames cannot contain commas or newlines: "
            f"{text!r}"
        )
    # Submit values preserve spaces literally. Double quotes become part of a
    # Windows transfer filename, so quoting a path such as "model file.aedt"
    # makes Condor try to open a filename that includes the quote characters.
    return text


def _condor_bool(value: bool) -> str:
    return "True" if value else "False"


def _progress(message: str) -> None:
    if str(os.environ.get("YADOF_PROGRESS", "")).strip().lower() in {"1", "true", "yes", "on"}:
        print(f"[yadof] {message}", flush=True)
