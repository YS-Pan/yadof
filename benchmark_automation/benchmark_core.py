"""Reproducible, resumable benchmark orchestration for the frozen yadof cases.

The runner treats task inputs as immutable content, gives every measured cell an
independent workspace, and delegates task execution to the installed ``yadof``
CLI.  Collection uses only documented public APIs and JSON CLI views.
"""

from __future__ import annotations

import contextlib
import dataclasses
import datetime as dt
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import os
import platform
import re
import shutil
import statistics
import subprocess
import sys
import threading
import time
import tomllib
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SCHEMA_VERSION = 1
RUNTIME_PATHS = (
    "jobs",
    "recorded_data",
    ".yadof/fast_scratch",
    ".yadof/surrogate/checkpoints",
    ".yadof/optimization/active.json",
    ".yadof/campaign.lock",
    ".yadof/logs",
)
TERMINAL_CELL_STATES = {"completed", "failed", "skipped"}
CONFIG_BLOCK_START = "# >>> benchmark_automation managed overrides >>>"
CONFIG_BLOCK_END = "# <<< benchmark_automation managed overrides <<<"
BASELINE_PROVIDER_PATTERN = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
BASELINE_ID_PATTERN = re.compile(
    r"(?P<task>[a-z][a-z0-9]*(?:-[a-z0-9]+)*)-(?P<fingerprint>[0-9a-f]{12})\Z"
)


class BenchmarkError(RuntimeError):
    """User-facing benchmark contract violation."""


