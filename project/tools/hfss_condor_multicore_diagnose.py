from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


THIS_FILE = Path(__file__).resolve()
PROJECT_ROOT = THIS_FILE.parents[1]
REPO_ROOT = THIS_FILE.parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from project import config as key_config  # noqa: E402
from project import config_all as project_config  # noqa: E402
from project.evaluate_manager import config as evaluate_config  # noqa: E402
from project.evaluate_manager.api import evaluate_population  # noqa: E402
from project.job_template import api as job_template_api  # noqa: E402


DEFAULT_PROJECTS = {
    "08": REPO_ROOT / "temp" / "huangzetao20260708.aedt",
    "09": REPO_ROOT / "temp" / "huangzetao20260709.aedt",
}
WORKFLOW_PROJECT_NAME = "Newchoke20260620"
RAW_DATA_DIR_NAME = "rawData"
RAW_DATA_ZIP_NAME = "rawData_outputs.zip"
SUBMIT_NAME = "job.sub"
CONDOR_LOG_NAME = "condor.log"
STDOUT_NAME = "stdout.txt"
STDERR_NAME = "stderr.txt"
INDIVIDUAL_METADATA_NAME = "individual_metadata.json"


EVENT_COLLECTOR_PS1 = r'''
param(
    [string]$StartTime = "",
    [int]$Hours = 4,
    [string]$OutputDir = "rawData"
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

if (-not (Test-Path -LiteralPath $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

function Write-JsonFile {
    param([string]$Path, [object]$Value)
    $Value | ConvertTo-Json -Depth 8 | Out-File -FilePath $Path -Encoding utf8
}

try {
    if ([string]::IsNullOrWhiteSpace($StartTime)) {
        $start = (Get-Date).AddHours(-1 * [Math]::Max(1, $Hours))
    } else {
        $start = ([DateTimeOffset]::Parse($StartTime)).LocalDateTime.AddMinutes(-10)
    }
} catch {
    $start = (Get-Date).AddHours(-1 * [Math]::Max(1, $Hours))
}

$pattern = "hf3d|ansys|ansysedt|aedt|0xc0000005|c0000005|Application Error|Windows Error Reporting"
$rows = New-Object System.Collections.Generic.List[object]
foreach ($logName in @("Application", "System")) {
    try {
        $events = Get-WinEvent -FilterHashtable @{LogName = $logName; StartTime = $start} -ErrorAction Stop
        foreach ($event in $events) {
            $message = [string]$event.Message
            $provider = [string]$event.ProviderName
            if (($message -match $pattern) -or ($provider -match $pattern)) {
                $rows.Add([pscustomobject]@{
                    time_created = $event.TimeCreated.ToString("o")
                    log_name = $logName
                    provider_name = $provider
                    id = $event.Id
                    level = $event.LevelDisplayName
                    message = $message
                })
            }
        }
    } catch {
        $rows.Add([pscustomobject]@{
            time_created = (Get-Date).ToString("o")
            log_name = $logName
            provider_name = "collector"
            id = -1
            level = "Error"
            message = $_.Exception.Message
        })
    }
}

$identity = [ordered]@{
    collected_at = (Get-Date).ToString("o")
    start_time = $start.ToString("o")
    computername = $env:COMPUTERNAME
    username = $env:USERNAME
    userdomain = $env:USERDOMAIN
    whoami = (& whoami.exe 2>$null)
    event_count = $rows.Count
}
Write-JsonFile (Join-Path $OutputDir "windows_events_identity.json") $identity
Write-JsonFile (Join-Path $OutputDir "windows_events.json") $rows
Write-JsonFile (Join-Path $OutputDir "windows_events_summary.json") ([ordered]@{
    collected_at = (Get-Date).ToString("o")
    start_time = $start.ToString("o")
    event_count = $rows.Count
    providers = @($rows | Group-Object provider_name | Sort-Object Count -Descending | Select-Object Count, Name)
})
'''


