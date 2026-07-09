from __future__ import annotations

import argparse
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
from typing import Sequence


THIS_FILE = Path(__file__).resolve()
PROJECT_ROOT = THIS_FILE.parents[1]
REPO_ROOT = THIS_FILE.parents[2]
COLLECTOR_SOURCE = THIS_FILE.with_name("collect_ansys_event_logs.ps1")
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from project import config_all as project_config  # noqa: E402


TARGET_MACHINE = "DESKTOP-A2096"
WORKFLOW_NAME = "workflow.py"
COLLECTOR_NAME = "collect_ansys_event_logs.ps1"
RAW_DATA_DIR_NAME = "rawData"
RAW_DATA_ZIP_NAME = "rawData_outputs.zip"
INDIVIDUAL_METADATA_NAME = "individual_metadata.json"
SUBMIT_NAME = "job.sub"
CONDOR_LOG_NAME = "condor.log"
STDOUT_NAME = "stdout.txt"
STDERR_NAME = "stderr.txt"


WORKFLOW_SOURCE = r'''from __future__ import annotations

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
INDIVIDUAL_METADATA = BASE_DIR / "individual_metadata.json"
COLLECTOR = BASE_DIR / "collect_ansys_event_logs.ps1"


def now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8", newline="\n")


def identity() -> dict[str, str]:
    try:
        whoami = subprocess.run(
            ["whoami.exe"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        ).stdout.strip()
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
    hours = max(1, int(os.environ.get("YADOF_EVENT_PROBE_HOURS", "48")))
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    runtime_identity = identity()
    write_json(
        INDIVIDUAL_METADATA,
        {
            "status": "running",
            "started_at": started_at,
            "query_hours": hours,
            **runtime_identity,
        },
    )

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
                "-Hours",
                str(hours),
                "-OutputDir",
                str(RAW_DATA_DIR),
            ],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        (RAW_DATA_DIR / "collector.stdout.txt").write_text(
            completed.stdout or "", encoding="utf-8", newline="\n"
        )
        (RAW_DATA_DIR / "collector.stderr.txt").write_text(
            completed.stderr or "", encoding="utf-8", newline="\n"
        )
        zip_raw_data()
        report_files = [
            path.name for path in sorted(RAW_DATA_DIR.iterdir()) if path.is_file()
        ]
        status = "done" if completed.returncode == 0 else "error"
        metadata = {
            "status": status,
            "started_at": started_at,
            "ended_at": now_text(),
            "query_hours": hours,
            "collector_returncode": completed.returncode,
            "collector_stdout_tail": (completed.stdout or "")[-4000:],
            "collector_stderr_tail": (completed.stderr or "")[-4000:],
            "raw_data_files": report_files,
            **runtime_identity,
        }
        if completed.returncode != 0:
            metadata["error_message"] = f"event collector exited with {completed.returncode}"
        write_json(INDIVIDUAL_METADATA, metadata)
        return int(completed.returncode)
    except Exception as exc:
        if RAW_DATA_DIR.exists():
            zip_raw_data()
        write_json(
            INDIVIDUAL_METADATA,
            {
                "status": "error",
                "started_at": started_at,
                "ended_at": now_text(),
                "query_hours": hours,
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


def new_job_name() -> str:
    return f"job_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_eventprobe_desktop-a2096"


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8", newline="\n")


def read_json(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(loaded) if isinstance(loaded, dict) else {}


def parse_cluster_id(text: str) -> int | None:
    match = re.search(r"submitted to cluster\s+(\d+)", text, flags=re.IGNORECASE)
    return int(match.group(1)) if match else None



def prepare_job(hours: int) -> Path:
    if not COLLECTOR_SOURCE.is_file():
        raise FileNotFoundError(COLLECTOR_SOURCE)

    jobs_dir = Path(project_config.JOBS_DIR)
    jobs_dir.mkdir(parents=True, exist_ok=True)
    job_dir = jobs_dir / new_job_name()
    job_dir.mkdir()
    for name in ("._home", "._appdata", "._localappdata", "._tmp", RAW_DATA_DIR_NAME):
        (job_dir / name).mkdir()

    (job_dir / WORKFLOW_NAME).write_text(WORKFLOW_SOURCE, encoding="utf-8", newline="\n")
    shutil.copy2(COLLECTOR_SOURCE, job_dir / COLLECTOR_NAME)
    write_json(
        job_dir / "job_input.json",
        {
            "job_name": job_dir.name,
            "probe": "ansys_event_viewer",
            "requested_machine": TARGET_MACHINE,
            "query_hours": hours,
            "created_at": now_text(),
        },
    )
    metadata = {
        "job_name": job_dir.name,
        "status": "prepared",
        "engine": "htcondor",
        "probe": "ansys_event_viewer",
        "requested_machine": TARGET_MACHINE,
        "query_hours": hours,
        "created_at": now_text(),
    }
    write_json(job_dir / "metadata.json", metadata)
    write_json(job_dir / "metaData.json", metadata)

    base_requirement = str(project_config.HTCONDOR_REQUIREMENTS).strip()
    requirements = f'{base_requirement} && (Machine =?= "{TARGET_MACHINE}")'
    environment = (
        "USERPROFILE=._home "
        "HOME=._home "
        "APPDATA=._appdata "
        "LOCALAPPDATA=._localappdata "
        "TEMP=._tmp "
        "TMP=._tmp "
        f"YADOF_EVENT_PROBE_HOURS={hours}"
    )
    submit_lines = [
        "# Auto-generated by project.tools.submit_condor_event_probe",
        "universe = vanilla",
        f"executable = {WORKFLOW_NAME}",
        "initialdir = .",
        "getenv = False",
        f'environment = "{environment}"',
        f"load_profile = {bool(project_config.HTCONDOR_LOAD_PROFILE)}",
        f"run_as_owner = {bool(project_config.HTCONDOR_RUN_AS_OWNER)}",
        f"requirements = {requirements}",
        "should_transfer_files = YES",
        "when_to_transfer_output = ON_EXIT",
        "transfer_executable = True",
        (
            "transfer_input_files = "
            "._appdata,._home,._localappdata,._tmp,"
            f"{COLLECTOR_NAME},job_input.json"
        ),
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
    (job_dir / SUBMIT_NAME).write_text("\n".join(submit_lines), encoding="utf-8", newline="\n")
    return job_dir


def extract_reports(job_dir: Path) -> list[Path]:
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
                with archive.open(member, "r") as source, target.open("wb") as dest:
                    shutil.copyfileobj(source, dest)
    return sorted((path for path in raw_dir.iterdir() if path.is_file()), key=lambda path: path.name.lower())


def submit_and_wait(job_dir: Path, timeout_sec: int) -> dict[str, object]:
    submitted_at = now_text()
    submit = subprocess.run(
        [str(project_config.HTCONDOR_SUBMIT_EXE), SUBMIT_NAME],
        cwd=str(job_dir),
        capture_output=True,
        text=True,
        check=False,
    )
    (job_dir / "condor_submit.stdout.txt").write_text(submit.stdout or "", encoding="utf-8", newline="\n")
    (job_dir / "condor_submit.stderr.txt").write_text(submit.stderr or "", encoding="utf-8", newline="\n")
    if submit.returncode != 0:
        raise RuntimeError(submit.stderr or submit.stdout or f"condor_submit exited with {submit.returncode}")

    cluster_id = parse_cluster_id(submit.stdout or "")
    if cluster_id is not None:
        (job_dir / "cluster.id").write_text(str(cluster_id), encoding="utf-8", newline="\n")

    wait = subprocess.run(
        ["condor_wait", "-wait", str(timeout_sec), CONDOR_LOG_NAME],
        cwd=str(job_dir),
        capture_output=True,
        text=True,
        timeout=timeout_sec + 30,
        check=False,
    )
    reports = extract_reports(job_dir)
    individual = read_json(job_dir / INDIVIDUAL_METADATA_NAME)
    metadata = read_json(job_dir / "metadata.json")
    metadata.update(individual)
    metadata.update(
        {
            "job_name": job_dir.name,
            "status": str(individual.get("status") or ("done" if wait.returncode == 0 else "error")),
            "requested_machine": TARGET_MACHINE,
            "condor_cluster_id": cluster_id,
            "condor_submitted_at": submitted_at,
            "condor_submit_stdout_tail": (submit.stdout or "")[-4000:],
            "condor_submit_stderr_tail": (submit.stderr or "")[-4000:],
            "condor_wait_returncode": wait.returncode,
            "condor_wait_stdout_tail": (wait.stdout or "")[-4000:],
            "condor_wait_stderr_tail": (wait.stderr or "")[-4000:],
            "raw_data_files": [path.name for path in reports],
            "runner_finished_at": now_text(),
        }
    )
    write_json(job_dir / "metadata.json", metadata)
    write_json(job_dir / "metaData.json", metadata)
    return metadata


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect recent ANSYS-related Windows events on DESKTOP-A2096.")
    parser.add_argument("--hours", type=int, default=48)
    parser.add_argument("--timeout-sec", type=int, default=900)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    job_dir = prepare_job(max(1, int(args.hours)))
    print(f"prepared={job_dir}")
    metadata = submit_and_wait(job_dir, max(60, int(args.timeout_sec)))
    print(f"status={metadata.get('status')}")
    print(f"cluster={metadata.get('condor_cluster_id')}")
    print(f"worker={metadata.get('worker_name')}")
    print(f"whoami={metadata.get('runtime_whoami')}")
    print(f"reports={','.join(str(item) for item in metadata.get('raw_data_files', []))}")
    return 0 if metadata.get("status") == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