@dataclasses.dataclass(frozen=True)
class Paths:
    root: Path
    config: Path
    runs: Path
    strategies: Path
    histories: Path


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def object_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path: Path, value: object) -> None:
    """Atomically replace a derived JSON index or mutable state file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    payload = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    with temporary.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def atomic_write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def write_new_json(path: Path, value: object) -> None:
    """Create immutable JSON evidence and refuse accidental replacement."""

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(payload)


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise BenchmarkError(f"expected a JSON object in {path}")
    return value


def _baseline_identity(
    paths: Paths,
    baseline: Path,
    manifest: Mapping[str, Any],
    case_id: str,
) -> dict[str, str]:
    layout = "baselines/<provider>/<task>-<12-hex-fingerprint-prefix>"
    try:
        relative = baseline.resolve().relative_to((paths.root / "baselines").resolve())
    except ValueError as exc:
        raise BenchmarkError(f"case {case_id!r} baseline must use {layout}") from exc
    if len(relative.parts) != 2:
        raise BenchmarkError(f"case {case_id!r} baseline must use {layout}")
    provider_id, baseline_id = relative.parts
    match = BASELINE_ID_PATTERN.fullmatch(baseline_id)
    if BASELINE_PROVIDER_PATTERN.fullmatch(provider_id) is None or match is None:
        raise BenchmarkError(f"case {case_id!r} baseline must use {layout}")

    task_id = match.group("task")
    fingerprint_prefix = match.group("fingerprint")
    task_fingerprint = manifest.get("task_fingerprint")
    if (
        not isinstance(task_fingerprint, str)
        or re.fullmatch(r"[0-9a-f]{64}", task_fingerprint) is None
    ):
        raise BenchmarkError(f"case {case_id!r} baseline has an invalid task_fingerprint")
    expected = {
        "baseline_id": baseline_id,
        "case_id": case_id,
        "provider_id": provider_id,
        "task_id": task_id,
    }
    for field, value in expected.items():
        if manifest.get(field) != value:
            raise BenchmarkError(
                f"case {case_id!r} baseline metadata {field} must be {value!r}"
            )
    if not task_fingerprint.startswith(fingerprint_prefix):
        raise BenchmarkError(
            f"case {case_id!r} baseline directory fingerprint prefix does not match task_fingerprint"
        )
    return {
        "provider_id": provider_id,
        "task_id": task_id,
        "fingerprint_prefix": fingerprint_prefix,
    }


def resolve_inside(root: Path, value: str | Path, *, label: str) -> Path:
    root = root.resolve()
    candidate = (root / value).resolve() if not Path(value).is_absolute() else Path(value).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise BenchmarkError(f"{label} escapes benchmark root: {value}") from exc
    return candidate


def resolve_runs_dir(
    benchmark_root: Path,
    configured_value: str | Path,
    *,
    override: str | Path | None = None,
    invocation_cwd: Path | None = None,
) -> Path:
    """Resolve mutable run output without weakening immutable-input containment."""

    if override is None:
        base = benchmark_root.resolve()
        value = Path(configured_value)
    else:
        base = (invocation_cwd or Path.cwd()).resolve()
        value = Path(override)
    value = value.expanduser()
    return value.resolve() if value.is_absolute() else (base / value).resolve()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _paths_overlap(left: Path, right: Path) -> bool:
    return _is_within(left, right) or _is_within(right, left)


def _existing_disk_root(path: Path) -> Path:
    candidate = path.resolve()
    while not candidate.exists():
        parent = candidate.parent
        if parent == candidate:
            raise BenchmarkError(f"cannot find an existing parent for runs_dir: {path}")
        candidate = parent
    return candidate


def _declared_files(workspace: Path, include_paths: Sequence[str]) -> list[Path]:
    workspace = workspace.resolve()
    files: list[Path] = []
    seen: set[Path] = set()
    for raw in include_paths:
        target = resolve_inside(workspace, raw, label="declared input")
        if not target.exists():
            raise BenchmarkError(f"declared input does not exist: {target}")
        candidates = [target] if target.is_file() else sorted(
            (path for path in target.rglob("*") if path.is_file()),
            key=lambda path: path.as_posix().casefold(),
        )
        for path in candidates:
            resolved = path.resolve()
            try:
                resolved.relative_to(workspace)
            except ValueError as exc:
                raise BenchmarkError(f"declared input resolves outside workspace: {path}") from exc
            if resolved not in seen:
                seen.add(resolved)
                files.append(resolved)
    return sorted(files, key=lambda path: path.as_posix().casefold())


def task_manifest(workspace: Path, include_paths: Sequence[str]) -> list[dict[str, str]]:
    workspace = workspace.resolve()
    return [
        {
            "path": path.relative_to(workspace).as_posix(),
            "sha256": file_sha256(path),
        }
        for path in _declared_files(workspace, include_paths)
    ]


def task_fingerprint(workspace: Path, include_paths: Sequence[str]) -> str:
    """Match the frozen-baseline path-tab-file-hash manifest algorithm."""

    lines = [f"{entry['path']}\t{entry['sha256']}" for entry in task_manifest(workspace, include_paths)]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def directory_manifest(root: Path) -> list[dict[str, str]]:
    root = root.resolve()
    if not root.is_dir():
        raise BenchmarkError(f"directory does not exist: {root}")
    files = sorted(
        (path.resolve() for path in root.rglob("*") if path.is_file()),
        key=lambda path: path.as_posix().casefold(),
    )
    return [
        {"path": path.relative_to(root).as_posix(), "sha256": file_sha256(path)}
        for path in files
    ]


def directory_fingerprint(root: Path) -> str:
    manifest = directory_manifest(root)
    lines = [f"{item['path']}\t{item['sha256']}" for item in manifest]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _load_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as stream:
            value = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise BenchmarkError(f"cannot load benchmark config {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise BenchmarkError("benchmark config root must be a table")
    return value


def load_config(
    config_path: Path,
    *,
    runs_dir_override: str | Path | None = None,
    invocation_cwd: Path | None = None,
) -> tuple[dict[str, Any], Paths]:
    config_path = config_path.resolve()
    root = config_path.parent
    config = _load_toml(config_path)
    if config.get("schema_version") != SCHEMA_VERSION:
        raise BenchmarkError(
            f"unsupported benchmark schema_version {config.get('schema_version')!r}; "
            f"expected {SCHEMA_VERSION}"
        )
    runner = config.get("runner")
    if not isinstance(runner, dict):
        raise BenchmarkError("missing [runner] table")
    paths = Paths(
        root=root,
        config=config_path,
        runs=resolve_runs_dir(
            root,
            str(runner.get("runs_dir", "runs")),
            override=runs_dir_override,
            invocation_cwd=invocation_cwd,
        ),
        strategies=resolve_inside(
            root,
            str(runner.get("strategy_template_dir", "strategy_templates")),
            label="strategy_template_dir",
        ),
        histories=resolve_inside(
            root,
            str(runner.get("history_snapshot_dir", "history_snapshots")),
            label="history_snapshot_dir",
        ),
    )
    validate_config(config, paths)
    return config, paths


def validate_config(config: Mapping[str, Any], paths: Paths) -> None:
    runner = config.get("runner", {})
    cases = config.get("cases")
    arms = config.get("arms")
    suites = config.get("suites")
    budgets = config.get("budgets")
    if not all(isinstance(item, dict) for item in (cases, arms, suites, budgets)):
        raise BenchmarkError("config requires [cases], [arms], [suites], and [budgets]")
    assert isinstance(runner, dict)
    assert isinstance(cases, dict) and isinstance(arms, dict)
    assert isinstance(suites, dict) and isinstance(budgets, dict)
    _config_overrides(
        runner.get("measured_config_overrides", {}),
        label="runner measured_config_overrides",
    )
    if paths.runs.exists() and not paths.runs.is_dir():
        raise BenchmarkError(f"runs_dir is not a directory: {paths.runs}")
    if paths.runs == paths.root or _is_within(paths.root, paths.runs):
        raise BenchmarkError("runs_dir must not be the benchmark root or contain it")
    for label, protected in (
        ("strategy_template_dir", paths.strategies),
        ("history_snapshot_dir", paths.histories),
    ):
        if _paths_overlap(paths.runs, protected):
            raise BenchmarkError(f"runs_dir overlaps {label}: {protected}")
    for case_id, case in cases.items():
        if not isinstance(case, dict):
            raise BenchmarkError(f"case {case_id!r} must be a table")
        baseline = resolve_inside(paths.root, str(case.get("baseline", "")), label=f"case {case_id} baseline")
        if _paths_overlap(paths.runs, baseline):
            raise BenchmarkError(f"runs_dir overlaps case {case_id!r} baseline: {baseline}")
        if not (baseline / "baseline.json").is_file() or not (baseline / "workspace").is_dir():
            raise BenchmarkError(f"case {case_id!r} baseline is incomplete: {baseline}")
        _baseline_identity(paths, baseline, read_json(baseline / "baseline.json"), case_id)
        include = case.get("include_paths")
        if not isinstance(include, list) or not include or not all(isinstance(x, str) for x in include):
            raise BenchmarkError(f"case {case_id!r} include_paths must be a non-empty string list")
        policy = case.get("history_policy")
        if policy not in {"empty", "snapshot"}:
            raise BenchmarkError(f"case {case_id!r} history_policy must be empty or snapshot")
        if policy == "snapshot":
            snapshot = resolve_inside(paths.histories, str(case.get("history_snapshot", "")), label="history snapshot")
            if not snapshot.is_dir():
                raise BenchmarkError(f"history snapshot does not exist: {snapshot}")
    for arm_id, arm in arms.items():
        if not isinstance(arm, dict):
            raise BenchmarkError(f"arm {arm_id!r} must be a table")
        template = resolve_inside(paths.strategies, str(arm.get("strategy_template", "")), label=f"arm {arm_id} template")
        if not template.is_file():
            raise BenchmarkError(f"strategy template does not exist: {template}")
        _config_overrides(
            arm.get("config_overrides", {}),
            label=f"arm {arm_id} config_overrides",
        )
    for suite_id, suite in suites.items():
        if not isinstance(suite, dict):
            raise BenchmarkError(f"suite {suite_id!r} must be a table")
        purpose = suite.get("purpose")
        if purpose not in {"structural", "performance"}:
            raise BenchmarkError(f"suite {suite_id!r} purpose must be structural or performance")
        suite_cases = suite.get("cases", [])
        suite_arms = suite.get("arms", [])
        seeds = suite.get("seeds", [])
        if not suite_cases or not all(case in cases for case in suite_cases):
            raise BenchmarkError(f"suite {suite_id!r} names an unknown or empty case set")
        if not all(arm in arms for arm in suite_arms):
            raise BenchmarkError(f"suite {suite_id!r} names an unknown arm")
        if not seeds or not all(isinstance(seed, int) and seed >= 0 for seed in seeds):
            raise BenchmarkError(f"suite {suite_id!r} seeds must be non-negative integers")
        smoke_only = bool(suite.get("smoke_only", False))
        if smoke_only and suite_arms:
            raise BenchmarkError(f"suite {suite_id!r} smoke_only suite must have no arms")
        if not smoke_only:
            suite_budget = budgets.get(suite_id)
            if not isinstance(suite_budget, dict):
                raise BenchmarkError(f"suite {suite_id!r} has no budget table")
            for case_id in suite_cases:
                case_budget = suite_budget.get(case_id)
                if not isinstance(case_budget, dict):
                    raise BenchmarkError(f"suite {suite_id!r} case {case_id!r} has no budget")
                attempted_by_arm: list[int] = []
                for arm_id in suite_arms:
                    budget = case_budget.get(arm_id)
                    if not isinstance(budget, dict):
                        raise BenchmarkError(
                            f"suite {suite_id!r} case {case_id!r} arm {arm_id!r} has no budget"
                        )
                    pop = budget.get("population")
                    generations = budget.get("generations")
                    maximum = budget.get("max_generations", generations)
                    if not all(isinstance(x, int) and x > 0 for x in (pop, generations, maximum)):
                        raise BenchmarkError(f"invalid positive integer budget for {suite_id}/{case_id}/{arm_id}")
                    if maximum < generations:
                        raise BenchmarkError(f"max_generations is below generations for {suite_id}/{case_id}/{arm_id}")
                    attempted_by_arm.append(int(pop) * int(generations))
                if purpose == "performance" and len(set(attempted_by_arm)) > 1:
                    raise BenchmarkError(
                        f"performance suite {suite_id!r} case {case_id!r} has unequal planned attempted budgets"
                    )


def _safe_id(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-._")
    return cleaned or "run"


def _config_overrides(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise BenchmarkError(f"{label} must be a table")
    overrides = dict(value)
    for key in overrides:
        if not isinstance(key, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            raise BenchmarkError(f"unsafe config override name in {label}: {key!r}")
    return overrides


def _cell_id(case_id: str, arm_id: str | None, seed: int, *, kind: str) -> str:
    if kind == "smoke":
        return _safe_id(f"smoke__{case_id}__seed-{seed}")
    return _safe_id(f"{case_id}__{arm_id}__seed-{seed}")


def _select_values(
    allowed: Sequence[Any], requested: Sequence[Any] | None, *, label: str
) -> list[Any]:
    if requested is None:
        return list(allowed)
    unknown = [value for value in requested if value not in allowed]
    if unknown:
        raise BenchmarkError(
            f"unknown {label} selection(s) {unknown!r}; allowed: {list(allowed)!r}"
        )
    requested_set = set(requested)
    selected = [value for value in allowed if value in requested_set]
    if not selected:
        raise BenchmarkError(f"{label} selection is empty")
    return selected


def _planned_commands(
    config: Mapping[str, Any], cell: Mapping[str, Any]
) -> list[list[str]]:
    python = str(Path(sys.executable).resolve())
    workspace = f"<run-root>/cells/{cell['cell_id']}/attempts/<attempt>/workspace"
    commands = [[python, "-m", "yadof", "init", workspace]]
    commands.append([python, "-m", "yadof", "check", "--workspace", workspace])
    case = config["cases"][cell["case"]]
    if cell["kind"] == "smoke":
        commands.append(
            [
                python,
                "-m",
                "yadof",
                "smoke-test",
                "--workspace",
                workspace,
                "--mode",
                str(case["mode"]),
                "--real-task",
            ]
        )
        return commands
    commands.append(
        [
            python,
            "-m",
            "yadof",
            "run",
            "--workspace",
            workspace,
            "--generations",
            str(cell["generations"]),
            "--start-generation",
            "0",
            "--mode",
            str(case["mode"]),
            "--population-size",
            str(cell["population"]),
            "--random-seed",
            str(cell["seed"]),
            "--no-smoke-test",
            "--no-progress",
            "--fail-on-all-infinite",
        ]
    )
    if int(cell["max_generations"]) > int(cell["generations"]):
        commands.append(
            [
                python,
                "-m",
                "yadof",
                "run",
                "--workspace",
                workspace,
                "--generations",
                str(int(cell["max_generations"]) - int(cell["generations"])),
                "--start-generation",
                str(cell["generations"]),
                "--mode",
                str(case["mode"]),
                "--population-size",
                str(cell["population"]),
                "--random-seed",
                str(cell["seed"]),
                "--no-smoke-test",
                "--no-progress",
                "--fail-on-all-infinite",
            ]
        )
    return commands


def build_plan(
    config: Mapping[str, Any],
    paths: Paths,
    suite_id: str,
    *,
    case_ids: Sequence[str] | None = None,
    arm_ids: Sequence[str] | None = None,
    seeds: Sequence[int] | None = None,
) -> dict[str, Any]:
    suites = config["suites"]
    if suite_id not in suites:
        raise BenchmarkError(f"unknown suite {suite_id!r}; choose from {', '.join(sorted(suites))}")
    suite = suites[suite_id]
    selected_cases = _select_values(suite["cases"], case_ids, label="case")
    selected_arms = _select_values(suite.get("arms", []), arm_ids, label="arm") if suite.get("arms") else []
    if arm_ids and not suite.get("arms"):
        raise BenchmarkError(f"suite {suite_id!r} has no measured arms to filter")
    selected_seeds = [int(seed) for seed in _select_values(suite["seeds"], seeds, label="seed")]
    cells: list[dict[str, Any]] = []
    if bool(suite.get("smoke", False)):
        for case_id in selected_cases:
            seed = selected_seeds[0]
            cells.append(
                {
                    "cell_id": _cell_id(case_id, None, seed, kind="smoke"),
                    "kind": "smoke",
                    "case": case_id,
                    "arm": None,
                    "seed": seed,
                    "population": 1,
                    "generations": 0,
                    "max_generations": 0,
                    "planned_attempted_evaluations": 1,
                    "disposable": True,
                }
            )
    if not bool(suite.get("smoke_only", False)):
        budgets = config["budgets"][suite_id]
        for case_id in selected_cases:
            for seed in selected_seeds:
                for arm_id in selected_arms:
                    budget = budgets[case_id][arm_id]
                    population = int(budget["population"])
                    generations = int(budget["generations"])
                    cells.append(
                        {
                            "cell_id": _cell_id(case_id, arm_id, seed, kind="measured"),
                            "kind": "measured",
                            "case": case_id,
                            "arm": arm_id,
                            "seed": seed,
                            "population": population,
                            "generations": generations,
                            "max_generations": int(budget.get("max_generations", generations)),
                            "planned_attempted_evaluations": population * generations,
                            "disposable": False,
                        }
                    )
    for cell in cells:
        cell["planned_commands"] = _planned_commands(config, cell)
    estimated_eval_sec = 0.0
    estimated_storage_mib = 0.0
    for cell in cells:
        case = config["cases"][cell["case"]]
        workers = max(1, int(case.get("max_workers", 1)))
        estimated_eval_sec += (
            float(case.get("observed_eval_sec", 0.0))
            * int(cell["planned_attempted_evaluations"])
            / workers
        )
        estimated_storage_mib += float(case.get("estimated_record_mib", 0.0)) * int(
            cell["planned_attempted_evaluations"]
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "suite": suite_id,
        "purpose": suite["purpose"],
        "fail_fast": bool(suite.get("fail_fast", suite["purpose"] == "structural")),
        "smoke_is_disposable": True,
        "selection": {
            "cases": selected_cases,
            "arms": selected_arms,
            "seeds": selected_seeds,
        },
        "cell_count": len(cells),
        "cells": cells,
        "estimates": {
            "evaluation_wall_lower_bound_sec": estimated_eval_sec,
            "record_storage_mib": estimated_storage_mib,
            "scope_note": "Task evaluation estimate excludes optimizer and surrogate training overhead.",
        },
        "prerequisites": {
            case_id: dict(config["cases"][case_id].get("resource", {}))
            for case_id in selected_cases
        },
    }


def _package_identity() -> dict[str, Any]:
    import yadof
    origin = Path(yadof.__file__).resolve()
    identity: dict[str, Any] = {
        "version": str(getattr(yadof, "__version__", "unknown")),
        "origin": str(origin),
        "module_sha256": file_sha256(origin),
        "python": str(Path(sys.executable).resolve()),
        "python_version": sys.version,
    }
    with contextlib.suppress(importlib.metadata.PackageNotFoundError, OSError):
        distribution = importlib.metadata.distribution("yadof")
        identity["distribution_name"] = distribution.metadata.get("Name", "yadof")
        identity["distribution_version"] = distribution.version
        record = next(
            (
                Path(distribution.locate_file(file)).resolve()
                for file in (distribution.files or ())
                if str(file).replace("\\", "/").endswith(".dist-info/RECORD")
            ),
            None,
        )
        if record is not None and record.is_file():
            identity["distribution_record"] = str(record)
            identity["distribution_record_sha256"] = file_sha256(record)
    return identity


def _baseline_details(config: Mapping[str, Any], paths: Paths, case_id: str) -> dict[str, Any]:
    case = config["cases"][case_id]
    root = resolve_inside(paths.root, case["baseline"], label=f"case {case_id} baseline")
    manifest = read_json(root / "baseline.json")
    workspace = root / "workspace"
    actual = task_fingerprint(workspace, case["include_paths"])
    runtime_paths = [relative for relative in RUNTIME_PATHS if (workspace / relative).exists()]
    identity = _baseline_identity(paths, root, manifest, case_id)
    return {
        "root": str(root),
        "workspace": str(workspace),
        "baseline_id": manifest.get("baseline_id"),
        "yadof_version": manifest.get("yadof_version"),
        "expected_task_fingerprint": manifest.get("task_fingerprint"),
        "actual_task_fingerprint": actual,
        "task_file_count": len(task_manifest(workspace, case["include_paths"])),
        "fingerprint_matches": actual == manifest.get("task_fingerprint"),
        "runtime_paths_present": runtime_paths,
        "runtime_clean": not runtime_paths,
        "include_paths": list(case["include_paths"]),
        **identity,
    }


def _strategy_details(config: Mapping[str, Any], paths: Paths, arm_id: str) -> dict[str, Any]:
    arm = config["arms"][arm_id]
    template = resolve_inside(paths.strategies, arm["strategy_template"], label=f"arm {arm_id} template")
    module_name = f"benchmark_strategy_{_safe_id(arm_id).replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, template)
    if spec is None or spec.loader is None:
        raise BenchmarkError(f"cannot load strategy template: {template}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    builder = getattr(module, "build_optimization", None)
    if not callable(builder):
        raise BenchmarkError(f"strategy {template} has no callable build_optimization")
    strategy = builder()
    return {
        "template": str(template),
        "sha256": file_sha256(template),
        "constructed_type": f"{type(strategy).__module__}.{type(strategy).__qualname__}",
        "surrogate": bool(arm.get("surrogate", False)),
        "config_overrides": _config_overrides(
            arm.get("config_overrides", {}),
            label=f"arm {arm_id} config_overrides",
        ),
    }


def _run_read_only(command: Sequence[str], *, cwd: Path, timeout: int) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = subprocess.run(
            list(command),
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return {
            "command": list(command),
            "returncode": result.returncode,
            "duration_sec": time.perf_counter() - started,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": list(command),
            "returncode": None,
            "duration_sec": time.perf_counter() - started,
            "stdout": (exc.stdout or "") if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "") if isinstance(exc.stderr, str) else "",
            "error": f"timed out after {timeout} seconds",
        }


def preflight(
    config: Mapping[str, Any],
    paths: Paths,
    suite_id: str,
    *,
    case_ids: Sequence[str] | None = None,
    arm_ids: Sequence[str] | None = None,
    seeds: Sequence[int] | None = None,
) -> dict[str, Any]:
    plan = build_plan(
        config,
        paths,
        suite_id,
        case_ids=case_ids,
        arm_ids=arm_ids,
        seeds=seeds,
    )
    identity = _package_identity()
    checks: list[dict[str, Any]] = []
    baseline_map: dict[str, Any] = {}
    strategy_map: dict[str, Any] = {}
    resource_map: dict[str, Any] = {}
    for case_id in plan["selection"]["cases"]:
        try:
            details = _baseline_details(config, paths, case_id)
            baseline_map[case_id] = details
            version_ok = details["yadof_version"] == identity["version"]
            checks.append(
                {
                    "name": f"baseline:{case_id}",
                    "ok": bool(
                        details["fingerprint_matches"]
                        and details["runtime_clean"]
                        and version_ok
                    ),
                    "details": details,
                    "error": (
                        None
                        if version_ok
                        and details["runtime_clean"]
                        and details["fingerprint_matches"]
                        else "baseline fingerprint/version differs or mutable runtime paths are present"
                    ),
                }
            )
            result = _run_read_only(
                [identity["python"], "-m", "yadof", "check", "--workspace", details["workspace"]],
                cwd=paths.root,
                timeout=300,
            )
            checks.append(
                {
                    "name": f"yadof-check:{case_id}",
                    "ok": result["returncode"] == 0,
                    "details": result,
                }
            )
        except Exception as exc:
            checks.append({"name": f"baseline:{case_id}", "ok": False, "error": str(exc)})
        resource = config["cases"][case_id].get("resource", {})
        kind = resource.get("kind")
        if kind == "environment_executable":
            variable = str(resource.get("variable", ""))
            value = os.environ.get(variable)
            exists = bool(value and Path(value).is_file())
            checks.append(
                {
                    "name": f"resource:{case_id}",
                    "ok": exists,
                    "details": {"kind": kind, "variable": variable, "value": value, "exists": exists},
                }
            )
            resource_map[case_id] = checks[-1]["details"]
        elif kind == "cuda":
            try:
                import torch

                available = bool(torch.cuda.is_available())
                details = {
                    "kind": "cuda",
                    "torch_version": str(torch.__version__),
                    "available": available,
                    "device": torch.cuda.get_device_name(0) if available else None,
                }
                checks.append({"name": f"resource:{case_id}", "ok": available, "details": details})
                resource_map[case_id] = details
            except Exception as exc:
                checks.append({"name": f"resource:{case_id}", "ok": False, "error": str(exc)})
    for arm_id in plan["selection"]["arms"]:
        try:
            strategy_map[arm_id] = _strategy_details(config, paths, arm_id)
            checks.append({"name": f"strategy:{arm_id}", "ok": True, "details": strategy_map[arm_id]})
        except Exception as exc:
            checks.append({"name": f"strategy:{arm_id}", "ok": False, "error": str(exc)})
    runner = config["runner"]
    disk_root = _existing_disk_root(paths.runs)
    free_mib = shutil.disk_usage(disk_root).free / (1024 * 1024)
    required_mib = max(
        float(runner.get("minimum_free_disk_mib", 0)),
        float(plan["estimates"]["record_storage_mib"]) * 2.0,
    )
    checks.append(
        {
            "name": "disk-space",
            "ok": free_mib >= required_mib,
            "details": {"free_mib": free_mib, "required_mib": required_mib, "path": str(disk_root)},
        }
    )
    installed_distribution_ok = bool(identity.get("distribution_record_sha256")) and (
        identity.get("distribution_version") == identity.get("version")
    )
    checks.append(
        {
            "name": "python-environment",
            "ok": installed_distribution_ok,
            "details": identity,
            "error": (
                None
                if installed_distribution_ok
                else "yadof must be an installed distribution with matching metadata and RECORD"
            ),
        }
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "suite": suite_id,
        "ok": all(bool(check.get("ok")) for check in checks),
        "checked_utc": utc_now(),
        "host": {"node": platform.node(), "platform": platform.platform()},
        "package": identity,
        "plan": plan,
        "baselines": baseline_map,
        "strategies": strategy_map,
        "resources": resource_map,
        "checks": checks,
    }


def build_run_spec(
    config: Mapping[str, Any],
    paths: Paths,
    suite_id: str,
    preflight_result: Mapping[str, Any],
    *,
    label: str | None = None,
) -> dict[str, Any]:
    if not preflight_result.get("ok"):
        raise BenchmarkError("preflight failed; no run directory was created")
    plan = dict(preflight_result["plan"])
    suite = config["suites"][suite_id]
    cases: dict[str, Any] = {}
    for case_id in plan["selection"]["cases"]:
        case = config["cases"][case_id]
        baseline = dict(preflight_result["baselines"][case_id])
        if case["history_policy"] == "empty":
            starting_evidence = {
                "policy": "empty",
                "snapshot": None,
                "fingerprint": object_sha256({"policy": "empty", "rows": 0, "checkpoints": 0}),
                "file_count": 0,
            }
        else:
            snapshot = resolve_inside(
                paths.histories,
                case["history_snapshot"],
                label=f"case {case_id} history snapshot",
            )
            manifest = directory_manifest(snapshot)
            starting_evidence = {
                "policy": "snapshot",
                "snapshot": str(snapshot),
                "fingerprint": directory_fingerprint(snapshot),
                "file_count": len(manifest),
                "manifest": manifest,
            }
        cases[case_id] = {
            "baseline": baseline,
            "mode": case["mode"],
            "history_policy": case["history_policy"],
            "history_snapshot": case.get("history_snapshot"),
            "starting_evidence": starting_evidence,
            "expected_objectives": int(case["expected_objectives"]),
            "rawdata_shapes": dict(case.get("rawdata_shapes", {})),
            "max_workers": int(case.get("max_workers", 1)),
            "representative_expensive_generation_sec": case.get(
                "representative_expensive_generation_sec"
            ),
            "resource": dict(case.get("resource", {})),
            "resolved_resource": dict(preflight_result.get("resources", {}).get(case_id, {})),
        }
    arms = {
        arm_id: dict(preflight_result["strategies"][arm_id])
        for arm_id in plan["selection"]["arms"]
    }
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_utc": utc_now(),
        "suite": suite_id,
        "purpose": suite["purpose"],
        "label": label,
        "config": {
            "path": str(paths.config),
            "sha256": file_sha256(paths.config),
        },
        "package": dict(preflight_result["package"]),
        "host": dict(preflight_result["host"]),
        "automation": {
            "core": {
                "path": str(Path(__file__).resolve()),
                "sha256": file_sha256(Path(__file__).resolve()),
            },
            "entrypoint": {
                "path": str(Path(__file__).resolve().with_name("benchmark.py")),
                "sha256": file_sha256(Path(__file__).resolve().with_name("benchmark.py")),
            },
        },
        "runner": {
            "command_timeout_sec": int(config["runner"].get("command_timeout_sec", 7200)),
            "audit_sample_percent": int(config["runner"].get("audit_sample_percent", 10)),
            "audit_random_seed": int(config["runner"].get("audit_random_seed", 0)),
            "fail_fast": bool(plan["fail_fast"]),
            "measured_config_overrides": _config_overrides(
                config["runner"].get("measured_config_overrides", {}),
                label="runner measured_config_overrides",
            ),
        },
        "cases": cases,
        "arms": arms,
        "plan": plan,
    }
    payload["spec_sha256"] = object_sha256(payload)
    return payload


def make_run_id(spec: Mapping[str, Any], label: str | None = None) -> str:
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    suffix = str(spec["spec_sha256"])[:12]
    middle = f"-{_safe_id(label)}" if label else ""
    return f"{stamp}{middle}-{suffix}"


def _initial_state(run_id: str, spec: Mapping[str, Any]) -> dict[str, Any]:
    now = utc_now()
    cells = {
        cell["cell_id"]: {
            "status": "pending",
            "kind": cell["kind"],
            "case": cell["case"],
            "arm": cell["arm"],
            "seed": cell["seed"],
            "attempts": [],
        }
        for cell in spec["plan"]["cells"]
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "spec_sha256": spec["spec_sha256"],
        "status": "pending",
        "created_utc": now,
        "updated_utc": now,
        "cells": cells,
        "events": [{"at": now, "event": "run-created"}],
    }


def create_run(paths: Paths, spec: Mapping[str, Any], *, run_id: str | None = None) -> tuple[str, Path]:
    chosen = _safe_id(run_id) if run_id else make_run_id(spec, spec.get("label"))
    run_root = resolve_inside(paths.runs, chosen, label="run_id")
    if run_root.exists():
        raise BenchmarkError(f"run already exists: {chosen}")
    run_root.mkdir(parents=True)
    write_new_json(run_root / "run_spec.json", spec)
    write_new_json(run_root / "matrix.json", spec["plan"])
    atomic_write_json(run_root / "run_state.json", _initial_state(chosen, spec))
    return chosen, run_root


def load_run(paths: Paths, run_id: str) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    run_root = resolve_inside(paths.runs, run_id, label="run_id")
    spec_path = run_root / "run_spec.json"
    state_path = run_root / "run_state.json"
    if not spec_path.is_file() or not state_path.is_file():
        raise BenchmarkError(f"run {run_id!r} does not contain run_spec.json and run_state.json")
    spec = read_json(spec_path)
    state = read_json(state_path)
    expected = spec.get("spec_sha256")
    without_hash = dict(spec)
    without_hash.pop("spec_sha256", None)
    actual = object_sha256(without_hash)
    if expected != actual:
        raise BenchmarkError(f"immutable run_spec.json fingerprint mismatch: expected {expected}, got {actual}")
    if state.get("spec_sha256") != expected:
        raise BenchmarkError("run_state.json refers to a different run spec")
    return run_root, spec, state


def verify_run_inputs(
    paths: Paths,
    spec: Mapping[str, Any],
    *,
    verify_automation: bool = True,
    verify_config: bool = True,
) -> None:
    """Refuse resume when any immutable selected input or installation drifts."""

    if verify_config and file_sha256(paths.config) != spec["config"]["sha256"]:
        raise BenchmarkError("benchmark.toml fingerprint changed since run creation")
    if verify_automation:
        for name, item in spec.get("automation", {}).items():
            if file_sha256(Path(item["path"])) != item["sha256"]:
                raise BenchmarkError(f"benchmark automation fingerprint drift for {name}")
    current_package = _package_identity()
    for key in ("version", "origin", "module_sha256", "python"):
        if current_package.get(key) != spec["package"].get(key):
            raise BenchmarkError(f"installed package identity drift for {key}")
    for case_id, case in spec["cases"].items():
        baseline = case["baseline"]
        actual = task_fingerprint(Path(baseline["workspace"]), baseline["include_paths"])
        if actual != baseline["actual_task_fingerprint"]:
            raise BenchmarkError(f"baseline task fingerprint drift for {case_id}")
        starting = case["starting_evidence"]
        if starting["policy"] == "snapshot":
            actual_history = directory_fingerprint(Path(starting["snapshot"]))
            if actual_history != starting["fingerprint"]:
                raise BenchmarkError(f"history snapshot fingerprint drift for {case_id}")
    for arm_id, arm in spec["arms"].items():
        if file_sha256(Path(arm["template"])) != arm["sha256"]:
            raise BenchmarkError(f"strategy template fingerprint drift for {arm_id}")


def _save_state(run_root: Path, state: dict[str, Any], *, event: str | None = None, **details: Any) -> None:
    now = utc_now()
    state["updated_utc"] = now
    if event:
        state.setdefault("events", []).append({"at": now, "event": event, **details})
    atomic_write_json(run_root / "run_state.json", state)


def _copy_declared_inputs(source: Path, destination: Path, include_paths: Sequence[str]) -> None:
    """Populate only declared task inputs into a freshly initialized workspace."""

    if not destination.is_dir():
        raise BenchmarkError(f"fresh yadof workspace does not exist: {destination}")
    for raw in include_paths:
        src = resolve_inside(source, raw, label="baseline input")
        dst = resolve_inside(destination, raw, label="cell input")
        if dst.is_dir():
            shutil.rmtree(dst)
        elif dst.exists():
            dst.unlink()
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)


def _apply_config_overrides(config_path: Path, overrides: Mapping[str, Any]) -> None:
    current = config_path.read_text(encoding="utf-8")
    if CONFIG_BLOCK_START in current or CONFIG_BLOCK_END in current:
        raise BenchmarkError(f"managed config override block already exists in {config_path}")
    checked = _config_overrides(overrides, label="managed config overrides")
    lines = ["", CONFIG_BLOCK_START]
    for key in sorted(checked):
        lines.append(f"{key} = {checked[key]!r}")
    lines.extend([CONFIG_BLOCK_END, ""])
    with config_path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join(lines))


def _copy_history_snapshot(snapshot: Path, workspace: Path) -> None:
    for source in sorted(snapshot.rglob("*"), key=lambda path: path.as_posix().casefold()):
        relative = source.relative_to(snapshot)
        destination = workspace / relative
        if source.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        elif source.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)


def _attempt_directory(run_root: Path, cell_id: str, attempt_number: int) -> Path:
    return run_root / "cells" / cell_id / "attempts" / f"{attempt_number:04d}"


def _prepare_attempt(
    config: Mapping[str, Any],
    paths: Paths,
    run_root: Path,
    spec: Mapping[str, Any],
    cell_plan: Mapping[str, Any],
    cell_state: dict[str, Any],
) -> tuple[Path, dict[str, Any]]:
    attempt_number = len(cell_state["attempts"]) + 1
    attempt_root = _attempt_directory(run_root, cell_plan["cell_id"], attempt_number)
    attempt_root.mkdir(parents=True, exist_ok=False)
    workspace = attempt_root / "workspace"
    attempt = {
        "attempt": attempt_number,
        "replacement_for": attempt_number - 1 if attempt_number > 1 else None,
        "status": "prepared",
        "created_utc": utc_now(),
        "workspace": str(workspace),
        "input_fingerprint": None,
        "post_input_fingerprint": None,
        "input_manifest": str(attempt_root / "input_manifest.json"),
        "commands": [],
        "sealed_utc": None,
        "error": None,
    }
    cell_state["attempts"].append(attempt)
    cell_state["status"] = "running"
    return attempt_root, attempt


def _materialize_attempt_inputs(
    paths: Paths,
    spec: Mapping[str, Any],
    cell_plan: Mapping[str, Any],
    attempt_root: Path,
    attempt: dict[str, Any],
) -> None:
    workspace = Path(attempt["workspace"])
    case_id = str(cell_plan["case"])
    case_spec = spec["cases"][case_id]
    baseline_workspace = Path(case_spec["baseline"]["workspace"])
    include_paths = case_spec["baseline"]["include_paths"]
    _copy_declared_inputs(baseline_workspace, workspace, include_paths)
    if case_spec["history_policy"] == "snapshot":
        snapshot_value = case_spec["starting_evidence"].get("snapshot")
        if not snapshot_value:
            raise BenchmarkError(f"snapshot history policy has no frozen snapshot for {case_id}")
        snapshot = Path(snapshot_value)
        if directory_fingerprint(snapshot) != case_spec["starting_evidence"]["fingerprint"]:
            raise BenchmarkError(f"history snapshot fingerprint drift for {case_id}")
        _copy_history_snapshot(snapshot, workspace)
    overrides: dict[str, Any] = {}
    if cell_plan["kind"] == "measured":
        overrides.update(spec.get("runner", {}).get("measured_config_overrides", {}))
    overrides.update({
        "FAST_EVALUATION_MAX_WORKERS": int(case_spec["max_workers"]),
        "OPTIMIZE_SMOKE_TEST_ENABLED": False,
    })
    if cell_plan["kind"] == "measured":
        arm_id = str(cell_plan["arm"])
        arm_spec = spec["arms"][arm_id]
        if file_sha256(Path(arm_spec["template"])) != arm_spec["sha256"]:
            raise BenchmarkError(f"strategy template fingerprint drift for {arm_id}")
        overrides.update(arm_spec.get("config_overrides", {}))
        shutil.copy2(Path(arm_spec["template"]), workspace / "submit" / "optimization.py")
    _apply_config_overrides(workspace / "config.py", overrides)
    manifest = task_manifest(workspace, include_paths)
    fingerprint = task_fingerprint(workspace, include_paths)
    attempt["input_fingerprint"] = fingerprint
    write_new_json(
        attempt_root / "input_manifest.json",
        {
            "schema_version": SCHEMA_VERSION,
            "case": case_id,
            "arm": cell_plan.get("arm"),
            "seed": cell_plan["seed"],
            "baseline_task_fingerprint": case_spec["baseline"]["actual_task_fingerprint"],
            "starting_evidence_fingerprint": case_spec["starting_evidence"]["fingerprint"],
            "fingerprint": fingerprint,
            "files": manifest,
        },
    )


def _stream_pipe(pipe: Any, output: Path, console: Any | None, prefix: str) -> None:
    with output.open("x", encoding="utf-8", errors="replace", newline="\n") as target:
        while True:
            raw = pipe.readline()
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
            target.write(line)
            target.flush()
            if console is not None:
                console.write(f"{prefix}{line}")
                console.flush()


def _execute_logged(
    command: Sequence[str],
    *,
    cwd: Path,
    attempt_root: Path,
    attempt: dict[str, Any],
    timeout_sec: int,
    label: str,
    stream_output: bool = False,
) -> dict[str, Any]:
    sequence = len(attempt["commands"]) + 1
    command_root = attempt_root / "commands" / f"{sequence:04d}-{_safe_id(label)}"
    command_root.mkdir(parents=True, exist_ok=False)
    stdout_path = command_root / "stdout.log"
    stderr_path = command_root / "stderr.log"
    started_path = command_root / "command.started.json"
    finished_path = command_root / "command.finished.json"
    metadata: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "sequence": sequence,
        "label": label,
        "command": list(command),
        "cwd": str(cwd),
        "started_utc": utc_now(),
        "ended_utc": None,
        "duration_sec": None,
        "returncode": None,
        "timed_out": False,
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
        "stdout_sha256": None,
        "stderr_sha256": None,
    }
    write_new_json(started_path, metadata)
    if stream_output:
        print(f"[{label}] {' '.join(str(part) for part in command)}", flush=True)
    else:
        print(
            f"[{label}] started; log_dir={command_root.relative_to(attempt_root)}",
            file=sys.stderr,
            flush=True,
        )
    started = time.perf_counter()
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
    process = subprocess.Popen(
        list(command),
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=creationflags,
    )
    assert process.stdout is not None and process.stderr is not None
    out_thread = threading.Thread(
        target=_stream_pipe,
        args=(
            process.stdout,
            stdout_path,
            sys.stdout if stream_output else None,
            f"[{label}:out] ",
        ),
        daemon=True,
    )
    err_thread = threading.Thread(
        target=_stream_pipe,
        args=(
            process.stderr,
            stderr_path,
            sys.stderr if stream_output else None,
            f"[{label}:err] ",
        ),
        daemon=True,
    )
    out_thread.start()
    err_thread.start()
    try:
        returncode = process.wait(timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        metadata["timed_out"] = True
        process.kill()
        returncode = process.wait()
    out_thread.join()
    err_thread.join()
    metadata.update(
        {
            "ended_utc": utc_now(),
            "duration_sec": time.perf_counter() - started,
            "returncode": returncode,
            "stdout_sha256": file_sha256(stdout_path),
            "stderr_sha256": file_sha256(stderr_path),
        }
    )
    write_new_json(finished_path, metadata)
    attempt["commands"].append(str(finished_path))
    if not stream_output and (returncode != 0 or metadata["timed_out"]):
        print(
            f"[{label}] failed; returncode={returncode}; timed_out={metadata['timed_out']}; "
            f"metadata={finished_path}",
            file=sys.stderr,
            flush=True,
        )
    return metadata


def _completed_generation_indices(workspace: Path) -> list[int]:
    from yadof.recorded_data import list_optimization_metadata

    metadata = _generation_metadata(list_optimization_metadata(workspace))
    return sorted({int(item.get("generation_index", -1)) for item in metadata})


def _has_completed_generation_prefix(workspace: Path, count: int) -> tuple[bool, list[int]]:
    indices = _completed_generation_indices(workspace)
    return indices[:count] == list(range(count)), indices


def _surrogate_has_been_used(workspace: Path) -> bool:
    from yadof.recorded_data import list_optimization_metadata

    return any(
        item.get("surrogate_used") is True
        for item in _generation_metadata(list_optimization_metadata(workspace))
    )


def _cell_command(spec: Mapping[str, Any], cell: Mapping[str, Any], workspace: Path) -> list[str]:
    python = str(spec["package"]["python"])
    case = spec["cases"][cell["case"]]
    if cell["kind"] == "smoke":
        return [
            python,
            "-m",
            "yadof",
            "smoke-test",
            "--workspace",
            str(workspace),
            "--mode",
            str(case["mode"]),
            "--real-task",
        ]
    return [
        python,
        "-m",
        "yadof",
        "run",
        "--workspace",
        str(workspace),
        "--generations",
        str(cell["generations"]),
        "--start-generation",
        "0",
        "--mode",
        str(case["mode"]),
        "--population-size",
        str(cell["population"]),
        "--random-seed",
        str(cell["seed"]),
        "--no-smoke-test",
        "--no-progress",
        "--fail-on-all-infinite",
    ]


def _seal_attempt(
    run_root: Path,
    state: dict[str, Any],
    cell_plan: Mapping[str, Any],
    attempt: dict[str, Any],
    *,
    status: str,
    include_paths: Sequence[str],
    error: str | None = None,
) -> None:
    cell_state = state["cells"][cell_plan["cell_id"]]
    workspace = Path(attempt["workspace"])
    fingerprint = (
        task_fingerprint(workspace, include_paths)
        if attempt.get("input_fingerprint") is not None
        else None
    )
    attempt["post_input_fingerprint"] = fingerprint
    if attempt.get("input_fingerprint") is not None and fingerprint != attempt["input_fingerprint"]:
        status = "failed"
        error = (
            f"declared task inputs changed during execution: "
            f"{attempt['input_fingerprint']} -> {fingerprint}"
        )
    attempt["status"] = status
    attempt["error"] = error
    attempt["sealed_utc"] = utc_now()
    cell_state["status"] = status
    event = "cell-completed" if status == "completed" else "cell-failed"
    _save_state(
        run_root,
        state,
        event=event,
        cell_id=cell_plan["cell_id"],
        attempt=attempt["attempt"],
        error=error,
    )


def _run_one_cell(
    config: Mapping[str, Any],
    paths: Paths,
    run_root: Path,
    spec: Mapping[str, Any],
    state: dict[str, Any],
    cell_plan: Mapping[str, Any],
    *,
    stream_subprocess_output: bool = False,
) -> bool:
    cell_state = state["cells"][cell_plan["cell_id"]]
    if cell_state["status"] == "completed":
        return True
    if cell_state["status"] == "running":
        previous = cell_state["attempts"][-1]
        if previous.get("input_fingerprint") is not None and Path(previous["workspace"]).is_dir():
            with contextlib.suppress(Exception):
                previous["post_input_fingerprint"] = task_fingerprint(
                    Path(previous["workspace"]),
                    spec["cases"][cell_plan["case"]]["baseline"]["include_paths"],
                )
        previous["status"] = "failed"
        previous["error"] = "runner stopped before the attempt was sealed"
        previous["sealed_utc"] = utc_now()
        cell_state["status"] = "failed"
        _save_state(run_root, state, event="interrupted-attempt-sealed", cell_id=cell_plan["cell_id"])
    try:
        attempt_root, attempt = _prepare_attempt(config, paths, run_root, spec, cell_plan, cell_state)
        _save_state(
            run_root,
            state,
            event="cell-attempt-prepared",
            cell_id=cell_plan["cell_id"],
            attempt=attempt["attempt"],
            replacement_for=attempt["replacement_for"],
        )
        include_paths = spec["cases"][cell_plan["case"]]["baseline"]["include_paths"]
        workspace = Path(attempt["workspace"])
        timeout = int(spec["runner"]["command_timeout_sec"])
        initialize = _execute_logged(
            [spec["package"]["python"], "-m", "yadof", "init", str(workspace)],
            cwd=paths.root,
            attempt_root=attempt_root,
            attempt=attempt,
            timeout_sec=min(timeout, 300),
            label="init",
            stream_output=stream_subprocess_output,
        )
        _save_state(run_root, state)
        if initialize["returncode"] != 0 or initialize["timed_out"]:
            _seal_attempt(
                run_root,
                state,
                cell_plan,
                attempt,
                status="failed",
                include_paths=include_paths,
                error="yadof init failed",
            )
            return False
        _materialize_attempt_inputs(paths, spec, cell_plan, attempt_root, attempt)
        _save_state(
            run_root,
            state,
            event="cell-inputs-materialized",
            cell_id=cell_plan["cell_id"],
            attempt=attempt["attempt"],
            input_fingerprint=attempt["input_fingerprint"],
        )
        check = _execute_logged(
            [spec["package"]["python"], "-m", "yadof", "check", "--workspace", str(workspace)],
            cwd=paths.root,
            attempt_root=attempt_root,
            attempt=attempt,
            timeout_sec=min(timeout, 300),
            label="check",
            stream_output=stream_subprocess_output,
        )
        _save_state(run_root, state)
        if check["returncode"] != 0 or check["timed_out"]:
            _seal_attempt(
                run_root,
                state,
                cell_plan,
                attempt,
                status="failed",
                include_paths=include_paths,
                error="yadof check failed",
            )
            return False
        command = _cell_command(spec, cell_plan, workspace)
        result = _execute_logged(
            command,
            cwd=paths.root,
            attempt_root=attempt_root,
            attempt=attempt,
            timeout_sec=timeout,
            label="smoke" if cell_plan["kind"] == "smoke" else "optimize",
            stream_output=stream_subprocess_output,
        )
        _save_state(run_root, state)
        if result["returncode"] != 0 or result["timed_out"]:
            error = "command timed out" if result["timed_out"] else f"command exited {result['returncode']}"
            _seal_attempt(
                run_root,
                state,
                cell_plan,
                attempt,
                status="failed",
                include_paths=include_paths,
                error=error,
            )
            return False
        generations_ok, observed_indices = _has_completed_generation_prefix(
            workspace, int(cell_plan["generations"])
        ) if cell_plan["kind"] == "measured" else (True, [])
        if not generations_ok:
            _seal_attempt(
                run_root,
                state,
                cell_plan,
                attempt,
                status="failed",
                include_paths=include_paths,
                error=(
                    "yadof command returned success without the expected complete generation "
                    f"metadata prefix; observed {observed_indices}"
                ),
            )
            return False
        if (
            cell_plan["kind"] == "measured"
            and spec["arms"][cell_plan["arm"]]["surrogate"]
            and int(cell_plan["max_generations"]) > int(cell_plan["generations"])
        ):
            if not _surrogate_has_been_used(workspace):
                extra = int(cell_plan["max_generations"]) - int(cell_plan["generations"])
                extension = [
                    spec["package"]["python"],
                    "-m",
                    "yadof",
                    "run",
                    "--workspace",
                    str(workspace),
                    "--generations",
                    str(extra),
                    "--start-generation",
                    str(cell_plan["generations"]),
                    "--mode",
                    str(spec["cases"][cell_plan["case"]]["mode"]),
                    "--population-size",
                    str(cell_plan["population"]),
                    "--random-seed",
                    str(cell_plan["seed"]),
                    "--no-smoke-test",
                    "--no-progress",
                    "--fail-on-all-infinite",
                ]
                extension_result = _execute_logged(
                    extension,
                    cwd=paths.root,
                    attempt_root=attempt_root,
                    attempt=attempt,
                    timeout_sec=timeout,
                    label="optional-checkpoint-extension",
                    stream_output=stream_subprocess_output,
                )
                _save_state(run_root, state)
                if extension_result["returncode"] != 0 or extension_result["timed_out"]:
                    _seal_attempt(
                        run_root,
                        state,
                        cell_plan,
                        attempt,
                        status="failed",
                        include_paths=include_paths,
                        error="optional checkpoint extension failed",
                    )
                    return False
                extension_ok, extension_indices = _has_completed_generation_prefix(
                    workspace, int(cell_plan["max_generations"])
                )
                if not extension_ok:
                    _seal_attempt(
                        run_root,
                        state,
                        cell_plan,
                        attempt,
                        status="failed",
                        include_paths=include_paths,
                        error=(
                            "checkpoint extension returned success without the expected complete "
                            f"generation metadata prefix; observed {extension_indices}"
                        ),
                    )
                    return False
        _seal_attempt(
            run_root,
            state,
            cell_plan,
            attempt,
            status="completed",
            include_paths=include_paths,
        )
        return True
    except Exception as exc:
        if cell_state.get("attempts"):
            attempt = cell_state["attempts"][-1]
            if attempt.get("status") not in TERMINAL_CELL_STATES:
                attempt["status"] = "failed"
                attempt["error"] = str(exc)
                attempt["sealed_utc"] = utc_now()
        cell_state["status"] = "failed"
        _save_state(run_root, state, event="cell-exception", cell_id=cell_plan["cell_id"], error=str(exc))
        return False
def execute_run(
    config: Mapping[str, Any],
    paths: Paths,
    run_id: str,
    *,
    fail_fast_override: bool | None = None,
    stream_subprocess_output: bool = False,
) -> dict[str, Any]:
    run_root, spec, state = load_run(paths, run_id)
    fail_fast = bool(spec["runner"]["fail_fast"]) if fail_fast_override is None else fail_fast_override
    state["status"] = "running"
    _save_state(run_root, state, event="run-started-or-resumed", fail_fast=fail_fast)
    success = True
    stop = False
    for cell_plan in spec["plan"]["cells"]:
        cell_state = state["cells"][cell_plan["cell_id"]]
        if cell_state["status"] == "completed":
            continue
        if stop:
            cell_state["status"] = "skipped"
            _save_state(run_root, state, event="cell-skipped-fail-fast", cell_id=cell_plan["cell_id"])
            continue
        print(f"[cell] {cell_plan['cell_id']} started", file=sys.stderr, flush=True)
        ok = _run_one_cell(
            config,
            paths,
            run_root,
            spec,
            state,
            cell_plan,
            stream_subprocess_output=stream_subprocess_output,
        )
        print(
            f"[cell] {cell_plan['cell_id']} {state['cells'][cell_plan['cell_id']]['status']}",
            file=sys.stderr,
            flush=True,
        )
        success = success and ok
        if not ok and fail_fast:
            stop = True
    statuses = [cell["status"] for cell in state["cells"].values()]
    if all(status == "completed" for status in statuses):
        state["status"] = "completed"
    elif any(status == "failed" for status in statuses):
        state["status"] = "incomplete"
    else:
        state["status"] = "incomplete"
    _save_state(run_root, state, event="run-finished", status=state["status"])
    return state


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Path):
        return str(value)
    if dataclasses.is_dataclass(value):
        return _json_safe(dataclasses.asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "tolist"):
        return _json_safe(value.tolist())
    if hasattr(value, "item"):
        with contextlib.suppress(Exception):
            return _json_safe(value.item())
    return str(value)


def _new_sequence_dir(parent: Path, prefix: str) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    for number in range(1, 1_000_000):
        candidate = parent / f"{prefix}-{number:04d}"
        try:
            candidate.mkdir()
            return candidate
        except FileExistsError:
            continue
    raise BenchmarkError(f"could not allocate a new {prefix} evidence directory")


def _write_new_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


def _capture_json_cli(
    command: Sequence[str],
    *,
    cwd: Path,
    evidence_dir: Path,
    stem: str,
    timeout: int,
) -> dict[str, Any]:
    result = _run_read_only(command, cwd=cwd, timeout=timeout)
    stdout_path = evidence_dir / f"{stem}.stdout.log"
    stderr_path = evidence_dir / f"{stem}.stderr.log"
    _write_new_text(stdout_path, str(result.get("stdout", "")))
    _write_new_text(stderr_path, str(result.get("stderr", "")))
    parsed: Any = None
    parse_error: str | None = None
    if result.get("returncode") == 0:
        try:
            parsed = json.loads(str(result.get("stdout", "")))
        except json.JSONDecodeError as exc:
            parse_error = str(exc)
    metadata = {
        "command": list(command),
        "cwd": str(cwd),
        "returncode": result.get("returncode"),
        "duration_sec": result.get("duration_sec"),
        "error": result.get("error"),
        "parse_error": parse_error,
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
        "stdout_sha256": file_sha256(stdout_path),
        "stderr_sha256": file_sha256(stderr_path),
    }
    write_new_json(evidence_dir / f"{stem}.command.json", _json_safe(metadata))
    if parsed is not None:
        write_new_json(evidence_dir / f"{stem}.json", _json_safe(parsed))
    return {"metadata": metadata, "payload": parsed}


def _generation_metadata(items: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    generations = [
        item
        for item in items
        if item.get("record_type") == "generation"
        or ("generation_index" in item and ("population_size" in item or "created_job_names" in item))
    ]
    return sorted(
        generations,
        key=lambda item: (
            str(item.get("run_id", "")),
            int(item.get("optimization_index", 0) or 0),
            int(item.get("generation_index", 0) or 0),
        ),
    )


def _attempted_count(generations: Sequence[Mapping[str, Any]]) -> int:
    total = 0
    for item in generations:
        population_size = item.get("population_size")
        if isinstance(population_size, int):
            total += population_size
        else:
            names = item.get("created_job_names")
            if isinstance(names, list):
                total += len(names)
    return total


def _initial_population_fingerprint(
    generations: Sequence[Mapping[str, Any]],
    normalized_variables: Mapping[str, Sequence[float]],
    records: Sequence[Mapping[str, Any]],
) -> tuple[str | None, int, str | None]:
    generation_zero = [item for item in generations if int(item.get("generation_index", -1)) == 0]
    if not generation_zero:
        return None, 0, "public optimization metadata has no generation 0"
    names = generation_zero[0].get("created_job_names")
    if not isinstance(names, list) or not names:
        return None, 0, "generation 0 metadata has no created_job_names"
    generation_names = {str(name) for name in names}
    indexed_names = [
        (int(record["population_index"]), str(record["job_name"]))
        for record in records
        if str(record.get("job_name")) in generation_names
        and isinstance(record.get("population_index"), int)
    ]
    if len(indexed_names) != len(generation_names):
        return None, 0, "population_index is unavailable for one or more generation-0 jobs"
    indexed_names.sort(key=lambda item: item[0])
    indices = [index for index, _name in indexed_names]
    if indices != list(range(len(indexed_names))):
        return None, 0, f"generation-0 population_index sequence is not contiguous: {indices}"
    ordered_names = [name for _index, name in indexed_names]
    missing = [name for name in ordered_names if name not in normalized_variables]
    if missing:
        return None, 0, f"normalized variables unavailable for {len(missing)} generation-0 jobs"
    matrix = [
        [float(value) for value in normalized_variables[str(name)]]
        for name in ordered_names
    ]
    return object_sha256(matrix), len(matrix), None


def _rawdata_shapes(workspace: Path, records: Sequence[Mapping[str, Any]]) -> tuple[dict[str, list[int]], str | None]:
    from yadof.job_template.rawdata_contract import load_rawdata_views
    from yadof.recorded_data import get_rawdata_samples

    completed = [item for item in records if item.get("status") == "completed"]
    if not completed:
        return {}, "no completed record is available for rawData shape inspection"
    job_name = str(completed[-1]["job_name"])
    samples = get_rawdata_samples(workspace, job_names=[job_name], status="completed")
    if not samples:
        return {}, f"public rawData API returned no sample for {job_name}"
    _name, items = samples[-1]
    return {view.name: [int(x) for x in view.data.shape] for view in load_rawdata_views(items)}, None


def _command_validity(attempt: Mapping[str, Any]) -> dict[str, Any]:
    commands: list[dict[str, Any]] = []
    warnings: list[str] = []
    for path_value in attempt.get("commands", []):
        try:
            metadata = read_json(Path(path_value))
        except BenchmarkError:
            continue
        stdout_path = Path(str(metadata.get("stdout", "")))
        stdout = ""
        if stdout_path.is_file():
            with contextlib.suppress(OSError):
                stdout = stdout_path.read_text(encoding="utf-8", errors="replace")
        if metadata.get("label") == "check":
            warnings.extend(
                line.strip() for line in stdout.splitlines() if line.lstrip().startswith("[WARN]")
            )
        commands.append(
            {
                "label": metadata.get("label"),
                "returncode": metadata.get("returncode"),
                "timed_out": metadata.get("timed_out"),
                "duration_sec": metadata.get("duration_sec"),
                "metadata": str(path_value),
            }
        )
    return {"commands": commands, "yadof_check_warnings": warnings}


def _finite_cost_row(row: Mapping[str, Any]) -> bool:
    costs = row.get("costs")
    return isinstance(costs, (list, tuple)) and bool(costs) and all(
        isinstance(value, (int, float)) and math.isfinite(float(value)) for value in costs
    )


def _collect_cell(
    spec: Mapping[str, Any],
    cell_plan: Mapping[str, Any],
    cell_state: Mapping[str, Any],
    evidence_dir: Path,
) -> dict[str, Any]:
    from yadof import recorded_data
    from yadof.tools import cost_viewer

    result: dict[str, Any] = {
        "cell_id": cell_plan["cell_id"],
        "kind": cell_plan["kind"],
        "case": cell_plan["case"],
        "arm": cell_plan["arm"],
        "seed": cell_plan["seed"],
        "execution_status": cell_state["status"],
        "eligible_for_primary_performance_aggregate": False,
        "exclusion_reason": None,
        "attempt": None,
        "validity": None,
        "metrics": None,
        "public_api_issues": [],
    }
    attempts = list(cell_state.get("attempts", []))
    if not attempts:
        result["exclusion_reason"] = "cell has no attempt workspace"
        return result
    attempt = attempts[-1]
    result["attempt"] = {
        "number": attempt.get("attempt"),
        "replacement_for": attempt.get("replacement_for"),
        "status": attempt.get("status"),
        "workspace": attempt.get("workspace"),
        "input_fingerprint": attempt.get("input_fingerprint"),
        "post_input_fingerprint": attempt.get("post_input_fingerprint"),
        "input_unchanged": attempt.get("input_fingerprint") == attempt.get("post_input_fingerprint"),
        "error": attempt.get("error"),
    }
    workspace = Path(str(attempt["workspace"]))
    if not workspace.is_dir():
        result["exclusion_reason"] = "latest attempt workspace does not exist"
        return result
    issues: list[str] = []
    objective_names_out: list[str] = []
    try:
        rows = cost_viewer.build_rows(
            workspace,
            status="completed",
            issues=issues,
            objective_names_out=objective_names_out,
        )
        objectives = objective_names_out or cost_viewer.objective_names(workspace, rows)
        cost_view_summary = cost_viewer.summarize_rows(
            workspace,
            rows,
            resolved_objective_names=objectives,
            issues=issues,
        )
    except Exception as exc:
        rows = []
        objectives = []
        cost_view_summary = None
        issues.append(f"cost_viewer collection failed: {exc}")
    try:
        records = list(recorded_data.list_records(workspace))
    except Exception as exc:
        records = []
        issues.append(f"list_records failed: {exc}")
    try:
        optimization_metadata = list(recorded_data.list_optimization_metadata(workspace))
    except Exception as exc:
        optimization_metadata = []
        issues.append(f"list_optimization_metadata failed: {exc}")
    try:
        surrogate_metadata = list(recorded_data.list_surrogate_metadata(workspace))
    except Exception as exc:
        surrogate_metadata = []
        issues.append(f"list_surrogate_metadata failed: {exc}")
    try:
        normalized = {
            str(name): tuple(float(value) for value in values)
            for name, values in recorded_data.get_normalized_variables(workspace, status=None)
        }
    except Exception as exc:
        normalized = {}
        issues.append(f"get_normalized_variables failed: {exc}")
    generations = _generation_metadata(optimization_metadata)
    attempted = _attempted_count(generations) if cell_plan["kind"] == "measured" else len(records)
    attempted_source = (
        "sum of population_size in public generation metadata"
        if cell_plan["kind"] == "measured"
        else "public record count in the disposable smoke workspace"
    )
    initial_fingerprint, initial_count, initial_reason = _initial_population_fingerprint(
        generations, normalized, records
    )
    finite_rows = [row for row in rows if _finite_cost_row(row)]
    invalid_rows = len(rows) - len(finite_rows)
    generation_validity: list[dict[str, Any]] = []
    for item in generations:
        generation_index = int(item.get("generation_index", 0) or 0)
        generation_rows = [
            row for row in rows if row.get("generation_index") == generation_index
        ]
        finite_generation_rows = [row for row in generation_rows if _finite_cost_row(row)]
        generation_validity.append(
            {
                "generation_index": generation_index,
                "population_size": item.get("population_size"),
                "source": item.get("source"),
                "surrogate_used": item.get("surrogate_used"),
                "completed_rows": len(generation_rows),
                "finite_rows": len(finite_generation_rows),
                "all_infinite": bool(generation_rows and not finite_generation_rows),
            }
        )
    hypervolume: dict[str, Any]
    if rows:
        try:
            x_values, cumulative, current, reference = cost_viewer.hypervolume_series(rows)
            attempted_by_generation: list[int] = []
            running = 0
            for item in generations:
                running += _attempted_count([item])
                attempted_by_generation.append(running)
            cumulative_values = [float(value) for value in cumulative]
            current_values = [float(value) for value in current]
            if len(attempted_by_generation) != len(cumulative_values):
                issues.append(
                    "hypervolume generation count differs from public optimization metadata; "
                    "attempted-count alignment is unavailable"
                )
                attempted_axis: list[int] | None = None
            else:
                attempted_axis = attempted_by_generation
            hypervolume = {
                "completed_row_axis": [float(value) for value in x_values],
                "attempted_evaluation_axis": attempted_axis,
                "cumulative": cumulative_values,
                "current_generation": current_values,
                "reference_point": [float(value) for value in reference],
                "final_cumulative": cumulative_values[-1] if cumulative_values else None,
            }
        except Exception as exc:
            hypervolume = {"final_cumulative": None, "error": str(exc)}
            issues.append(f"hypervolume_series failed: {exc}")
    else:
        hypervolume = {"final_cumulative": None, "error": "no completed cost rows"}
    try:
        observed_shapes, shape_error = _rawdata_shapes(workspace, records)
        if shape_error:
            issues.append(shape_error)
    except Exception as exc:
        observed_shapes = {}
        issues.append(f"rawData shape inspection failed: {exc}")
    expected_shapes = spec["cases"][cell_plan["case"]]["rawdata_shapes"]
    rawdata_shape_match = bool(observed_shapes) and observed_shapes == expected_shapes
    evaluator_duration = sum(
        float(item.get("job_metadata", {}).get("elapsed_time", 0.0))
        for item in records
        if isinstance(item.get("job_metadata", {}).get("elapsed_time"), (int, float))
    )
    training_events = [
        {
            key: item.get(key)
            for key in (
                "generation_index",
                "duration_sec",
                "sample_count",
                "query_count",
                "epochs",
                "member_count",
                "device",
            )
            if key in item
        }
        for item in surrogate_metadata
        if isinstance(item, Mapping)
    ]
    training_duration = sum(
        float(item["duration_sec"])
        for item in surrogate_metadata
        if isinstance(item, Mapping) and isinstance(item.get("duration_sec"), (int, float))
    )
    reference_generation_sec = spec["cases"][cell_plan["case"]].get(
        "representative_expensive_generation_sec"
    )
    surrogate_evidence: dict[str, Any] | None = None
    is_surrogate = bool(
        cell_plan["kind"] == "measured"
        and spec["arms"].get(cell_plan["arm"], {}).get("surrogate", False)
    )
    if is_surrogate:
        python = str(spec["package"]["python"])
        summary = _capture_json_cli(
            [
                python,
                "-m",
                "yadof",
                "view",
                "surrogate",
                "summary",
                "--workspace",
                str(workspace),
                "--format",
                "json",
            ],
            cwd=workspace,
            evidence_dir=evidence_dir,
            stem=f"{cell_plan['cell_id']}.surrogate-summary",
            timeout=300,
        )
        checkpoint_count = None
        if isinstance(summary["payload"], Mapping):
            checkpoint_count = summary["payload"].get(
                "checkpoint_count", len(summary["payload"].get("checkpoints", []))
            )
        public_training_checkpoint_count = sum(
            1
            for item in surrogate_metadata
            if isinstance(item, Mapping)
            and item.get("status") == "completed"
            and not bool(item.get("skipped", False))
            and bool(item.get("checkpoint_path"))
        )
        effective_checkpoint_count = (
            checkpoint_count
            if isinstance(checkpoint_count, int)
            else public_training_checkpoint_count
        )
        audits: dict[str, Any] = {}
        if effective_checkpoint_count > 0:
            for quantity, stem_suffix in (("all-costs", "costs"), ("all-rawdata", "rawdata")):
                audit = _capture_json_cli(
                    [
                        python,
                        "-m",
                        "yadof",
                        "view",
                        "surrogate",
                        "audit",
                        "--workspace",
                        str(workspace),
                        "--sample-percent",
                        str(spec["runner"]["audit_sample_percent"]),
                        "--random-seed",
                        str(spec["runner"]["audit_random_seed"]),
                        "--metric",
                        "both",
                        "--quantity",
                        quantity,
                        "--format",
                        "json",
                    ],
                    cwd=workspace,
                    evidence_dir=evidence_dir,
                    stem=f"{cell_plan['cell_id']}.surrogate-audit-{stem_suffix}",
                    timeout=int(spec["runner"]["command_timeout_sec"]),
                )
                audits[stem_suffix] = {
                    "returncode": audit["metadata"]["returncode"],
                    "payload": audit["payload"],
                    "command": audit["metadata"],
                }
        surrogate_evidence = {
            "checkpoint_count": effective_checkpoint_count,
            "checkpoint_count_source": (
                "view surrogate summary JSON"
                if isinstance(checkpoint_count, int)
                else "public list_surrogate_metadata fallback because summary JSON failed"
            ),
            "summary_checkpoint_count": checkpoint_count,
            "public_training_checkpoint_count": public_training_checkpoint_count,
            "summary": summary["payload"],
            "summary_command": summary["metadata"],
            "audits": audits,
            "training_events": training_events,
            "training_duration_sec": training_duration,
            "representative_expensive_generation_context": (
                {
                    "declared_generation_sec": float(reference_generation_sec),
                    "training_headroom_sec": float(reference_generation_sec) - training_duration,
                    "training_fraction_of_declared_generation": (
                        training_duration / float(reference_generation_sec)
                    ),
                    "interpretation": "Context only; not an algorithm verdict or a comparison to this cheap run.",
                }
                if isinstance(reference_generation_sec, (int, float))
                and float(reference_generation_sec) > 0
                else None
            ),
            "training_lag_generations": {
                "value": None,
                "reason": "The public summary/audit schema does not expose each checkpoint's exact training cutoff.",
            },
            "coverage_classification": {
                "value": None,
                "reason": "Without a public checkpoint cutoff, overlap and forward-generation audit cells are not relabeled.",
            },
        }
    status_counts = {
        str(status): sum(1 for item in records if str(item.get("status")) == str(status))
        for status in {item.get("status") for item in records}
    }
    completed_evaluations = int(status_counts.get("completed", 0))
    failed_evaluations = max(0, attempted - completed_evaluations)
    timeout_evaluations = sum(
        1
        for item in records
        if "timeout"
        in json.dumps(
            {
                "status": item.get("status"),
                "error": item.get("error"),
                "job_metadata": item.get("job_metadata", {}),
            },
            default=str,
            ensure_ascii=False,
        ).casefold()
    )
    command_validity = _command_validity(attempt)
    workspace_roots = {
        root: (workspace / root).is_dir() for root in ("submit", "job_template")
    }
    result["validity"] = {
        "planned_real_evaluations": int(cell_plan["planned_attempted_evaluations"]),
        "attempted_real_evaluations": attempted,
        "completed_candidate_evaluations": completed_evaluations,
        "failed_candidate_evaluations": failed_evaluations,
        "timeout_candidate_evaluations": timeout_evaluations,
        "all_infinite_generation_count": sum(
            1 for item in generation_validity if item["all_infinite"]
        ),
        "generation_sequence": generation_validity,
        "complete_task_roots": workspace_roots,
        "command_evidence": command_validity["commands"],
        "yadof_check_warnings": command_validity["yadof_check_warnings"],
    }
    metrics = {
        "objective_names": objectives,
        "objective_count": len(objectives),
        "completed_cost_rows": len(rows),
        "finite_objective_rows": len(finite_rows),
        "invalid_objective_rows": invalid_rows,
        "attempted_real_evaluations": attempted,
        "attempted_count_source": attempted_source,
        "record_status_counts": dict(sorted(status_counts.items())),
        "evaluator_elapsed_sec_sum": evaluator_duration,
        "initial_population_fingerprint": initial_fingerprint,
        "initial_population_count": initial_count,
        "initial_population_gap": initial_reason,
        "hypervolume": hypervolume,
        "cost_view_summary": cost_view_summary,
        "evaluation_normalized_hv_auc": {
            "value": None,
            "reason": "yadof 0.4.0 public cost_viewer exposes HV series but no evaluation-normalized HV-AUC contract.",
        },
        "rawdata_shapes": observed_shapes,
        "rawdata_shapes_match_contract": rawdata_shape_match,
        "generation_metadata": optimization_metadata,
        "surrogate_training_metadata": surrogate_metadata,
        "surrogate": surrogate_evidence,
        "cost_rows": rows,
    }
    complete = cell_state["status"] == "completed"
    result["eligible_for_primary_performance_aggregate"] = bool(
        complete and cell_plan["kind"] == "measured"
    )
    if not complete:
        result["exclusion_reason"] = "cell execution did not complete"
    elif cell_plan["kind"] != "measured":
        result["exclusion_reason"] = "disposable smoke cells are structural evidence, not measured arms"
    result["metrics"] = _json_safe(metrics)
    result["public_api_issues"] = issues
    return _json_safe(result)


def collect_run(paths: Paths, run_id: str) -> tuple[Path, dict[str, Any]]:
    run_root, spec, state = load_run(paths, run_id)
    verify_run_inputs(paths, spec, verify_automation=False, verify_config=False)
    evidence_dir = _new_sequence_dir(run_root / "evidence", "collect")
    cell_plan_by_id = {cell["cell_id"]: cell for cell in spec["plan"]["cells"]}
    cells: dict[str, Any] = {}
    for cell_id, cell_state in state["cells"].items():
        cells[cell_id] = _collect_cell(spec, cell_plan_by_id[cell_id], cell_state, evidence_dir)
    tool_gaps: dict[str, str] = {
        "evaluation_normalized_hv_auc": "No public yadof 0.4.0 metric contract; values are null.",
        "checkpoint_training_cutoff": "Not present in public surrogate summary/audit JSON; overlap/forward labels are withheld.",
    }
    failed_summaries = [
        cell_id
        for cell_id, cell in cells.items()
        if _metric(cell, "surrogate", "summary_command", "returncode") not in (None, 0)
    ]
    if failed_summaries:
        tool_gaps["surrogate_summary_json"] = (
            "The public `yadof view surrogate summary --format json` command failed for "
            f"{failed_summaries}; its append-only stderr evidence is retained. On the first "
            "test_com canary, yadof 0.4.0 reported `could not convert string to float: 'x0'`."
        )
    failed_audits = [
        cell_id
        for cell_id, cell in cells.items()
        if any(
            value.get("returncode") not in (None, 0)
            for value in (_metric(cell, "surrogate", "audits") or {}).values()
        )
    ]
    if failed_audits:
        tool_gaps["surrogate_audit_json"] = (
            "The public surrogate audit JSON command failed for "
            f"{failed_audits}; command metadata and stderr are retained without private fallback."
        )
    collection = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "spec_sha256": spec["spec_sha256"],
        "collected_utc": utc_now(),
        "execution_state": state["status"],
        "suite": spec["suite"],
        "purpose": spec["purpose"],
        "collector": {
            "core_path": str(Path(__file__).resolve()),
            "core_sha256": file_sha256(Path(__file__).resolve()),
            "entrypoint_sha256": file_sha256(Path(__file__).resolve().with_name("benchmark.py")),
        },
        "cells": cells,
        "tool_gaps": tool_gaps,
    }
    collection_path = evidence_dir / "collection.json"
    write_new_json(collection_path, _json_safe(collection))
    atomic_write_json(run_root / "metrics.json", _json_safe(collection))
    atomic_write_json(
        run_root / "collection_index.json",
        {
            "schema_version": SCHEMA_VERSION,
            "latest": str(collection_path.relative_to(run_root)),
            "sha256": file_sha256(collection_path),
            "updated_utc": utc_now(),
        },
    )
    return collection_path, collection


def _latest_collection(run_root: Path) -> tuple[Path, dict[str, Any]]:
    index = read_json(run_root / "collection_index.json")
    path = resolve_inside(run_root, str(index.get("latest", "")), label="collection index")
    if not path.is_file():
        raise BenchmarkError(f"indexed collection does not exist: {path}")
    actual = file_sha256(path)
    if actual != index.get("sha256"):
        raise BenchmarkError(f"indexed collection fingerprint mismatch: {path}")
    return path, read_json(path)


def _metric(cell: Mapping[str, Any], *keys: str) -> Any:
    value: Any = cell.get("metrics")
    for key in keys:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    return value


def _population_pair_rows(spec: Mapping[str, Any], collection: Mapping[str, Any]) -> list[dict[str, Any]]:
    measured = [
        cell
        for cell in collection["cells"].values()
        if cell.get("kind") == "measured"
    ]
    groups: dict[tuple[str, int], list[Mapping[str, Any]]] = defaultdict(list)
    for cell in measured:
        groups[(str(cell["case"]), int(cell["seed"]))].append(cell)
    rows: list[dict[str, Any]] = []
    expected_arms = list(spec["arms"])
    for (case_id, seed), cells in sorted(groups.items()):
        by_arm = {str(cell["arm"]): cell for cell in cells}
        fingerprints = {
            arm: _metric(by_arm[arm], "initial_population_fingerprint")
            for arm in expected_arms
            if arm in by_arm
        }
        available = len(fingerprints) == len(expected_arms) and all(fingerprints.values())
        rows.append(
            {
                "case": case_id,
                "seed": seed,
                "fingerprints": fingerprints,
                "equal": bool(available and len(set(fingerprints.values())) == 1),
                "gap": None if available else "one or more arm fingerprints are unavailable",
            }
        )
    return rows


def _structural_report(spec: Mapping[str, Any], collection: Mapping[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    workspace_paths: list[str] = []
    for cell_id, cell in collection["cells"].items():
        complete = cell.get("execution_status") == "completed"
        checks.append(
            {
                "check": "cell-completed",
                "cell_id": cell_id,
                "ok": complete,
                "details": cell.get("exclusion_reason"),
            }
        )
        if complete:
            workspace_paths.append(str(cell.get("attempt", {}).get("workspace")))
            expected_objectives = int(spec["cases"][cell["case"]]["expected_objectives"])
            actual_objectives = _metric(cell, "objective_count")
            checks.append(
                {
                    "check": "objective-count",
                    "cell_id": cell_id,
                    "ok": actual_objectives == expected_objectives,
                    "details": {"expected": expected_objectives, "actual": actual_objectives},
                }
            )
            checks.append(
                {
                    "check": "rawdata-shape-contract",
                    "cell_id": cell_id,
                    "ok": bool(_metric(cell, "rawdata_shapes_match_contract")),
                    "details": _metric(cell, "rawdata_shapes"),
                }
            )
            checks.append(
                {
                    "check": "declared-inputs-unchanged",
                    "cell_id": cell_id,
                    "ok": bool(cell.get("attempt", {}).get("input_unchanged")),
                    "details": cell.get("attempt"),
                }
            )
            warnings = cell.get("validity", {}).get("yadof_check_warnings", [])
            checks.append(
                {
                    "check": "yadof-check-zero-warnings",
                    "cell_id": cell_id,
                    "ok": not warnings,
                    "details": warnings,
                }
            )
            roots = cell.get("validity", {}).get("complete_task_roots", {})
            checks.append(
                {
                    "check": "complete-task-source-roots",
                    "cell_id": cell_id,
                    "ok": bool(roots) and all(bool(value) for value in roots.values()),
                    "details": roots,
                }
            )
            if cell.get("kind") == "measured":
                generations = cell.get("validity", {}).get("generation_sequence", [])
                expected_count = int(
                    next(
                        plan_cell["generations"]
                        for plan_cell in spec["plan"]["cells"]
                        if plan_cell["cell_id"] == cell_id
                    )
                )
                indices = [item.get("generation_index") for item in generations]
                expected_indices = list(range(expected_count))
                checks.append(
                    {
                        "check": "expected-generation-sequence",
                        "cell_id": cell_id,
                        "ok": indices[:expected_count] == expected_indices,
                        "details": {"expected_prefix": expected_indices, "actual": indices},
                    }
                )
                checks.append(
                    {
                        "check": "finite-cost-in-each-expected-generation",
                        "cell_id": cell_id,
                        "ok": len(generations) >= expected_count
                        and all(int(item.get("finite_rows", 0)) > 0 for item in generations[:expected_count]),
                        "details": generations,
                    }
                )
                surrogate_arm = bool(spec["arms"][cell["arm"]]["surrogate"])
                surrogate_used = [item.get("surrogate_used") for item in generations]
                intended = (
                    any(value is True for value in surrogate_used)
                    if surrogate_arm
                    else not any(value is True for value in surrogate_used)
                )
                checks.append(
                    {
                        "check": "optimization-metadata-arm",
                        "cell_id": cell_id,
                        "ok": intended,
                        "details": {
                            "arm": cell["arm"],
                            "surrogate_expected": surrogate_arm,
                            "surrogate_used": surrogate_used,
                            "sources": [item.get("source") for item in generations],
                        },
                    }
                )
            if cell.get("kind") == "measured" and spec["arms"][cell["arm"]]["surrogate"]:
                checkpoint_count = _metric(cell, "surrogate", "checkpoint_count")
                checks.append(
                    {
                        "check": "surrogate-checkpoint-created",
                        "cell_id": cell_id,
                        "ok": isinstance(checkpoint_count, int) and checkpoint_count > 0,
                        "details": {"checkpoint_count": checkpoint_count},
                    }
                )
                audits = _metric(cell, "surrogate", "audits") or {}
                audit_details = {
                    name: {
                        "returncode": value.get("returncode"),
                        "payload_present": value.get("payload") is not None,
                    }
                    for name, value in audits.items()
                }
                checks.append(
                    {
                        "check": "surrogate-summary-and-audit-json",
                        "cell_id": cell_id,
                        "ok": _metric(cell, "surrogate", "summary") is not None
                        and {"costs", "rawdata"}.issubset(audits)
                        and all(
                            value.get("returncode") == 0 and value.get("payload") is not None
                            for value in audits.values()
                        ),
                        "details": audit_details,
                    }
                )
    population_pairs = _population_pair_rows(spec, collection)
    for pair in population_pairs:
        checks.append(
            {
                "check": "paired-generation-zero-population",
                "cell_id": f"{pair['case']}__seed-{pair['seed']}",
                "ok": pair["equal"],
                "details": pair,
            }
        )
    checks.append(
        {
            "check": "isolated-cell-workspaces",
            "cell_id": "selected-matrix",
            "ok": len(workspace_paths) == len(set(workspace_paths)),
            "details": workspace_paths,
        }
    )
    return {
        "contract_satisfied": all(bool(item["ok"]) for item in checks),
        "checks": checks,
        "initial_population_pairs": population_pairs,
    }


def _descriptive(values: Sequence[float]) -> dict[str, Any]:
    finite = [float(value) for value in values if math.isfinite(float(value))]
    if not finite:
        return {"count": 0, "mean": None, "median": None, "minimum": None, "maximum": None}
    return {
        "count": len(finite),
        "mean": statistics.fmean(finite),
        "median": statistics.median(finite),
        "minimum": min(finite),
        "maximum": max(finite),
    }


def _performance_report(spec: Mapping[str, Any], collection: Mapping[str, Any]) -> dict[str, Any]:
    surrogate_arms = [arm for arm, details in spec["arms"].items() if details.get("surrogate")]
    real_arms = [arm for arm, details in spec["arms"].items() if not details.get("surrogate")]
    if len(surrogate_arms) != 1 or len(real_arms) != 1:
        raise BenchmarkError("descriptive paired report requires exactly one surrogate and one real-search arm")
    surrogate_arm = surrogate_arms[0]
    real_arm = real_arms[0]
    measured = [cell for cell in collection["cells"].values() if cell.get("kind") == "measured"]
    groups: dict[tuple[str, int], dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for cell in measured:
        groups[(str(cell["case"]), int(cell["seed"]))][str(cell["arm"])] = cell
    pair_rows: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    difference_fields = {
        "final_cumulative_hypervolume": ("hypervolume", "final_cumulative"),
        "evaluator_elapsed_sec_sum": ("evaluator_elapsed_sec_sum",),
        "finite_objective_rows": ("finite_objective_rows",),
        "invalid_objective_rows": ("invalid_objective_rows",),
    }
    for (case_id, seed), by_arm in sorted(groups.items()):
        real = by_arm.get(real_arm)
        surrogate = by_arm.get(surrogate_arm)
        reasons: list[str] = []
        if real is None or surrogate is None:
            reasons.append("paired arm is missing")
        elif not real.get("eligible_for_primary_performance_aggregate") or not surrogate.get(
            "eligible_for_primary_performance_aggregate"
        ):
            reasons.append("one or both cells are incomplete")
        fingerprints = {
            real_arm: _metric(real or {}, "initial_population_fingerprint"),
            surrogate_arm: _metric(surrogate or {}, "initial_population_fingerprint"),
        }
        fingerprint_equal = bool(
            all(fingerprints.values()) and len(set(fingerprints.values())) == 1
        )
        if not fingerprint_equal:
            reasons.append("generation-0 population fingerprints do not match")
        attempted = {
            real_arm: _metric(real or {}, "attempted_real_evaluations"),
            surrogate_arm: _metric(surrogate or {}, "attempted_real_evaluations"),
        }
        if attempted[real_arm] != attempted[surrogate_arm]:
            reasons.append("observed attempted real-evaluation counts are unequal")
        if reasons:
            excluded.append(
                {
                    "case": case_id,
                    "seed": seed,
                    "reasons": reasons,
                    "execution_status": {
                        real_arm: real.get("execution_status") if real else None,
                        surrogate_arm: surrogate.get("execution_status") if surrogate else None,
                    },
                    "attempted_real_evaluations": attempted,
                    "initial_population_fingerprints": fingerprints,
                }
            )
            continue
        assert real is not None and surrogate is not None
        raw: dict[str, Any] = {}
        differences: dict[str, Any] = {}
        for name, keys in difference_fields.items():
            real_value = _metric(real, *keys)
            surrogate_value = _metric(surrogate, *keys)
            raw[name] = {real_arm: real_value, surrogate_arm: surrogate_value}
            if isinstance(real_value, (int, float)) and isinstance(surrogate_value, (int, float)):
                differences[f"{surrogate_arm}_minus_{real_arm}"] = differences.get(
                    f"{surrogate_arm}_minus_{real_arm}", {}
                )
                differences[f"{surrogate_arm}_minus_{real_arm}"][name] = float(surrogate_value) - float(real_value)
        raw["surrogate_training_duration_sec"] = _metric(
            surrogate, "surrogate", "training_duration_sec"
        )
        raw["evaluation_normalized_hv_auc"] = {
            real_arm: _metric(real, "evaluation_normalized_hv_auc", "value"),
            surrogate_arm: _metric(surrogate, "evaluation_normalized_hv_auc", "value"),
        }
        pair_rows.append(
            {
                "case": case_id,
                "seed": seed,
                "attempted_real_evaluations": attempted,
                "initial_population_fingerprints": fingerprints,
                "raw": raw,
                "differences": differences,
            }
        )
    aggregate: dict[str, Any] = {}
    for case_id in sorted({row["case"] for row in pair_rows}):
        case_rows = [row for row in pair_rows if row["case"] == case_id]
        metrics: dict[str, list[float]] = defaultdict(list)
        for row in case_rows:
            for direction, values in row["differences"].items():
                for name, value in values.items():
                    metrics[f"{direction}.{name}"].append(float(value))
        aggregate[case_id] = {name: _descriptive(values) for name, values in sorted(metrics.items())}
    return {
        "interpretation_policy": (
            "Raw values and paired descriptive differences only; no ordering, inferential test, "
            "decision threshold, or scientific acceptance claim is produced."
        ),
        "arm_roles": {"real": real_arm, "surrogate": surrogate_arm},
        "included_pairs": pair_rows,
        "excluded_pairs_retained": excluded,
        "descriptive_aggregate_by_case": aggregate,
        "tool_gaps": collection.get("tool_gaps", {}),
    }


def _format_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, float):
        return f"{value:.8g}"
    return str(value)


def _report_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        f"# Benchmark report: {report['run_id']}",
        "",
        f"- Suite: `{report['suite']}`",
        f"- Purpose: `{report['purpose']}`",
        f"- Generated: `{report['generated_utc']}`",
        f"- Collection: `{report['collection']}`",
        "",
    ]
    if report["purpose"] == "structural":
        structural = report["structural"]
        lines.extend(
            [
                "## Structural contract",
                "",
                f"Contract satisfied: `{str(structural['contract_satisfied']).lower()}`",
                "",
                "| Check | Cell | Result |",
                "|---|---|---|",
            ]
        )
        for item in structural["checks"]:
            lines.append(
                f"| {item['check']} | `{item['cell_id']}` | "
                f"{'ok' if item['ok'] else 'not satisfied'} |"
            )
    else:
        performance = report["performance"]
        lines.extend(
            [
                "## Descriptive paired output",
                "",
                performance["interpretation_policy"],
                "",
                "| Case | Seed | Real attempted | Surrogate attempted | Final HV (real) | Final HV (surrogate) |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        real_arm = performance["arm_roles"]["real"]
        surrogate_arm = performance["arm_roles"]["surrogate"]
        for row in performance["included_pairs"]:
            raw = row["raw"]["final_cumulative_hypervolume"]
            attempted = row["attempted_real_evaluations"]
            lines.append(
                f"| {row['case']} | {row['seed']} | {attempted[real_arm]} | "
                f"{attempted[surrogate_arm]} | {_format_value(raw[real_arm])} | "
                f"{_format_value(raw[surrogate_arm])} |"
            )
        lines.extend(
            [
                "",
                f"Excluded paired cells retained in raw evidence: {len(performance['excluded_pairs_retained'])}.",
            ]
        )
    lines.extend(
        [
            "",
            "## Public-tool gaps",
            "",
        ]
    )
    for name, reason in report.get("tool_gaps", {}).items():
        lines.append(f"- `{name}`: {reason}")
    return "\n".join(lines) + "\n"


def report_run(paths: Paths, run_id: str) -> tuple[Path, Path, dict[str, Any]]:
    run_root, spec, _state = load_run(paths, run_id)
    verify_run_inputs(paths, spec, verify_automation=False, verify_config=False)
    collection_path, collection = _latest_collection(run_root)
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "suite": spec["suite"],
        "purpose": spec["purpose"],
        "generated_utc": utc_now(),
        "spec_sha256": spec["spec_sha256"],
        "collection": str(collection_path.relative_to(run_root)),
        "collection_sha256": file_sha256(collection_path),
        "collector": collection.get("collector"),
        "tool_gaps": collection.get("tool_gaps", {}),
        "validity_by_cell": {
            cell_id: {
                "execution_status": cell.get("execution_status"),
                "exclusion_reason": cell.get("exclusion_reason"),
                "validity": cell.get("validity"),
                "public_api_issues": cell.get("public_api_issues", []),
            }
            for cell_id, cell in collection["cells"].items()
        },
    }
    if spec["purpose"] == "structural":
        report["structural"] = _structural_report(spec, collection)
    else:
        report["performance"] = _performance_report(spec, collection)
    report_dir = _new_sequence_dir(run_root / "reports", "report")
    json_path = report_dir / "report.json"
    markdown_path = report_dir / "report.md"
    write_new_json(json_path, _json_safe(report))
    markdown = _report_markdown(report)
    _write_new_text(markdown_path, markdown)
    atomic_write_json(run_root / "report.json", _json_safe(report))
    atomic_write_text(run_root / "report.md", markdown)
    atomic_write_json(
        run_root / "report_index.json",
        {
            "schema_version": SCHEMA_VERSION,
            "latest_json": str(json_path.relative_to(run_root)),
            "latest_markdown": str(markdown_path.relative_to(run_root)),
            "json_sha256": file_sha256(json_path),
            "markdown_sha256": file_sha256(markdown_path),
            "updated_utc": utc_now(),
        },
    )
    return json_path, markdown_path, report


def summarize_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Return a bounded planning view that omits expanded command lines."""
    by_case: dict[str, dict[str, int]] = {}
    smoke_count = 0
    measured_count = 0
    attempted_total = 0
    for cell in plan.get("cells", []):
        case_id = str(cell.get("case"))
        bucket = by_case.setdefault(
            case_id,
            {"cells": 0, "smoke_cells": 0, "measured_cells": 0, "planned_attempted_evaluations": 0},
        )
        attempted = int(cell.get("planned_attempted_evaluations", 0))
        kind = str(cell.get("kind"))
        bucket["cells"] += 1
        bucket["planned_attempted_evaluations"] += attempted
        attempted_total += attempted
        if kind == "smoke":
            smoke_count += 1
            bucket["smoke_cells"] += 1
        else:
            measured_count += 1
            bucket["measured_cells"] += 1
    return _json_safe(
        {
            "schema_version": plan.get("schema_version", SCHEMA_VERSION),
            "view": "plan-summary",
            "suite": plan.get("suite"),
            "purpose": plan.get("purpose"),
            "selection": plan.get("selection", {}),
            "fail_fast": plan.get("fail_fast"),
            "cells": {
                "total": int(plan.get("cell_count", smoke_count + measured_count)),
                "smoke": smoke_count,
                "measured": measured_count,
                "planned_attempted_evaluations": attempted_total,
                "by_case": by_case,
            },
            "estimates": plan.get("estimates", {}),
            "prerequisites": plan.get("prerequisites", {}),
            "detail": {
                "available_with": "plan --full-json",
                "omitted": ["expanded cell objects", "planned command lines"],
            },
        }
    )