EVENT_PROBE_WORKFLOW = r'''
from __future__ import annotations

import getpass
import json
import os
import platform
import subprocess
import sys
import traceback
import zipfile
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
RAW_DATA_DIR = BASE_DIR / "rawData"
RAW_DATA_ZIP = BASE_DIR / "rawData_outputs.zip"
METADATA = BASE_DIR / "individual_metadata.json"
COLLECTOR = BASE_DIR / "collect_windows_events.ps1"


def now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8", newline="\n")


def identity() -> dict[str, object]:
    try:
        whoami = subprocess.run(["whoami.exe"], capture_output=True, text=True, timeout=10, check=False).stdout.strip()
    except Exception:
        whoami = ""
    return {
        "worker_name": os.environ.get("COMPUTERNAME", ""),
        "runtime_user": getpass.getuser(),
        "runtime_whoami": whoami,
        "runtime_cwd": str(BASE_DIR),
        "runtime_python": sys.executable,
        "runtime_platform": platform.platform(),
        "runtime_condor_scratch_dir": os.environ.get("_CONDOR_SCRATCH_DIR", ""),
    }


def zip_raw_data() -> None:
    files = sorted(path for path in RAW_DATA_DIR.iterdir() if path.is_file())
    tmp_path = RAW_DATA_ZIP.with_name(RAW_DATA_ZIP.name + ".tmp")
    with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, arcname=path.name)
    os.replace(tmp_path, RAW_DATA_ZIP)


def main() -> int:
    started_at = now_text()
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    runtime_identity = identity()
    write_json(METADATA, {"status": "running", "started_at": started_at, **runtime_identity})
    try:
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(COLLECTOR),
                "-StartTime",
                os.environ.get("YADOF_EVENT_START", ""),
                "-Hours",
                os.environ.get("YADOF_EVENT_HOURS", "4"),
                "-OutputDir",
                str(RAW_DATA_DIR),
            ],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
        )
        (RAW_DATA_DIR / "collector.stdout.txt").write_text(completed.stdout or "", encoding="utf-8", newline="\n")
        (RAW_DATA_DIR / "collector.stderr.txt").write_text(completed.stderr or "", encoding="utf-8", newline="\n")
        zip_raw_data()
        report_files = [path.name for path in sorted(RAW_DATA_DIR.iterdir()) if path.is_file()]
        status = "done" if completed.returncode == 0 else "error"
        metadata = {
            "status": status,
            "started_at": started_at,
            "ended_at": now_text(),
            "collector_returncode": completed.returncode,
            "collector_stdout_tail": (completed.stdout or "")[-4000:],
            "collector_stderr_tail": (completed.stderr or "")[-4000:],
            "raw_data_files": report_files,
            **runtime_identity,
        }
        if completed.returncode != 0:
            metadata["error_message"] = f"Windows event collector exited with {completed.returncode}"
        write_json(METADATA, metadata)
        return int(completed.returncode)
    except Exception as exc:
        if RAW_DATA_DIR.exists():
            zip_raw_data()
        write_json(
            METADATA,
            {
                "status": "error",
                "started_at": started_at,
                "ended_at": now_text(),
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "traceback_tail": traceback.format_exc()[-4000:],
                **runtime_identity,
            },
        )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
'''


def now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def stamp_text() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(loaded) if isinstance(loaded, dict) else {}


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8", newline="\n")


def tail_text(path: Path, limit: int = 4000) -> str:
    if not path.is_file():
        return ""
    data = path.read_bytes()
    for encoding in ("utf-8", "utf-8-sig", "mbcs", "gbk"):
        try:
            return data.decode(encoding)[-limit:]
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode("utf-8", errors="replace")[-limit:]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_int_list(text: str) -> tuple[int, ...]:
    values: list[int] = []
    for item in str(text).split(","):
        stripped = item.strip()
        if not stripped:
            continue
        value = int(stripped)
        if value < 1:
            raise ValueError(f"core count must be positive: {value}")
        if value not in values:
            values.append(value)
    if not values:
        raise ValueError("at least one core count is required")
    return tuple(values)


