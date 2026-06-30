from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Sequence


THIS_FILE = Path(__file__).resolve()
PROJECT_ROOT = THIS_FILE.parents[1]
REPO_ROOT = THIS_FILE.parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from project import config as project_config  # noqa: E402


TARGET_MACHINE = "DESKTOP-2094"
WORKFLOW_NAME = "workflow.py"
RAW_DATA_DIR_NAME = "rawData"
RAW_DATA_ZIP_NAME = "rawData_outputs.zip"
INDIVIDUAL_METADATA_NAME = "individual_metadata.json"
SUBMIT_NAME = "job.sub"
CONDOR_LOG_NAME = "condor.log"
STDOUT_NAME = "stdout.txt"
STDERR_NAME = "stderr.txt"
ACTION_SCRIPTS = {
    "diagnose": "collect_desktop2094_diagnostics.ps1",
    "fix": "fix_desktop2094_ansys_settings.ps1",
}


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


def now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8", newline="\n")


def bootstrap_env() -> None:
    for key, path in {
        "USERPROFILE": BASE_DIR / "_home",
        "HOME": BASE_DIR / "_home",
        "APPDATA": BASE_DIR / "_appdata",
        "LOCALAPPDATA": BASE_DIR / "_localappdata",
        "TEMP": BASE_DIR / "_tmp",
        "TMP": BASE_DIR / "_tmp",
        "TMPDIR": BASE_DIR / "_tmp",
    }.items():
        os.environ[key] = str(path)
        path.mkdir(parents=True, exist_ok=True)


def identity() -> dict[str, str]:
    try:
        whoami = subprocess.run(
            ["whoami.exe"], capture_output=True, text=True, timeout=10, check=False
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
        "runtime_userprofile": os.environ.get("USERPROFILE", ""),
        "runtime_appdata": os.environ.get("APPDATA", ""),
        "runtime_localappdata": os.environ.get("LOCALAPPDATA", ""),
        "runtime_temp": os.environ.get("TEMP", ""),
    }


def zip_raw_data() -> None:
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(path for path in RAW_DATA_DIR.iterdir() if path.is_file())
    tmp_path = RAW_DATA_ZIP.with_name(RAW_DATA_ZIP.name + ".tmp")
    with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, arcname=path.name)
    os.replace(tmp_path, RAW_DATA_ZIP)


def main() -> int:
    bootstrap_env()
    started_at = now_text()
    job_input = {}
    try:
        job_input = json.loads((BASE_DIR / "job_input.json").read_text(encoding="utf-8"))
    except Exception:
        job_input = {}
    action = os.environ.get("YADOF_2094_ACTION", "diagnose")
    script_name = os.environ.get("YADOF_2094_SCRIPT", "") or str(job_input.get("script_name") or "")
    event_hours = os.environ.get("YADOF_2094_EVENT_HOURS", "24")
    dry_run = os.environ.get("YADOF_2094_DRY_RUN", "0").strip().lower() in {"1", "true", "yes", "on"}
    script = BASE_DIR / script_name
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    runtime_identity = identity()
    write_json(
        INDIVIDUAL_METADATA,
        {"status": "running", "started_at": started_at, "action": action, **runtime_identity},
    )
    try:
        args = [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-OutputDir",
            str(RAW_DATA_DIR),
        ]
        if action == "diagnose":
            args.extend(["-EventHours", str(event_hours)])
        if action == "fix" and dry_run:
            args.append("-DryRun")
        completed = subprocess.run(
            args,
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=int(os.environ.get("YADOF_2094_TIMEOUT_SEC", "1800")),
            check=False,
        )
        (RAW_DATA_DIR / "collector.stdout.txt").write_text(completed.stdout or "", encoding="utf-8", newline="\n")
        (RAW_DATA_DIR / "collector.stderr.txt").write_text(completed.stderr or "", encoding="utf-8", newline="\n")
        zip_raw_data()
        reports = [path.name for path in sorted(RAW_DATA_DIR.iterdir()) if path.is_file()]
        status = "done" if completed.returncode == 0 else "error"
        payload = {
            "status": status,
            "started_at": started_at,
            "ended_at": now_text(),
            "action": action,
            "script": script_name,
            "event_hours": event_hours,
            "dry_run": dry_run,
            "collector_returncode": completed.returncode,
            "collector_stdout_tail": (completed.stdout or "")[-4000:],
            "collector_stderr_tail": (completed.stderr or "")[-4000:],
            "raw_data_files": reports,
            **runtime_identity,
        }
        if completed.returncode != 0:
            payload["error_message"] = f"{action} script exited with {completed.returncode}"
        write_json(INDIVIDUAL_METADATA, payload)
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
                "action": action,
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


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8", newline="\n")


