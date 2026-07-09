from __future__ import annotations

import argparse
import csv
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
COLLECTOR_SOURCE = THIS_FILE.with_name("collect_ansys_hash_inventory.ps1")
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from project import config_all as project_config  # noqa: E402


DEFAULT_MACHINES = ("DESKTOP-A2091", "DESKTOP-A2096")
WORKFLOW_NAME = "workflow.py"
COLLECTOR_NAME = "collect_ansys_hash_inventory.ps1"
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
COLLECTOR = BASE_DIR / "collect_ansys_hash_inventory.ps1"


def now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8", newline="\n")


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
    write_json(INDIVIDUAL_METADATA, {"status": "running", "started_at": started_at, **runtime_identity})
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
                "-OutputDir",
                str(RAW_DATA_DIR),
            ],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=1800,
            check=False,
        )
        (RAW_DATA_DIR / "collector.stdout.txt").write_text(
            completed.stdout or "", encoding="utf-8", newline="\n"
        )
        (RAW_DATA_DIR / "collector.stderr.txt").write_text(
            completed.stderr or "", encoding="utf-8", newline="\n"
        )
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
            metadata["error_message"] = f"hash collector exited with {completed.returncode}"
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


def machine_list(text: str) -> tuple[str, ...]:
    machines = tuple(item.strip() for item in text.split(",") if item.strip())
    return machines or DEFAULT_MACHINES


def new_job_dir(machine: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    label = re.sub(r"[^A-Za-z0-9_.-]+", "_", machine).lower()
    job_dir = Path(project_config.JOBS_DIR) / f"job_{stamp}_hashprobe_{label}"
    job_dir.mkdir(parents=True)
    return job_dir


def prepare_job(machine: str) -> Path:
    if not COLLECTOR_SOURCE.is_file():
        raise FileNotFoundError(COLLECTOR_SOURCE)
    job_dir = new_job_dir(machine)
    for name in ("._home", "._appdata", "._localappdata", "._tmp", RAW_DATA_DIR_NAME):
        (job_dir / name).mkdir()
    (job_dir / WORKFLOW_NAME).write_text(WORKFLOW_SOURCE, encoding="utf-8", newline="\n")
    shutil.copy2(COLLECTOR_SOURCE, job_dir / COLLECTOR_NAME)
    write_json(
        job_dir / "job_input.json",
        {
            "job_name": job_dir.name,
            "probe": "ansys_hash_inventory",
            "requested_machine": machine,
            "created_at": now_text(),
        },
    )
    metadata = {
        "job_name": job_dir.name,
        "status": "prepared",
        "engine": "htcondor",
        "probe": "ansys_hash_inventory",
        "requested_machine": machine,
        "created_at": now_text(),
    }
    write_json(job_dir / "metadata.json", metadata)
    write_json(job_dir / "metaData.json", metadata)

    requirements = f'{project_config.HTCONDOR_REQUIREMENTS} && (Machine =?= "{machine}")'
    environment = (
        "USERPROFILE=._home HOME=._home APPDATA=._appdata "
        "LOCALAPPDATA=._localappdata TEMP=._tmp TMP=._tmp"
    )
    lines = [
        "# Auto-generated by project.tools.submit_condor_ansys_hash_probe",
        "universe = vanilla",
        f"executable = {project_config.HTCONDOR_PYTHON_EXE}",
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
            "._appdata,._home,._localappdata,._tmp,"
            f"{COLLECTOR_NAME},job_input.json,{WORKFLOW_NAME}"
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


def load_hash_rows(job_dir: Path) -> dict[str, dict[str, str]]:
    path = job_dir / RAW_DATA_DIR_NAME / "ansys_install_hashes.csv"
    rows: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            key = str(row.get("relative_path") or "").replace("/", "\\").lower()
            if key:
                rows[key] = dict(row)
    return rows


def compare_jobs(job_dirs: dict[str, Path]) -> Path:
    machine_rows = {machine: load_hash_rows(job_dir) for machine, job_dir in job_dirs.items()}
    machines = tuple(machine_rows)
    all_paths = sorted(set().union(*(set(rows) for rows in machine_rows.values())))
    comparison: list[dict[str, object]] = []
    for path in all_paths:
        rows = {machine: machine_rows[machine].get(path) for machine in machines}
        present = [machine for machine, row in rows.items() if row is not None]
        hashes = {str(row.get("sha256") or "") for row in rows.values() if row is not None}
        lengths = {str(row.get("length") or "") for row in rows.values() if row is not None}
        versions = {str(row.get("file_version") or "") for row in rows.values() if row is not None}
        status = "identical"
        if len(present) != len(machines):
            status = "missing"
        elif len(hashes) > 1 or len(lengths) > 1:
            status = "hash_mismatch"
        elif len(versions) > 1:
            status = "version_text_mismatch"
        comparison.append(
            {
                "relative_path": path,
                "status": status,
                "machines": {
                    machine: (
                        None
                        if row is None
                        else {
                            "sha256": row.get("sha256"),
                            "length": row.get("length"),
                            "file_version": row.get("file_version"),
                            "product_version": row.get("product_version"),
                            "last_write_time": row.get("last_write_time"),
                        }
                    )
                    for machine, row in rows.items()
                },
            }
        )

    summaries = {
        machine: read_json(job_dir / RAW_DATA_DIR_NAME / "ansys_hash_summary.json")
        for machine, job_dir in job_dirs.items()
    }
    counts: dict[str, int] = {}
    for row in comparison:
        status = str(row["status"])
        counts[status] = counts.get(status, 0) + 1
    payload = {
        "generated_at": now_text(),
        "machines": list(machines),
        "counts": counts,
        "differences": [row for row in comparison if row["status"] != "identical"],
        "summaries": summaries,
        "job_directories": {machine: str(path) for machine, path in job_dirs.items()},
    }
    output = Path(project_config.JOBS_DIR) / f"ansys_hash_comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    write_json(output, payload)
    return output


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare Ansys binary hashes across HTCondor workers.")
    parser.add_argument("--machines", default=",".join(DEFAULT_MACHINES))
    parser.add_argument("--timeout-sec", type=int, default=1800)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    machines = machine_list(args.machines)
    jobs = {machine: prepare_job(machine) for machine in machines}
    clusters = {machine: submit_job(job_dir) for machine, job_dir in jobs.items()}
    for machine in machines:
        print(f"submitted machine={machine} cluster={clusters[machine]} job={jobs[machine]}")
    statuses = {machine: wait_job(jobs[machine], max(60, int(args.timeout_sec))) for machine in machines}
    for machine, metadata in statuses.items():
        print(
            f"completed machine={machine} status={metadata.get('status')} "
            f"worker={metadata.get('worker_name')}"
        )
    if any(metadata.get("status") != "done" for metadata in statuses.values()):
        return 1
    comparison = compare_jobs(jobs)
    print(f"comparison={comparison}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