def parse_project_labels(text: str) -> tuple[str, ...]:
    labels: list[str] = []
    for item in str(text).split(","):
        label = item.strip()
        if not label:
            continue
        if label not in DEFAULT_PROJECTS:
            raise ValueError(f"unknown project label {label!r}; expected one of {tuple(DEFAULT_PROJECTS)}")
        if label not in labels:
            labels.append(label)
    if not labels:
        raise ValueError("at least one project label is required")
    return tuple(labels)



def parse_cluster_id(text: str) -> int | None:
    match = re.search(r"submitted to cluster\s+(\d+)", text or "", flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def resolve_condor_config(explicit: str | None) -> str:
    if explicit:
        return explicit
    existing = os.environ.get("CONDOR_CONFIG", "").strip()
    if existing:
        return existing
    submit_exe = shutil.which(str(getattr(project_config, "HTCONDOR_SUBMIT_EXE", "condor_submit")))
    if submit_exe:
        candidate = Path(submit_exe).resolve().parents[1] / "condor_config"
        if candidate.is_file():
            return str(candidate)
    return ""


def subprocess_env(condor_config: str | None = None) -> dict[str, str]:
    env = dict(os.environ)
    if condor_config:
        env["CONDOR_CONFIG"] = condor_config
    return env


def run_command(
    command: Sequence[str],
    *,
    cwd: Path,
    condor_config: str | None = None,
    timeout_sec: int = 120,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=str(cwd),
        env=subprocess_env(condor_config),
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        check=False,
    )


def write_condor_status(path: Path, condor_config: str | None) -> None:
    completed = run_command(
        ["condor_status", "-af", "Name", "Machine", "Cpus", "Memory", "Disk", "OpSys", "YADOF_RAMDISK", "YADOF_EXECUTE_DIR"],
        cwd=REPO_ROOT,
        condor_config=condor_config,
        timeout_sec=60,
    )
    path.write_text(
        (completed.stdout or "") + ("\nSTDERR:\n" + completed.stderr if completed.stderr else ""),
        encoding="utf-8",
        newline="\n",
    )


def build_htcondor_environment(cores: int, *, ansys_license: str, non_graphical: bool) -> str:
    parts = [
        "USERPROFILE=._home",
        "HOME=._home",
        "APPDATA=._appdata",
        "LOCALAPPDATA=._localappdata",
        "TEMP=._tmp",
        "TMP=._tmp",
        f"YADOF_HFSS_JOB_CPUCORE={int(cores)}",
        "YADOF_HFSS_PARALLEL_TASKS=1",
        f"YADOF_HFSS_NON_GRAPHICAL={1 if non_graphical else 0}",
        "YADOF_HFSS_PIN_RETRIES=1",
        "YADOF_HFSS_RETRY_CPUCORE=1",
    ]
    if ansys_license:
        parts.append(f"ANSYSLMD_LICENSE_FILE={ansys_license}")
    return " ".join(parts)


def patch_runtime_config(
    *,
    cores: int,
    memory: str,
    disk: str,
    poll_sec: float,
    requirements: str,
    ansys_license: str,
    timeout_sec: float,
    condor_config: str,
) -> None:
    values: dict[str, Any] = {
        "EVALUATION_MODE": "distributed",
        "EVALUATION_TIMEOUT_SEC": float(timeout_sec),
        "HTCONDOR_REQUEST_CPUS": int(cores),
        "HTCONDOR_REQUEST_MEMORY": memory,
        "HTCONDOR_REQUEST_DISK": disk,
        "HTCONDOR_POLL_SEC": float(poll_sec),
        "HTCONDOR_REQUIREMENTS": requirements,
        "HTCONDOR_ALLOWED_MACHINES": (),
        "HTCONDOR_EXCLUDED_MACHINES": (),
        "HTCONDOR_ENVIRONMENT": build_htcondor_environment(cores, ansys_license=ansys_license, non_graphical=True),
        "HFSS_JOB_CPUCORE": int(cores),
        "HFSS_PARALLEL_TASKS": 1,
        "HFSS_NON_GRAPHICAL": True,
        "ANSYS_LICENSE_SERVER": ansys_license,
    }
    modules = (key_config, project_config, evaluate_config.project_config)
    for module in modules:
        for name, value in values.items():
            setattr(module, name, value)
    evaluate_config.project_config = project_config
    if condor_config:
        os.environ["CONDOR_CONFIG"] = condor_config
    os.environ["YADOF_PROGRESS"] = "1"


def ignore_template_items(_dir: str, names: list[str]) -> set[str]:
    ignored = {"__pycache__", "._appdata", "._home", "._localappdata", "._tmp", "_tmp", "rawData", "history"}
    return {
        name
        for name in names
        if name in ignored
        or name.lower().endswith((".aedtresults", ".aedtresult", ".pyaedt", ".lock"))
    }


def prepare_project_template(label: str, aedt_path: Path, work_dir: Path) -> Path:
    template_dir = work_dir / "templates" / f"template_{label}"
    if template_dir.exists():
        shutil.rmtree(template_dir)
    shutil.copytree(PROJECT_ROOT / "job_template", template_dir, ignore=ignore_template_items)
    for existing in template_dir.glob("*.aedt"):
        existing.unlink()
    shutil.copy2(aedt_path, template_dir / f"{WORKFLOW_PROJECT_NAME}.aedt")
    return template_dir


def population_row() -> tuple[float, ...]:
    return (0.5,) * int(job_template_api.get_variable_count())


def find_job_by_run_id(jobs_dir: Path, run_id: str) -> Path | None:
    if not jobs_dir.is_dir():
        return None
    directories = sorted((path for path in jobs_dir.iterdir() if path.is_dir()), key=lambda path: path.stat().st_mtime, reverse=True)
    for directory in directories:
        metadata = read_json(directory / "metadata.json")
        if metadata.get("run_id") == run_id:
            return directory
    return None


def parse_submit_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().lower()
        if key in {"request_cpus", "request_memory", "request_disk", "requirements", "environment", "executable"}:
            values[f"submit_{key}"] = value.strip().strip('"')
    return values


def parse_condor_log(path: Path) -> dict[str, Any]:
    text = tail_text(path, limit=20000)
    info: dict[str, Any] = {}
    slot_match = re.search(r"SlotName:\s+\S+@([^\s]+)", text)
    if slot_match:
        info["condor_execute_machine"] = slot_match.group(1)
    alias_match = re.search(r"alias=([^&>\s]+)", text)
    if alias_match and "condor_execute_machine" not in info:
        info["condor_execute_machine"] = alias_match.group(1)
    return_matches = re.findall(r"Normal termination \(return value ([^)]+)\)", text, flags=re.IGNORECASE)
    if return_matches:
        raw_value = return_matches[-1].strip()
        try:
            value = int(raw_value, 0)
            info["condor_return_value"] = value
            info["condor_return_value_hex"] = f"0x{(value & 0xFFFFFFFF):08X}"
        except ValueError:
            info["condor_return_value"] = raw_value
    for key in ("Cpus", "Memory", "Disk"):
        matches = re.findall(rf"^\s*{key}\s*=\s*([^\r\n]+)", text, flags=re.MULTILINE)
        if matches:
            info[f"condor_allocated_{key.lower()}"] = matches[-1].strip()
    memory_usage = re.findall(r"^\s*(\d+)\s+-\s+MemoryUsage of job \(MB\)", text, flags=re.MULTILINE)
    if memory_usage:
        info["condor_peak_memory_usage_mb"] = max(int(value) for value in memory_usage)
    return info


def collect_local_events(output_dir: Path, *, start_time: str, hours: int, condor_config: str | None) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    collector = output_dir / "collect_windows_events.ps1"
    collector.write_text(EVENT_COLLECTOR_PS1.strip() + "\n", encoding="utf-8", newline="\n")
    completed = run_command(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(collector),
            "-StartTime",
            start_time,
            "-Hours",
            str(hours),
            "-OutputDir",
            str(output_dir),
        ],
        cwd=REPO_ROOT,
        condor_config=condor_config,
        timeout_sec=900,
    )
    (output_dir / "collector.stdout.txt").write_text(completed.stdout or "", encoding="utf-8", newline="\n")
    (output_dir / "collector.stderr.txt").write_text(completed.stderr or "", encoding="utf-8", newline="\n")
    return {
        "local_event_dir": str(output_dir),
        "local_event_returncode": completed.returncode,
        "local_event_count": read_json(output_dir / "windows_events_summary.json").get("event_count"),
    }


