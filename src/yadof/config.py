"""Package defaults and validated workspace configuration loading."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
import os
from pathlib import Path
from types import MappingProxyType, ModuleType
import uuid

from .workspace import WorkspaceContext, resolve_workspace


class ConfigError(ValueError):
    """Raised when a workspace configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class SettingSpec:
    """One authoritative core setting declaration."""

    name: str
    default: object
    kind: str
    reload_policy: str = "generation"
    path_policy: str | None = None
    choices: tuple[object, ...] = ()


def _spec(
    name: str,
    default: object,
    kind: str,
    *,
    reload_policy: str = "generation",
    path_policy: str | None = None,
    choices: tuple[object, ...] = (),
) -> SettingSpec:
    return SettingSpec(name, default, kind, reload_policy, path_policy, choices)


_CORE_SETTING_SPECS: tuple[SettingSpec, ...] = (
    # Workspace paths. Relative values are rooted at the selected workspace.
    _spec("JOB_TEMPLATE_DIR", "job_template", "path", path_policy="workspace_relative"),
    _spec("JOBS_DIR", "jobs", "path", path_policy="workspace_relative"),
    _spec("RECORDED_DATA_DIR", "recorded_data", "path", path_policy="workspace_relative"),
    _spec("SURROGATE_CHECKPOINT_DIR", ".yadof/surrogate/checkpoints", "path", path_policy="workspace_relative"),
    _spec("LOGS_DIR", ".yadof/logs", "path", path_policy="workspace_relative"),
    _spec("TOOL_OUTPUT_DIR", ".yadof/tool_output", "path", path_policy="workspace_relative"),
    _spec("FAST_EVALUATION_SCRATCH_DIR", ".yadof/fast_scratch", "path", path_policy="workspace_relative"),
    # Reliable immutable-segment history recorder. These values are frozen for
    # one active campaign even when other workspace config is hot-reloaded.
    _spec("HISTORY_SEGMENT_MAX_CANDIDATES", 16, "positive_int", reload_policy="session_frozen"),
    _spec("HISTORY_SEGMENT_TARGET_BYTES", 16 * 1024 * 1024, "positive_int", reload_policy="session_frozen"),
    _spec("HISTORY_MAX_CANDIDATE_BYTES", 64 * 1024 * 1024, "positive_int", reload_policy="session_frozen"),
    _spec("HISTORY_UNPUBLISHED_MAX_CANDIDATES", 32, "positive_int", reload_policy="session_frozen"),
    _spec("HISTORY_UNPUBLISHED_MAX_BYTES", 512 * 1024 * 1024, "positive_int", reload_policy="session_frozen"),
    _spec("HISTORY_WRITER_MAX_CONSECUTIVE_FAILURES", 3, "positive_int", reload_policy="session_frozen"),
    # Evaluation backend.
    _spec("EVALUATION_MODE", "local", "choice", choices=("fast", "local", "distributed")),
    _spec("EVALUATION_TIMEOUT_SEC", 6 * 60 * 60, "positive_real"),
    _spec("LOCAL_EVALUATION_MAX_WORKERS", 8, "positive_int"),
    _spec("LOCAL_RESOURCE_AUTODETECT_ENABLED", True, "bool"),
    _spec("LOCAL_RESOURCE_SYSTEM_RESERVE_FRACTION", 0.15, "fraction"),
    _spec("FAST_EVALUATION_MAX_WORKERS", 8, "positive_int"),
    _spec("FAST_RESOURCE_AUTODETECT_ENABLED", True, "bool"),
    _spec("FAST_RESOURCE_SYSTEM_RESERVE_FRACTION", 0.15, "fraction"),
    _spec("FAST_EVALUATION_CPUS_PER_WORKER", 1, "positive_int"),
    _spec("FAST_EVALUATION_MEMORY_MIB_PER_WORKER", 512, "positive_int"),
    _spec("FAST_EVALUATION_SCRATCH_DISK_KIB_PER_WORKER", 1024, "positive_int"),
    # HTCondor backend.
    _spec("HTCONDOR_SUBMIT_EXE", "condor_submit", "string"),
    _spec("HTCONDOR_REMOVE_EXE", "condor_rm", "string"),
    _spec("HTCONDOR_HISTORY_EXE", "condor_history", "string"),
    _spec("HTCONDOR_POLL_SEC", 30.0, "positive_real"),
    _spec("HTCONDOR_REQUEST_CPUS", 1, "positive_int"),
    _spec("HTCONDOR_REQUEST_MEMORY", "4GB", "resource"),
    _spec("HTCONDOR_REQUEST_DISK", "2GB", "resource"),
    _spec("HTCONDOR_RESOURCE_AUTODETECT_ENABLED", True, "bool"),
    _spec("HTCONDOR_RESOURCE_BOOTSTRAP_MULTIPLIER", 2.0, "positive_real"),
    _spec("HTCONDOR_RESOURCE_TRIM_TOP_FRACTION", 0.05, "fraction"),
    _spec("YADOF_RESOURCE_RETRY_DOUBLINGS", 4, "nonnegative_int"),
    _spec("HTCONDOR_REQUEST_DISK_MULTIPLIER", 1.0, "positive_real"),
    _spec("HTCONDOR_JOB_TIMEOUT_MODE", "auto", "choice", choices=("auto", "fixed")),
    _spec("HTCONDOR_JOB_TIMEOUT_SEC", 60 * 60, "positive_int"),
    _spec("HTCONDOR_JOB_TIMEOUT_MULTIPLIER", 2.0, "positive_real"),
    _spec("HTCONDOR_JOB_TIMEOUT_TRIM_TOP_FRACTION", 0.10, "fraction"),
    _spec("HTCONDOR_LOAD_PROFILE", True, "bool"),
    _spec("HTCONDOR_RUN_AS_OWNER", False, "bool"),
    _spec("HTCONDOR_REQUIREMENTS", '(OpSys == "WINDOWS")', "string"),
    _spec("HTCONDOR_ALLOWED_MACHINES", (), "string_sequence"),
    _spec("HTCONDOR_EXCLUDED_MACHINES", (), "string_sequence"),
    _spec("HTCONDOR_ENVIRONMENT", "USERPROFILE=._home HOME=._home TEMP=._tmp TMP=._tmp", "string"),
    # Optimizer.
    _spec("OPTIMIZE_POPULATION_SIZE", 200, "positive_int"),
    _spec("OPTIMIZE_SMOKE_TEST_ENABLED", True, "bool"),
    _spec("OPTIMIZE_RANDOM_SEED", 20260624, "nonnegative_int"),
    _spec("OPTIMIZE_ARCHIVE_KEY_DECIMALS", 10, "nonnegative_int"),
    _spec("OPTIMIZE_SURROGATE_MAX_TRAINING_LAG", 1, "nonnegative_int"),
    # Cross-component viewer diagnostic policy.
    _spec("SURROGATE_RELATIVE_ERROR_EPS", 1e-8, "positive_real"),
)