def _tail_text(value: Any, limit: int = 600) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) <= limit:
        return text
    return f"...{text[-limit:]}"


def summarize_preflight(result: Mapping[str, Any]) -> dict[str, Any]:
    """Return check outcomes without embedding commands, stdout, or stderr."""
    checks: list[dict[str, Any]] = []
    for check in result.get("checks", []):
        compact: dict[str, Any] = {
            "name": check.get("name"),
            "ok": bool(check.get("ok")),
        }
        if check.get("error"):
            compact["error"] = check.get("error")
        details = check.get("details")
        if isinstance(details, Mapping):
            selected = {
                key: details.get(key)
                for key in (
                    "kind",
                    "variable",
                    "exists",
                    "available",
                    "device",
                    "returncode",
                    "timed_out",
                    "free_mib",
                    "required_mib",
                )
                if key in details
            }
            if selected:
                compact["details"] = selected
            if not compact["ok"]:
                diagnostic = _tail_text(details.get("stderr")) or _tail_text(details.get("stdout"))
                if diagnostic:
                    compact["diagnostic_tail"] = diagnostic
        checks.append(compact)
    package = result.get("package", {})
    plan = summarize_plan(result.get("plan", {}))
    plan.pop("detail", None)
    passed = sum(1 for check in checks if check["ok"])
    return _json_safe(
        {
            "schema_version": result.get("schema_version", SCHEMA_VERSION),
            "view": "preflight-summary",
            "suite": result.get("suite"),
            "ok": bool(result.get("ok")),
            "checked_utc": result.get("checked_utc"),
            "checks": {
                "total": len(checks),
                "passed": passed,
                "failed": len(checks) - passed,
                "items": checks,
            },
            "package": {
                "version": package.get("version"),
                "origin": package.get("origin"),
                "python": package.get("python"),
                "python_version": str(package.get("python_version", "")).splitlines()[0],
            },
            "plan": plan,
            "detail": {
                "available_with": "preflight --full-json",
                "omitted": ["command stdout/stderr", "full package fingerprints", "expanded plan cells"],
            },
        }
    )