def extract_raw_zip(job_dir: Path) -> list[str]:
    raw_dir = job_dir / RAW_DATA_DIR_NAME
    raw_dir.mkdir(exist_ok=True)
    archive_path = job_dir / RAW_DATA_ZIP_NAME
    if archive_path.is_file():
        with zipfile.ZipFile(archive_path, "r") as archive:
            for member in archive.infolist():
                name = member.filename.replace("\\", "/")
                if member.is_dir() or "/" in name:
                    continue
                target = raw_dir / Path(name).name
                with archive.open(member, "r") as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination)
    return [path.name for path in sorted(raw_dir.iterdir()) if path.is_file()]


def submit_worker_event_probe(
    *,
    machine: str,
    start_time: str,
    hours: int,
    jobs_dir: Path,
    requirements: str,
    condor_config: str | None,
    timeout_sec: int = 1200,
) -> dict[str, Any]:
    safe_machine = re.sub(r"[^A-Za-z0-9_.-]+", "_", machine).lower()
    job_dir = jobs_dir / f"job_{stamp_text()}_{int(time.time() * 1000) % 1000000:06d}_eventprobe_{safe_machine}"
    job_dir.mkdir(parents=True)
    for name in ("._home", "._appdata", "._localappdata", "._tmp", RAW_DATA_DIR_NAME):
        (job_dir / name).mkdir()
    (job_dir / "workflow.py").write_text(EVENT_PROBE_WORKFLOW.strip() + "\n", encoding="utf-8", newline="\n")
    (job_dir / "collect_windows_events.ps1").write_text(EVENT_COLLECTOR_PS1.strip() + "\n", encoding="utf-8", newline="\n")
    write_json(
        job_dir / "metadata.json",
        {
            "job_name": job_dir.name,
            "status": "prepared",
            "engine": "htcondor",
            "probe": "windows_event_log",
            "requested_machine": machine,
            "event_start_time": start_time,
            "event_hours": hours,
            "created_at": now_text(),
        },
    )
    base = requirements.strip() or '(OpSys == "WINDOWS")'
    probe_requirements = f"({base}) && (Machine =?= \"{machine}\")"
    environment = (
        "USERPROFILE=._home HOME=._home APPDATA=._appdata LOCALAPPDATA=._localappdata "
        f"TEMP=._tmp TMP=._tmp YADOF_EVENT_START={start_time} YADOF_EVENT_HOURS={int(hours)}"
    )
    submit_text = "\n".join(
        [
            "# Auto-generated by project.tools.hfss_condor_multicore_diagnose",
            "universe = vanilla",
            "executable = workflow.py",
            "initialdir = .",
            "getenv = False",
            f'environment = "{environment}"',
            f"load_profile = {'True' if bool(getattr(project_config, 'HTCONDOR_LOAD_PROFILE', True)) else 'False'}",
            f"run_as_owner = {'True' if bool(getattr(project_config, 'HTCONDOR_RUN_AS_OWNER', False)) else 'False'}",
            f"requirements = {probe_requirements}",
            "should_transfer_files = YES",
            "when_to_transfer_output = ON_EXIT",
            "transfer_executable = True",
            "transfer_input_files = ._appdata,._home,._localappdata,._tmp,collect_windows_events.ps1",
            f"output = {STDOUT_NAME}",
            f"error = {STDERR_NAME}",
            f"log = {CONDOR_LOG_NAME}",
            "request_cpus = 1",
            "request_memory = 512MB",
            "request_disk = 1GB",
            "notification = never",
            "queue 1",
            "",
        ]
    )
    (job_dir / SUBMIT_NAME).write_text(submit_text, encoding="utf-8", newline="\n")
    submit = run_command([str(getattr(project_config, "HTCONDOR_SUBMIT_EXE", "condor_submit")), SUBMIT_NAME], cwd=job_dir, condor_config=condor_config)
    (job_dir / "condor_submit.stdout.txt").write_text(submit.stdout or "", encoding="utf-8", newline="\n")
    (job_dir / "condor_submit.stderr.txt").write_text(submit.stderr or "", encoding="utf-8", newline="\n")
    cluster_id = parse_cluster_id(submit.stdout or "")
    wait_returncode: int | None = None
    if submit.returncode == 0:
        wait = run_command(["condor_wait", "-wait", str(timeout_sec), CONDOR_LOG_NAME], cwd=job_dir, condor_config=condor_config, timeout_sec=timeout_sec + 30)
        wait_returncode = wait.returncode
        (job_dir / "condor_wait.stdout.txt").write_text(wait.stdout or "", encoding="utf-8", newline="\n")
        (job_dir / "condor_wait.stderr.txt").write_text(wait.stderr or "", encoding="utf-8", newline="\n")
    raw_files = extract_raw_zip(job_dir)
    individual = read_json(job_dir / INDIVIDUAL_METADATA_NAME)
    metadata = read_json(job_dir / "metadata.json")
    metadata.update(individual)
    metadata.update(
        {
            "status": str(individual.get("status") or ("done" if wait_returncode == 0 else "error")),
            "condor_cluster_id": cluster_id,
            "condor_submit_returncode": submit.returncode,
            "condor_wait_returncode": wait_returncode,
            "raw_data_files": raw_files,
            "runner_finished_at": now_text(),
        }
    )
    write_json(job_dir / "metadata.json", metadata)
    return {
        "worker_event_probe_job": str(job_dir),
        "worker_event_probe_status": metadata.get("status"),
        "worker_event_probe_cluster": cluster_id,
        "worker_event_probe_files": raw_files,
        "worker_event_count": read_json(job_dir / RAW_DATA_DIR_NAME / "windows_events_summary.json").get("event_count"),
    }