_CORE_SETTING_BY_NAME = MappingProxyType(
    {spec.name: spec for spec in _CORE_SETTING_SPECS}
)
if len(_CORE_SETTING_BY_NAME) != len(_CORE_SETTING_SPECS):
    raise RuntimeError("core configuration schema contains duplicate names")
DEFAULT_CONFIG: Mapping[str, object] = MappingProxyType(
    {spec.name: spec.default for spec in _CORE_SETTING_SPECS}
)

_PATH_NAMES = frozenset(
    spec.name for spec in _CORE_SETTING_SPECS if spec.path_policy is not None
)


@dataclass(frozen=True, slots=True)
class LoadedConfig:
    """Immutable effective settings, their sources, and resolved workspace paths."""

    workspace: WorkspaceContext
    values: Mapping[str, object]
    sources: Mapping[str, str]

    def __getattr__(self, name: str) -> object:
        try:
            return self.values[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __getitem__(self, name: str) -> object:
        return self.values[name]

    def source_for(self, name: str) -> str:
        try:
            return self.sources[name]
        except KeyError as exc:
            raise KeyError(f"unknown config name: {name}") from exc

    def as_dict(self) -> dict[str, object]:
        return dict(self.values)

    def describe(self) -> str:
        """Format effective values with their package/workspace/CLI precedence."""

        lines = [f"workspace = {self.workspace.root}"]
        for spec in _CORE_SETTING_SPECS:
            lines.append(
                f"{spec.name} = {self.values[spec.name]!r}  # "
                f"{self.sources[spec.name]}; reload={spec.reload_policy}"
            )
        return "\n".join(lines)


def _load_workspace_values(config_file: Path) -> dict[str, object]:
    if not config_file.is_file():
        raise ConfigError(f"workspace config file does not exist: {config_file}")
    module = ModuleType(f"_yadof_workspace_config_{uuid.uuid4().hex}")
    module.__file__ = str(config_file)
    module.__package__ = ""
    try:
        code = compile(config_file.read_bytes(), str(config_file), "exec")
        exec(code, module.__dict__)
    except (Exception, SystemExit) as exc:
        raise ConfigError(f"failed to load workspace config {config_file}: {exc}") from exc
    return {
        name: value
        for name, value in vars(module).items()
        if name.isupper() and not name.startswith("_")
    }


def _real(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{name} must be a real number, got {type(value).__name__}")
    number = float(value)
    if not math.isfinite(number):
        raise ConfigError(f"{name} must be finite")
    return number


def _validate_value(name: str, value: object) -> object:
    spec = _CORE_SETTING_BY_NAME.get(name)
    if spec is None:
        raise ConfigError(f"no validator is registered for config setting {name}")
    kind = spec.kind
    if kind == "path":
        if not isinstance(value, (str, os.PathLike)) or not str(value):
            raise ConfigError(f"{name} must be a non-empty path")
        return value
    if kind == "bool":
        if not isinstance(value, bool):
            raise ConfigError(f"{name} must be bool, got {type(value).__name__}")
        return value
    if kind in {"positive_int", "nonnegative_int"}:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigError(f"{name} must be an integer, got {type(value).__name__}")
        minimum = 1 if kind == "positive_int" else 0
        if value < minimum:
            raise ConfigError(f"{name} must be >= {minimum}")
        return value
    if kind in {"positive_real", "nonnegative_real"}:
        number = _real(value, name)
        if number <= 0.0 and kind == "positive_real":
            raise ConfigError(f"{name} must be > 0")
        if number < 0.0 and kind == "nonnegative_real":
            raise ConfigError(f"{name} must be >= 0")
        return value
    if kind == "fraction":
        number = _real(value, name)
        if not 0.0 <= number <= 1.0:
            raise ConfigError(f"{name} must be between 0 and 1")
        return value
    if kind == "string":
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(f"{name} must be a non-empty string")
        return value
    if kind == "string_sequence":
        if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
            raise ConfigError(f"{name} must be a sequence of strings")
        result = tuple(value)
        if not all(isinstance(item, str) and item for item in result):
            raise ConfigError(f"{name} must contain only non-empty strings")
        return result
    if kind == "resource":
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            raise ConfigError(f"{name} must be a resource string or positive integer")
        if isinstance(value, str) and not value.strip():
            raise ConfigError(f"{name} must not be empty")
        if isinstance(value, int) and value <= 0:
            raise ConfigError(f"{name} must be positive")
        return value
    if kind == "choice":
        if value not in spec.choices:
            choices = ", ".join(repr(item) for item in spec.choices)
            raise ConfigError(f"{name} must be one of: {choices}")
        return value
    raise ConfigError(f"no validator is registered for config setting {name}")


def _merge_layer(
    values: dict[str, object],
    sources: dict[str, str],
    layer: Mapping[str, object],
    source: str,
) -> None:
    unknown = sorted(set(layer) - set(DEFAULT_CONFIG))
    if unknown:
        raise ConfigError(f"unknown config setting(s): {', '.join(unknown)}")
    for name, raw_value in layer.items():
        values[name] = _validate_value(name, raw_value)
        sources[name] = source


def _validate_task_paths(workspace: WorkspaceContext) -> None:
    if not workspace.root.is_dir():
        raise ConfigError(f"workspace directory does not exist: {workspace.root}")
    if not workspace.submit_dir.is_dir():
        raise ConfigError(
            f"workspace submit directory does not exist: {workspace.submit_dir}"
        )
    if not workspace.job_template_dir.is_dir():
        raise ConfigError(
            f"workspace job_template directory does not exist: {workspace.job_template_dir}"
        )
    misplaced = [
        name
        for name in ("calc_cost.py", "optimization.py")
        if (workspace.job_template_dir / name).exists()
    ]
    if misplaced:
        raise ConfigError(
            "submit-only source must not be placed in job_template: "
            + ", ".join(misplaced)
            + "; move it below the fixed workspace submit/ directory"
        )
    job_required = ("parameters_constraints.py", "workflow.py")
    job_missing = [
        name
        for name in job_required
        if not (workspace.job_template_dir / name).is_file()
    ]
    if job_missing:
        raise ConfigError(
            "workspace job_template is missing required task file(s): "
            + ", ".join(job_missing)
        )
    submit_required = (
        ("calc_cost.py", "optimization.py")
        if workspace.requires_optimization_source
        else ("calc_cost.py",)
    )
    submit_missing = [
        name for name in submit_required if not (workspace.submit_dir / name).is_file()
    ]
    if submit_missing:
        raise ConfigError(
            "workspace submit is missing required submit-side file(s): "
            + ", ".join(submit_missing)
        )


def _paths_overlap(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def _validate_workspace_path_boundaries(workspace: WorkspaceContext) -> None:
    paths = {
        "submit": workspace.submit_dir,
        "job_template": workspace.job_template_dir,
        "jobs": workspace.jobs_dir,
        "recorded_data": workspace.recorded_data_dir,
        "surrogate checkpoints": workspace.surrogate_checkpoint_dir,
        "logs": workspace.logs_dir,
        "tool output": workspace.tool_output_dir,
        "fast scratch": workspace.fast_evaluation_scratch_dir,
    }
    names = tuple(paths)
    for index, left_name in enumerate(names):
        for right_name in names[index + 1 :]:
            left = paths[left_name]
            right = paths[right_name]
            if _paths_overlap(left, right):
                raise ConfigError(
                    f"workspace paths must not overlap: {left_name}={left} and "
                    f"{right_name}={right}"
                )


def load_config(
    workspace: WorkspaceContext | str | os.PathLike[str] | None = None,
    *,
    overrides: Mapping[str, object] | None = None,
    validate_task_paths: bool = True,
) -> LoadedConfig:
    """Load package defaults, workspace config, then non-mutating overrides."""

    base_workspace = resolve_workspace(workspace)
    values = {
        spec.name: _validate_value(spec.name, spec.default)
        for spec in _CORE_SETTING_SPECS
    }
    sources = {name: "package default" for name in values}
    default_workspace = WorkspaceContext.from_path(base_workspace.root)
    for name, path in base_workspace.path_settings().items():
        if path != default_workspace.path_settings()[name]:
            values[name] = path
            sources[name] = "explicit workspace context"
    _merge_layer(
        values,
        sources,
        _load_workspace_values(base_workspace.config_file),
        f"workspace config: {base_workspace.config_file}",
    )
    if overrides:
        _merge_layer(values, sources, overrides, "temporary override")

    if (
        int(values["HISTORY_SEGMENT_MAX_CANDIDATES"])
        > int(values["HISTORY_UNPUBLISHED_MAX_CANDIDATES"])
    ):
        raise ConfigError(
            "HISTORY_SEGMENT_MAX_CANDIDATES must not exceed "
            "HISTORY_UNPUBLISHED_MAX_CANDIDATES"
        )
    if (
        int(values["HISTORY_MAX_CANDIDATE_BYTES"])
        > int(values["HISTORY_UNPUBLISHED_MAX_BYTES"])
    ):
        raise ConfigError(
            "HISTORY_MAX_CANDIDATE_BYTES must not exceed "
            "HISTORY_UNPUBLISHED_MAX_BYTES"
        )

    path_values = {name: values[name] for name in _PATH_NAMES}
    effective_workspace = base_workspace.with_path_settings(path_values)  # type: ignore[arg-type]
    for name, path in effective_workspace.path_settings().items():
        values[name] = path
    _validate_workspace_path_boundaries(effective_workspace)
    if validate_task_paths:
        _validate_task_paths(effective_workspace)
    return LoadedConfig(
        workspace=effective_workspace,
        values=MappingProxyType(values),
        sources=MappingProxyType(sources),
    )


def format_effective_config(config: LoadedConfig) -> str:
    """Return a stable human-readable effective config and precedence listing."""

    return config.describe()


__all__ = [
    "ConfigError",
    "DEFAULT_CONFIG",
    "LoadedConfig",
    "format_effective_config",
    "load_config",
]