def summarize_run_state(run_root: Path, run_id: str, state: Mapping[str, Any]) -> dict[str, Any]:
    """Return current cell status and only actionable attempt failures."""
    by_status: dict[str, int] = defaultdict(int)
    attention: list[dict[str, Any]] = []
    cells = state.get("cells", {})
    for cell_id, cell in cells.items():
        status = str(cell.get("status", "unknown"))
        by_status[status] += 1
        if status == "completed":
            continue
        attempts = cell.get("attempts") or []
        latest = attempts[-1] if attempts else {}
        item: dict[str, Any] = {
            "cell_id": cell_id,
            "status": status,
            "error": latest.get("error"),
            "attempt": latest.get("attempt"),
        }
        commands = latest.get("commands") or []
        if commands:
            item["latest_command_metadata"] = commands[-1]
        attention.append(item)
    state_status = str(state.get("status", "unknown"))
    runs_dir = run_root.resolve().parent
    next_command = (
        ["--runs-dir", str(runs_dir), "collect", "--run-id", run_id]
        if state_status == "completed"
        else ["--runs-dir", str(runs_dir), "resume", "--run-id", run_id]
    )
    return _json_safe(
        {
            "schema_version": state.get("schema_version", SCHEMA_VERSION),
            "view": "run-summary",
            "run_id": run_id,
            "runs_dir": str(runs_dir),
            "run_root": str(run_root.resolve()),
            "execution_state": state_status,
            "updated_utc": state.get("updated_utc"),
            "cells": {"total": len(cells), "by_status": dict(sorted(by_status.items()))},
            "attention": attention,
            "run_state": str(run_root / "run_state.json"),
            "next_command": next_command,
        }
    )