def case_record(
    *,
    label: str,
    aedt_path: Path,
    cores: int,
    memory: str,
    costs: Sequence[Sequence[float]],
    job_dir: Path | None,
    started_at: str,
    ended_at: str,
) -> dict[str, Any]:
    metadata = read_json(job_dir / "metadata.json") if job_dir else {}
    individual = read_json(job_dir / INDIVIDUAL_METADATA_NAME) if job_dir else {}
    combined: dict[str, Any] = {}
    combined.update(metadata)
    combined.update(individual)
    submit_info = parse_submit_file(job_dir / SUBMIT_NAME) if job_dir else {}
    condor_info = parse_condor_log(job_dir / CONDOR_LOG_NAME) if job_dir else {}
    record: dict[str, Any] = {
        "project_label": label,
        "aedt_path": str(aedt_path),
        "aedt_sha256": sha256_file(aedt_path),
        "requested_cores": int(cores),
        "requested_memory": memory,
        "started_at": started_at,
        "ended_at": ended_at,
        "job_dir": str(job_dir) if job_dir else "",
        "status": combined.get("status", "missing_job"),
        "error": combined.get("error") or combined.get("error_message") or "",
        "costs": costs,
        "raw_data_files": combined.get("raw_data_files", []),
        "runtime_hfss_job_cpucore": combined.get("runtime_hfss_job_cpucore"),
        "runtime_hfss_parallel_tasks": combined.get("runtime_hfss_parallel_tasks"),
        "runtime_user": combined.get("runtime_user"),
        "runtime_whoami": combined.get("runtime_whoami"),
        "runtime_cwd": combined.get("runtime_cwd"),
        "runtime_condor_scratch_dir": combined.get("runtime_condor_scratch_dir"),
        "runtime_temp": combined.get("runtime_temp"),
        "runtime_ansys_license": combined.get("runtime_ansys_license"),
        "batch_log_tail": tail_text(job_dir / "batch.log") if job_dir else "",
        "stdout_tail": tail_text(job_dir / STDOUT_NAME) if job_dir else "",
        "stderr_tail": tail_text(job_dir / STDERR_NAME) if job_dir else "",
    }
    record.update(submit_info)
    record.update(condor_info)
    return record


