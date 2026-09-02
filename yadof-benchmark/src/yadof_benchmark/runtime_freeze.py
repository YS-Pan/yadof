"""Optional installed-code guard for a deliberately frozen experiment."""
from __future__ import annotations

import hashlib
from importlib import metadata
from pathlib import Path
import sys

from .benchmark_runtime.contracts import BenchmarkError
from .benchmark_runtime.storage import atomic_write_json, read_json


def installed_fingerprint():
    result = {}
    for name in ("yadof", "yadof-benchmark"):
        distribution = metadata.distribution(name)
        files = {}
        for relative in distribution.files or ():
            path = Path(distribution.locate_file(relative)).resolve()
            if path.suffix == ".pyc" or "__pycache__" in path.parts or path.name == "RECORD":
                continue
            if path.is_file():
                files[str(relative).replace("\\", "/")] = hashlib.sha256(path.read_bytes()).hexdigest()
        result[name] = {"version": distribution.version, "location": str(distribution.locate_file("")), "files": files}
    return {"python": sys.executable, "distributions": result}


def freeze_runtime(workspace, *, command, provenance):
    path = Path(workspace) / "runtime_lock.json"
    if path.exists():
        raise BenchmarkError("runtime lock already exists; use a fresh experiment workspace")
    atomic_write_json(path, {"installed": installed_fingerprint(), "inputs": input_fingerprint(Path(workspace)),
                             "command": list(command), "provenance": provenance})
    return path


def verify_runtime(workspace):
    root = Path(workspace)
    control = root / "benchmark_control.json"
    if control.is_file():
        config = read_json(control)
        if config.get("task_files") != task_fingerprint(root):
            raise BenchmarkError("task files changed during the frozen benchmark cell")
        root = Path(config["root"])
    path = root / "runtime_lock.json"
    if path.is_file():
        lock = read_json(path)
        if lock["installed"] != installed_fingerprint() or lock["inputs"] != input_fingerprint(root):
            raise BenchmarkError("installed package or experiment input fingerprint changed during the frozen benchmark")


def _hash_paths(root, paths):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(paths) if p.is_file() and "__pycache__" not in p.parts}


def input_fingerprint(root):
    return _hash_paths(root, [root / "benchmark.py", *root.joinpath("resources").rglob("*")])


def task_fingerprint(root):
    return _hash_paths(root, [root / "config.py", *root.joinpath("job_template").rglob("*"),
                              *root.joinpath("submit").rglob("*")])