def read_json(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(loaded) if isinstance(loaded, dict) else {}


def parse_cluster_id(text: str) -> int | None:
    match = re.search(r"submitted to cluster\s+(\d+)", text, flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def quote_atom(value: str) -> str:
    return f'"{value}"' if any(char in value for char in (" ", ",")) else value


def new_job_dir(action: str, target: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    label = re.sub(r"[^A-Za-z0-9_.-]+", "_", target).lower()
    job_dir = Path(project_config.JOBS_DIR) / f"job_{stamp}_{action}_{label}"
    job_dir.mkdir(parents=True)
    return job_dir


def prepare_job(
    action: str,
    *,
    target_machine: str,
    target_slot: str | None,
    dry_run: bool,
    event_hours: int,
    script_timeout_sec: int,
) -> Path:
    script_name = ACTION_SCRIPTS[action]
    script_source = THIS_FILE.with_name(script_name)
    if not script_source.is_file():
        raise FileNotFoundError(script_source)
    target = target_slot or target_machine
    job_dir = new_job_dir(action, target)
    for name in ("_home", "_appdata", "_localappdata", "_tmp", RAW_DATA_DIR_NAME):
        (job_dir / name).mkdir()
    (job_dir / WORKFLOW_NAME).write_text(WORKFLOW_SOURCE, encoding="utf-8", newline="\n")
    shutil.copy2(script_source, job_dir / script_name)
    metadata = {
        "job_name": job_dir.name,
        "status": "prepared",
        "engine": "htcondor",
        "probe": "desktop2094_ansys",
        "action": action,
        "requested_machine": target_machine,
        "requested_slot": target_slot or "",
        "dry_run": bool(dry_run),
        "script_name": script_name,
        "created_at": now_text(),
    }
    write_json(job_dir / "metadata.json", metadata)
    write_json(job_dir / "metaData.json", metadata)
    write_json(job_dir / "job_input.json", metadata)

    base_requirement = str(project_config.HTCONDOR_REQUIREMENTS).strip()
    requirements = f'{base_requirement} && (Machine =?= "{target_machine}")'
    if target_slot:
        requirements += f' && (Name =?= "{target_slot}")'
    environment = (
        "USERPROFILE=_home;"
        "HOME=_home;"
        "APPDATA=_appdata;"
        "LOCALAPPDATA=_localappdata;"
        "TEMP=_tmp;"
        "TMP=_tmp;"
        f"YADOF_2094_ACTION={action};"
        f"YADOF_2094_SCRIPT={script_name};"
        f"YADOF_2094_EVENT_HOURS={max(1, int(event_hours))};"
        f"YADOF_2094_DRY_RUN={1 if dry_run else 0};"
        f"YADOF_2094_TIMEOUT_SEC={int(script_timeout_sec)}"
    )
    lines = [
        "# Auto-generated by project.tools.submit_desktop2094_ansys_probe",
        "universe = vanilla",
        f"executable = {quote_atom(str(project_config.HTCONDOR_PYTHON_EXE))}",
        "initialdir = .",
        "getenv = False",
        f"arguments = {WORKFLOW_NAME}",
        f'environment = "{environment}"',
        f"load_profile = {bool(project_config.HTCONDOR_LOAD_PROFILE)}",
        f"run_as_owner = {bool(project_config.HTCONDOR_RUN_AS_OWNER)}",
        f"requirements = {requirements}",
        "should_transfer_files = YES",
        "when_to_transfer_output = ON_EXIT",
        "transfer_executable = False",
        (
            "transfer_input_files = "
            f"_appdata,_home,_localappdata,_tmp,{script_name},job_input.json,{WORKFLOW_NAME}"
        ),
        f"output = {STDOUT_NAME}",
        f"error = {STDERR_NAME}",
        f"log = {CONDOR_LOG_NAME}",
        "request_cpus = 1",
        "request_memory = 1GB",
        "request_disk = 1GB",
        "notification = never",
        "queue 1",
        "",
    ]
    (job_dir / SUBMIT_NAME).write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return job_dir


def submit_job(job_dir: Path) -> int:
    completed = subprocess.run(
        [str(project_config.HTCONDOR_SUBMIT_EXE), SUBMIT_NAME],
        cwd=str(job_dir),
        capture_output=True,
        text=True,
        check=False,
    )
    (job_dir / "condor_submit.stdout.txt").write_text(completed.stdout or "", encoding="utf-8", newline="\n")
    (job_dir / "condor_submit.stderr.txt").write_text(completed.stderr or "", encoding="utf-8", newline="\n")
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr or completed.stdout or f"condor_submit exited with {completed.returncode}")
    cluster_id = parse_cluster_id(completed.stdout or "")
    if cluster_id is None:
        raise RuntimeError(f"could not parse cluster id from: {completed.stdout}")
    (job_dir / "cluster.id").write_text(str(cluster_id), encoding="utf-8", newline="\n")
    return cluster_id


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
                with archive.open(member, "r") as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination)
    return sorted((path for path in raw_dir.iterdir() if path.is_file()), key=lambda path: path.name.lower())


def wait_job(job_dir: Path, timeout_sec: int) -> dict[str, object]:
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
            "status": str(individual.get("status") or ("done" if wait.returncode == 0 else "error")),
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


def slot_names(machine: str, count: int) -> tuple[str, ...]:
    return tuple(f"slot1_{idx}@{machine}" for idx in range(1, count + 1))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Submit DESKTOP-2094 ANSYS diagnostic or fix jobs through HTCondor.")
    parser.add_argument("action", choices=sorted(ACTION_SCRIPTS))
    parser.add_argument("--target-machine", default=TARGET_MACHINE)
    parser.add_argument("--slot", default="")
    parser.add_argument("--all-slots", action="store_true", help="Submit one job per slot1_N on the target machine.")
    parser.add_argument("--slot-count", type=int, default=12)
    parser.add_argument("--dry-run", action="store_true", help="For fix action, collect before/after intent without writing registry values.")
    parser.add_argument("--event-hours", type=int, default=24)
    parser.add_argument("--script-timeout-sec", type=int, default=1800)
    parser.add_argument("--wait-timeout-sec", type=int, default=2400)
    parser.add_argument("--no-wait", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    target_machine = str(args.target_machine)
    targets: tuple[str | None, ...]
    if args.all_slots:
        targets = slot_names(target_machine, max(1, int(args.slot_count)))
    else:
        targets = (str(args.slot).strip() or None,)

    job_dirs: list[Path] = []
    for target_slot in targets:
        job_dir = prepare_job(
            str(args.action),
            target_machine=target_machine,
            target_slot=target_slot,
            dry_run=bool(args.dry_run),
            event_hours=int(args.event_hours),
            script_timeout_sec=int(args.script_timeout_sec),
        )
        cluster_id = submit_job(job_dir)
        metadata = read_json(job_dir / "metadata.json")
        metadata.update({"condor_cluster_id": cluster_id, "condor_submitted_at": now_text()})
        write_json(job_dir / "metadata.json", metadata)
        write_json(job_dir / "metaData.json", metadata)
        print(f"submitted action={args.action} cluster={cluster_id} job_dir={job_dir}")
        job_dirs.append(job_dir)

    if args.no_wait:
        return 0

    status = 0
    for job_dir in job_dirs:
        metadata = wait_job(job_dir, max(60, int(args.wait_timeout_sec)))
        print(
            "finished "
            f"job_dir={job_dir} status={metadata.get('status')} "
            f"worker={metadata.get('worker_name')} whoami={metadata.get('runtime_whoami')} "
            f"reports={','.join(str(x) for x in metadata.get('raw_data_files', []))}"
        )
        if metadata.get("status") != "done":
            status = 1
    return status


if __name__ == "__main__":
    raise SystemExit(main())