def run_case(
    *,
    label: str,
    aedt_path: Path,
    template_dir: Path,
    cores: int,
    memory: str,
    args: argparse.Namespace,
    work_dir: Path,
    condor_config: str,
) -> dict[str, Any]:
    started_at = now_text()
    run_id = f"hfss_condor_diag_{label}_cpu{cores}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    patch_runtime_config(
        cores=cores,
        memory=memory,
        disk=str(args.disk),
        poll_sec=float(args.poll_sec),
        requirements=str(args.requirements),
        ansys_license=str(args.ansys_license),
        timeout_sec=float(args.timeout_sec),
        condor_config=condor_config,
    )
    print(f"running project={label} cores={cores} memory={memory} run_id={run_id}", flush=True)
    costs = evaluate_population(
        (population_row(),),
        mode="distributed",
        jobs_dir=PROJECT_ROOT / "jobs",
        job_template_dir=template_dir,
        timeout_sec=float(args.timeout_sec),
        run_id=run_id,
        optimization_index=0,
        generation_index=0,
    )
    ended_at = now_text()
    job_dir = find_job_by_run_id(PROJECT_ROOT / "jobs", run_id)
    record = case_record(
        label=label,
        aedt_path=aedt_path,
        cores=cores,
        memory=memory,
        costs=costs,
        job_dir=job_dir,
        started_at=started_at,
        ended_at=ended_at,
    )
    event_mode = str(args.collect_events).strip().lower()
    should_collect = event_mode == "always" or (event_mode == "auto" and record.get("status") != "done")
    if should_collect:
        event_dir = work_dir / "events" / f"{label}_cpu{cores}_local"
        record.update(collect_local_events(event_dir, start_time=started_at, hours=int(args.event_hours), condor_config=condor_config))
        machine = str(record.get("condor_execute_machine") or "").strip()
        if machine:
            try:
                record.update(
                    submit_worker_event_probe(
                        machine=machine,
                        start_time=started_at,
                        hours=int(args.event_hours),
                        jobs_dir=PROJECT_ROOT / "jobs",
                        requirements=str(args.requirements),
                        condor_config=condor_config,
                    )
                )
            except Exception as exc:  # noqa: BLE001 - event collection must not hide the HFSS result.
                record["worker_event_probe_error"] = f"{type(exc).__name__}: {exc}"
    return record