def summarize_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """Return bounded validity and result evidence without fingerprints or raw rows."""
    status_counts: dict[str, int] = defaultdict(int)
    evaluation_totals = {
        "planned": 0,
        "attempted": 0,
        "completed": 0,
        "failed": 0,
        "timeouts": 0,
        "all_infinite_generations": 0,
    }
    attention: list[dict[str, Any]] = []
    validity_keys = {
        "planned": "planned_real_evaluations",
        "attempted": "attempted_real_evaluations",
        "completed": "completed_candidate_evaluations",
        "failed": "failed_candidate_evaluations",
        "timeouts": "timeout_candidate_evaluations",
        "all_infinite_generations": "all_infinite_generation_count",
    }
    for cell_id, cell in report.get("validity_by_cell", {}).items():
        status = str(cell.get("execution_status", "unknown"))
        status_counts[status] += 1
        validity = cell.get("validity") or {}
        for summary_key, source_key in validity_keys.items():
            value = validity.get(source_key)
            if isinstance(value, (int, float)):
                evaluation_totals[summary_key] += int(value)
        issues = list(cell.get("public_api_issues") or [])
        concerns: list[str] = []
        if status != "completed":
            concerns.append(f"execution_status={status}")
        for source_key, label in (
            ("failed_candidate_evaluations", "failed candidates"),
            ("timeout_candidate_evaluations", "candidate timeouts"),
            ("all_infinite_generation_count", "all-infinite generations"),
        ):
            count = int(validity.get(source_key, 0) or 0)
            if count:
                concerns.append(f"{count} {label}")
        warnings = list(validity.get("yadof_check_warnings") or [])
        if warnings:
            concerns.append(f"{len(warnings)} yadof check warnings")
        if issues:
            concerns.append(f"{len(issues)} public API issues")
        if concerns:
            attention.append(
                {
                    "cell_id": cell_id,
                    "concerns": concerns,
                    "exclusion_reason": cell.get("exclusion_reason"),
                    "public_api_issues": issues,
                }
            )
    summary: dict[str, Any] = {
        "schema_version": report.get("schema_version", SCHEMA_VERSION),
        "view": "report-summary",
        "run_id": report.get("run_id"),
        "suite": report.get("suite"),
        "purpose": report.get("purpose"),
        "generated_utc": report.get("generated_utc"),
        "validity": {
            "cells_by_execution_status": dict(sorted(status_counts.items())),
            "evaluation_totals": evaluation_totals,
            "attention": attention,
        },
        "tool_gaps": report.get("tool_gaps", {}),
    }
    if report.get("purpose") == "structural":
        structural = report.get("structural", {})
        failed_checks = [
            {"check": item.get("check"), "cell_id": item.get("cell_id")}
            for item in structural.get("checks", [])
            if not item.get("ok")
        ]
        summary["structural"] = {
            "contract_satisfied": bool(structural.get("contract_satisfied")),
            "check_count": len(structural.get("checks", [])),
            "failed_checks": failed_checks,
        }
    else:
        performance = report.get("performance", {})
        real_arm = performance.get("arm_roles", {}).get("real")
        surrogate_arm = performance.get("arm_roles", {}).get("surrogate")
        difference_key = f"{surrogate_arm}_minus_{real_arm}"
        pairs: list[dict[str, Any]] = []
        for row in performance.get("included_pairs", []):
            raw = row.get("raw", {})
            differences = row.get("differences", {}).get(difference_key, {})
            metrics: dict[str, Any] = {}
            for metric in (
                "final_cumulative_hypervolume",
                "evaluator_elapsed_sec_sum",
            ):
                if metric in raw:
                    metrics[metric] = {
                        "by_arm": raw.get(metric),
                        "surrogate_minus_real": differences.get(metric),
                    }
            metrics["surrogate_training_duration_sec"] = raw.get(
                "surrogate_training_duration_sec"
            )
            pairs.append(
                {
                    "case": row.get("case"),
                    "seed": row.get("seed"),
                    "attempted_real_evaluations": row.get("attempted_real_evaluations"),
                    "metrics": metrics,
                }
            )
        aggregate = {
            case_id: {
                name: values
                for name, values in metrics.items()
                if name.endswith(".final_cumulative_hypervolume")
                or name.endswith(".evaluator_elapsed_sec_sum")
            }
            for case_id, metrics in performance.get(
                "descriptive_aggregate_by_case", {}
            ).items()
        }
        summary["performance"] = {
            "interpretation_policy": performance.get("interpretation_policy"),
            "arm_roles": performance.get("arm_roles", {}),
            "included_pair_count": len(pairs),
            "excluded_pair_count": len(performance.get("excluded_pairs_retained", [])),
            "pairs": pairs,
            "excluded_pairs": performance.get("excluded_pairs_retained", []),
            "descriptive_aggregate_by_case": aggregate,
        }
    return _json_safe(summary)