def write_markdown_summary(path: Path, payload: Mapping[str, Any]) -> None:
    rows = payload.get("cases", [])
    lines = [
        "# HFSS Condor Multicore Diagnosis",
        "",
        f"- Generated at: {payload.get('generated_at')}",
        f"- Requirements: `{payload.get('requirements')}`",
        f"- Memory: `{payload.get('memory')}`",
        "",
        "| Project | Cores | Status | Return | Worker | Runtime cores | Memory MB | Job |",
        "| --- | ---: | --- | --- | --- | ---: | ---: | --- |",
    ]
    for row in rows if isinstance(rows, list) else []:
        job_name = Path(str(row.get("job_dir") or "")).name
        lines.append(
            "| {project} | {cores} | {status} | {ret} | {worker} | {runtime} | {mem} | {job} |".format(
                project=row.get("project_label", ""),
                cores=row.get("requested_cores", ""),
                status=row.get("status", ""),
                ret=row.get("condor_return_value_hex") or row.get("condor_return_value") or "",
                worker=row.get("condor_execute_machine", ""),
                runtime=row.get("runtime_hfss_job_cpucore", ""),
                mem=row.get("condor_peak_memory_usage_mb", ""),
                job=job_name,
            )
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def matrix_cases(labels: Iterable[str], cores: Sequence[int], include_one_core_control: bool) -> tuple[tuple[str, int], ...]:
    cases: list[tuple[str, int]] = []
    for label in labels:
        label_cores = list(cores)
        if label == "08" and include_one_core_control and 1 not in label_cores:
            label_cores = [1] + label_cores
        for core in label_cores:
            cases.append((label, int(core)))
    return tuple(cases)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run controlled HFSS HTCondor multicore diagnostics.")
    parser.add_argument("--projects", default="08,09", help="Comma-separated project labels: 08,09.")
    parser.add_argument("--cores", default="2,6", help="Comma-separated multicore values. Default follows the 20260709 efficient test plan.")
    parser.add_argument("--skip-one-core-control", action="store_true", help="Do not prepend the 08 one-core control.")
    parser.add_argument("--memory", default="16GB", help="HTCondor request_memory for all HFSS runs.")
    parser.add_argument("--disk", default=str(getattr(project_config, "HTCONDOR_REQUEST_DISK", "5GB")))
    parser.add_argument("--requirements", default='(OpSys == "WINDOWS")', help="Base HTCondor requirements.")
    parser.add_argument("--timeout-sec", type=float, default=float(getattr(project_config, "EVALUATION_TIMEOUT_SEC", 6 * 60 * 60)))
    parser.add_argument("--poll-sec", type=float, default=300.0)
    parser.add_argument("--condor-config", default="")
    parser.add_argument("--ansys-license", default=str(getattr(project_config, "ANSYS_LICENSE_SERVER", os.environ.get("ANSYSLMD_LICENSE_FILE", "1055@localhost"))))
    parser.add_argument("--work-dir", default="")
    parser.add_argument("--collect-events", choices=("auto", "always", "never"), default="auto")
    parser.add_argument("--event-hours", type=int, default=4)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    labels = parse_project_labels(args.projects)
    cores = parse_int_list(args.cores)
    condor_config = resolve_condor_config(args.condor_config or None)
    work_dir = Path(args.work_dir) if args.work_dir else REPO_ROOT / "temp" / f"hfss_condor_multicore_diag_{stamp_text()}"
    work_dir.mkdir(parents=True, exist_ok=True)
    write_condor_status(work_dir / "condor_status.txt", condor_config)

    templates: dict[str, Path] = {}
    aedt_paths: dict[str, Path] = {}
    for label in labels:
        aedt_path = DEFAULT_PROJECTS[label]
        if not aedt_path.is_file():
            raise FileNotFoundError(aedt_path)
        aedt_paths[label] = aedt_path
        templates[label] = prepare_project_template(label, aedt_path, work_dir)

    cases: list[dict[str, Any]] = []
    for label, core_count in matrix_cases(labels, cores, not args.skip_one_core_control):
        record = run_case(
            label=label,
            aedt_path=aedt_paths[label],
            template_dir=templates[label],
            cores=core_count,
            memory=str(args.memory),
            args=args,
            work_dir=work_dir,
            condor_config=condor_config,
        )
        cases.append(record)
        summary_path = work_dir / "diagnostic_summary.json"
        write_json(
            summary_path,
            {
                "generated_at": now_text(),
                "work_dir": str(work_dir),
                "condor_config": condor_config,
                "requirements": str(args.requirements),
                "memory": str(args.memory),
                "cores": list(cores),
                "cases": cases,
            },
        )
        write_markdown_summary(work_dir / "diagnostic_summary.md", read_json(summary_path))
        print(f"completed project={label} cores={core_count} status={record.get('status')} job={record.get('job_dir')}", flush=True)

    final_payload = read_json(work_dir / "diagnostic_summary.json")
    print(f"summary={work_dir / 'diagnostic_summary.md'}", flush=True)
    statuses = [str(row.get("status")) for row in final_payload.get("cases", []) if isinstance(row, dict)]
    return 0 if statuses and all(status == "done" for status in statuses) else 1


if __name__ == "__main__":
    raise SystemExit(main())