def _artifact_entry(path: Path, role: str, read_policy: str) -> dict[str, Any]:
    exists = path.is_file()
    return {
        "role": role,
        "path": str(path),
        "exists": exists,
        "size_bytes": path.stat().st_size if exists else None,
        "read_policy": read_policy,
    }


def inspect_run(paths: Paths, run_id: str) -> dict[str, Any]:
    """Build the bounded first-read view for an existing run."""
    run_root, spec, state = load_run(paths, run_id)
    report_markdown = run_root / "report.md"
    report_json = run_root / "report.json"
    metrics_json = run_root / "metrics.json"
    run_summary = summarize_run_state(run_root, run_id, state)
    run_summary.pop("schema_version", None)
    run_summary.pop("view", None)
    results = summarize_report(read_json(report_json)) if report_json.is_file() else None
    artifacts = [
        _artifact_entry(
            report_markdown,
            "concise human/agent report",
            "read first when the structured summary needs narrative context",
        ),
        _artifact_entry(
            report_json,
            "complete stable report",
            "query targeted fields only; do not repeatedly read the whole file",
        ),
        _artifact_entry(
            metrics_json,
            "large collected public-API evidence",
            "never read whole; query one cell and field only after the report is insufficient",
        ),
        _artifact_entry(
            run_root / "run_state.json",
            "execution state and attempt index",
            "query a specific non-completed cell during diagnosis",
        ),
        _artifact_entry(
            run_root / "run_spec.json",
            "immutable provenance",
            "read only when verifying identity or reproducing a run",
        ),
        _artifact_entry(
            run_root / "matrix.json",
            "expanded immutable cell matrix",
            "read only when one planned cell or command must be verified",
        ),
    ]
    if results is not None:
        next_commands: list[list[str]] = []
    elif metrics_json.is_file():
        next_commands = [["--runs-dir", str(paths.runs), "report", "--run-id", run_id]]
    elif state.get("status") == "completed":
        next_commands = [["--runs-dir", str(paths.runs), "collect", "--run-id", run_id]]
    else:
        next_commands = [
            ["--runs-dir", str(paths.runs), "collect", "--run-id", run_id],
            ["--runs-dir", str(paths.runs), "resume", "--run-id", run_id],
        ]
    return _json_safe(
        {
            "schema_version": SCHEMA_VERSION,
            "view": "agent-summary",
            "run": {
                **run_summary,
                "suite": spec.get("suite"),
                "purpose": spec.get("purpose"),
            },
            "results": results,
            "artifacts": artifacts,
            "next_commands": next_commands,
            "progressive_disclosure": (
                "Use this summary first, then report.md, then targeted report.json fields. "
                "Read one cell/log only for diagnosis; never load metrics.json wholesale."
            ),
        }
    )
