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


_DEFAULT_ITEMS: tuple[tuple[str, object], ...] = (
    # Workspace paths. Relative values are rooted at the selected workspace.
    ("JOB_TEMPLATE_DIR", "job_template"),
    ("JOBS_DIR", "jobs"),
    ("RECORDED_DATA_DIR", "recorded_data"),
    ("SURROGATE_CHECKPOINT_DIR", ".yadof/surrogate/checkpoints"),
    ("LOGS_DIR", ".yadof/logs"),
    ("TOOL_OUTPUT_DIR", ".yadof/tool_output"),
    ("FAST_EVALUATION_SCRATCH_DIR", ".yadof/fast_scratch"),
    # Best-effort immutable-segment history recorder. These values are frozen for
    # one active campaign even when other workspace config is hot-reloaded.
    ("HISTORY_SEGMENT_MAX_CANDIDATES", 16),
    ("HISTORY_SEGMENT_TARGET_BYTES", 16 * 1024 * 1024),
    ("HISTORY_MAX_CANDIDATE_BYTES", 64 * 1024 * 1024),
    ("HISTORY_UNPUBLISHED_MAX_CANDIDATES", 32),
    ("HISTORY_UNPUBLISHED_MAX_BYTES", 512 * 1024 * 1024),
    ("HISTORY_WRITER_MAX_CONSECUTIVE_FAILURES", 3),
    ("HISTORY_WRITER_SHUTDOWN_TIMEOUT_SEC", 5.0),
    # Evaluation backend.
    ("EVALUATION_MODE", "local"),
    ("EVALUATION_TIMEOUT_SEC", 6 * 60 * 60),
    ("LOCAL_EVALUATION_MAX_WORKERS", 8),
    ("LOCAL_RESOURCE_AUTODETECT_ENABLED", True),
    ("LOCAL_RESOURCE_SYSTEM_RESERVE_FRACTION", 0.15),
    ("FAST_EVALUATION_MAX_WORKERS", 8),
    ("FAST_RESOURCE_AUTODETECT_ENABLED", True),
    ("FAST_RESOURCE_SYSTEM_RESERVE_FRACTION", 0.15),
    ("FAST_EVALUATION_CPUS_PER_WORKER", 1),
    ("FAST_EVALUATION_MEMORY_MIB_PER_WORKER", 512),
    ("FAST_EVALUATION_SCRATCH_DISK_KIB_PER_WORKER", 1024),
    # HTCondor backend.
    ("HTCONDOR_SUBMIT_EXE", "condor_submit"),
    ("HTCONDOR_REMOVE_EXE", "condor_rm"),
    ("HTCONDOR_HISTORY_EXE", "condor_history"),
    ("HTCONDOR_POLL_SEC", 30.0),
    ("HTCONDOR_REQUEST_CPUS", 1),
    ("HTCONDOR_REQUEST_MEMORY", "4GB"),
    ("HTCONDOR_REQUEST_DISK", "2GB"),
    ("HTCONDOR_RESOURCE_AUTODETECT_ENABLED", True),
    ("HTCONDOR_RESOURCE_BOOTSTRAP_MULTIPLIER", 2.0),
    ("HTCONDOR_RESOURCE_TRIM_TOP_FRACTION", 0.05),
    ("YADOF_RESOURCE_RETRY_DOUBLINGS", 4),
    ("HTCONDOR_REQUEST_DISK_MULTIPLIER", 1.0),
    ("HTCONDOR_JOB_TIMEOUT_MODE", "auto"),
    ("HTCONDOR_JOB_TIMEOUT_SEC", 60 * 60),
    ("HTCONDOR_JOB_TIMEOUT_MULTIPLIER", 2.0),
    ("HTCONDOR_JOB_TIMEOUT_TRIM_TOP_FRACTION", 0.10),
    ("HTCONDOR_LOAD_PROFILE", True),
    ("HTCONDOR_RUN_AS_OWNER", False),
    ("HTCONDOR_REQUIREMENTS", '(OpSys == "WINDOWS")'),
    ("HTCONDOR_ALLOWED_MACHINES", ()),
    ("HTCONDOR_EXCLUDED_MACHINES", ()),
    ("HTCONDOR_ENVIRONMENT", "USERPROFILE=._home HOME=._home TEMP=._tmp TMP=._tmp"),
    # Optimizer.
    ("OPTIMIZE_POPULATION_SIZE", 200),
    ("OPTIMIZE_SMOKE_TEST_ENABLED", True),
    ("OPTIMIZE_RANDOM_SEED", 20260624),
    ("OPTIMIZE_NSGA3_REF_DIR_METHOD", "das-dennis"),
    ("OPTIMIZE_NSGA3_PARTITIONS", None),
    ("OPTIMIZE_REFILL_ATTEMPTS", 8),
    ("OPTIMIZE_ARCHIVE_KEY_DECIMALS", 10),
    ("OPTIMIZE_CROSSOVER_PROBABILITY", 0.85),
    ("OPTIMIZE_MUTATION_PROBABILITY", 0.35),
    ("OPTIMIZE_CROSSOVER_ETA", 10.0),
    ("OPTIMIZE_MUTATION_ETA", 10.0),
    ("OPTIMIZE_DIM_MUT_PER_INDIVIDUAL", 7),
    # GPSAF surrogate assistance.
    ("OPTIMIZE_SURROGATE_ALPHA", 3),
    ("OPTIMIZE_SURROGATE_BETA", 3),
    ("OPTIMIZE_SURROGATE_GAMMA", 0.5),
    ("OPTIMIZE_SURROGATE_EXPLORATION_FRACTION", 0.10),
    ("OPTIMIZE_SURROGATE_MAX_TRAINING_LAG", 2),
    # Surrogate model.
    ("SURROGATE_RELATIVE_ERROR_EPS", 1e-8),
    ("SURROGATE_CONSTANT_ATOL", 1e-12),
    ("SURROGATE_TARGET_SCALE_FLOOR", 1e-6),
    ("SURROGATE_TORCH_DEVICE", "auto"),
    ("SURROGATE_INR_EPOCHS", 32),
    ("SURROGATE_INR_ENSEMBLE_SIZE", 3),
    ("SURROGATE_INR_BATCH_SIZE", 16),
    ("SURROGATE_INR_LR", 1e-3),
    ("SURROGATE_INR_WEIGHT_DECAY", 1e-5),
    ("SURROGATE_INR_LOSS_BETA", 0.05),
    ("SURROGATE_MAX_NONFINITE_FRACTION", 0.20),
    ("SURROGATE_INR_X_LATENT_DIM", 96),
    ("SURROGATE_INR_FIELD_EMB_DIM", 12),
    ("SURROGATE_INR_COORD_FOURIER_FEATURES", 24),
    ("SURROGATE_INR_HIDDEN_DIM", 192),
    ("SURROGATE_INR_HIDDEN_LAYERS", 3),
    ("SURROGATE_INR_TRAIN_QUERY_CHUNK", 4096),
    ("SURROGATE_INR_TRAIN_QUERY_SAMPLE_COUNT", 8192),
    ("SURROGATE_INR_SAMPLE_BATCH_EVAL", 64),
    ("SURROGATE_INR_QUERY_BATCH_EVAL", 8192),
    ("SURROGATE_INR_BOOTSTRAP_MEMBERS", True),
    ("SURROGATE_INR_BOOTSTRAP_FRACTION", 1.0),
)

DEFAULT_CONFIG: Mapping[str, object] = MappingProxyType(dict(_DEFAULT_ITEMS))

_PATH_NAMES = {
    "JOB_TEMPLATE_DIR",
    "JOBS_DIR",
    "RECORDED_DATA_DIR",
    "SURROGATE_CHECKPOINT_DIR",
    "LOGS_DIR",
    "TOOL_OUTPUT_DIR",
    "FAST_EVALUATION_SCRATCH_DIR",
}
_BOOL_NAMES = {
    "LOCAL_RESOURCE_AUTODETECT_ENABLED",
    "FAST_RESOURCE_AUTODETECT_ENABLED",
    "HTCONDOR_RESOURCE_AUTODETECT_ENABLED",
    "HTCONDOR_LOAD_PROFILE",
    "HTCONDOR_RUN_AS_OWNER",
    "OPTIMIZE_SMOKE_TEST_ENABLED",
    "SURROGATE_INR_BOOTSTRAP_MEMBERS",
}
_POSITIVE_INT_NAMES = {
    "LOCAL_EVALUATION_MAX_WORKERS",
    "FAST_EVALUATION_MAX_WORKERS",
    "FAST_EVALUATION_CPUS_PER_WORKER",
    "FAST_EVALUATION_MEMORY_MIB_PER_WORKER",
    "FAST_EVALUATION_SCRATCH_DISK_KIB_PER_WORKER",
    "HISTORY_SEGMENT_MAX_CANDIDATES",
    "HISTORY_SEGMENT_TARGET_BYTES",
    "HISTORY_MAX_CANDIDATE_BYTES",
    "HISTORY_UNPUBLISHED_MAX_CANDIDATES",
    "HISTORY_UNPUBLISHED_MAX_BYTES",
    "HISTORY_WRITER_MAX_CONSECUTIVE_FAILURES",
    "HTCONDOR_REQUEST_CPUS",
    "HTCONDOR_JOB_TIMEOUT_SEC",
    "OPTIMIZE_POPULATION_SIZE",
    "OPTIMIZE_REFILL_ATTEMPTS",
    "OPTIMIZE_DIM_MUT_PER_INDIVIDUAL",
    "SURROGATE_INR_EPOCHS",
    "SURROGATE_INR_ENSEMBLE_SIZE",
    "SURROGATE_INR_BATCH_SIZE",
    "SURROGATE_INR_X_LATENT_DIM",
    "SURROGATE_INR_FIELD_EMB_DIM",
    "SURROGATE_INR_COORD_FOURIER_FEATURES",
    "SURROGATE_INR_HIDDEN_DIM",
    "SURROGATE_INR_HIDDEN_LAYERS",
    "SURROGATE_INR_TRAIN_QUERY_CHUNK",
    "SURROGATE_INR_TRAIN_QUERY_SAMPLE_COUNT",
    "SURROGATE_INR_SAMPLE_BATCH_EVAL",
    "SURROGATE_INR_QUERY_BATCH_EVAL",
}
_NONNEGATIVE_INT_NAMES = {
    "YADOF_RESOURCE_RETRY_DOUBLINGS",
    "OPTIMIZE_RANDOM_SEED",
    "OPTIMIZE_ARCHIVE_KEY_DECIMALS",
    "OPTIMIZE_SURROGATE_ALPHA",
    "OPTIMIZE_SURROGATE_BETA",
    "OPTIMIZE_SURROGATE_MAX_TRAINING_LAG",
}
_POSITIVE_REAL_NAMES = {
    "EVALUATION_TIMEOUT_SEC",
    "HTCONDOR_POLL_SEC",
    "HTCONDOR_RESOURCE_BOOTSTRAP_MULTIPLIER",
    "HTCONDOR_REQUEST_DISK_MULTIPLIER",
    "HTCONDOR_JOB_TIMEOUT_MULTIPLIER",
    "OPTIMIZE_CROSSOVER_ETA",
    "OPTIMIZE_MUTATION_ETA",
    "SURROGATE_RELATIVE_ERROR_EPS",
    "SURROGATE_TARGET_SCALE_FLOOR",
    "SURROGATE_INR_LR",
    "SURROGATE_INR_BOOTSTRAP_FRACTION",
    "HISTORY_WRITER_SHUTDOWN_TIMEOUT_SEC",
}
_NONNEGATIVE_REAL_NAMES = {
    "SURROGATE_CONSTANT_ATOL",
    "SURROGATE_INR_WEIGHT_DECAY",
    "SURROGATE_INR_LOSS_BETA",
}
_FRACTION_NAMES = {
    "LOCAL_RESOURCE_SYSTEM_RESERVE_FRACTION",
    "FAST_RESOURCE_SYSTEM_RESERVE_FRACTION",
    "HTCONDOR_RESOURCE_TRIM_TOP_FRACTION",
    "HTCONDOR_JOB_TIMEOUT_TRIM_TOP_FRACTION",
    "OPTIMIZE_CROSSOVER_PROBABILITY",
    "OPTIMIZE_MUTATION_PROBABILITY",
    "OPTIMIZE_SURROGATE_GAMMA",
    "OPTIMIZE_SURROGATE_EXPLORATION_FRACTION",
    "SURROGATE_MAX_NONFINITE_FRACTION",
}
_STRING_NAMES = {
    "HTCONDOR_SUBMIT_EXE",
    "HTCONDOR_REMOVE_EXE",
    "HTCONDOR_HISTORY_EXE",
    "HTCONDOR_REQUIREMENTS",
    "HTCONDOR_ENVIRONMENT",
    "OPTIMIZE_NSGA3_REF_DIR_METHOD",
    "SURROGATE_TORCH_DEVICE",
}


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
        for name, _default in _DEFAULT_ITEMS:
            lines.append(f"{name} = {self.values[name]!r}  # {self.sources[name]}")
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
    if name in _PATH_NAMES:
        if not isinstance(value, (str, os.PathLike)) or not str(value):
            raise ConfigError(f"{name} must be a non-empty path")
        return value
    if name in _BOOL_NAMES:
        if not isinstance(value, bool):
            raise ConfigError(f"{name} must be bool, got {type(value).__name__}")
        return value
    if name in _POSITIVE_INT_NAMES or name in _NONNEGATIVE_INT_NAMES:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigError(f"{name} must be an integer, got {type(value).__name__}")
        minimum = 1 if name in _POSITIVE_INT_NAMES else 0
        if value < minimum:
            raise ConfigError(f"{name} must be >= {minimum}")
        return value
    if name in _POSITIVE_REAL_NAMES or name in _NONNEGATIVE_REAL_NAMES:
        number = _real(value, name)
        if number <= 0.0 and name in _POSITIVE_REAL_NAMES:
            raise ConfigError(f"{name} must be > 0")
        if number < 0.0 and name in _NONNEGATIVE_REAL_NAMES:
            raise ConfigError(f"{name} must be >= 0")
        return value
    if name in _FRACTION_NAMES:
        number = _real(value, name)
        if not 0.0 <= number <= 1.0:
            raise ConfigError(f"{name} must be between 0 and 1")
        return value
    if name in _STRING_NAMES:
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(f"{name} must be a non-empty string")
        return value
    if name in {"HTCONDOR_ALLOWED_MACHINES", "HTCONDOR_EXCLUDED_MACHINES"}:
        if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
            raise ConfigError(f"{name} must be a sequence of strings")
        result = tuple(value)
        if not all(isinstance(item, str) and item for item in result):
            raise ConfigError(f"{name} must contain only non-empty strings")
        return result
    if name in {"HTCONDOR_REQUEST_MEMORY", "HTCONDOR_REQUEST_DISK"}:
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            raise ConfigError(f"{name} must be a resource string or positive integer")
        if isinstance(value, str) and not value.strip():
            raise ConfigError(f"{name} must not be empty")
        if isinstance(value, int) and value <= 0:
            raise ConfigError(f"{name} must be positive")
        return value
    if name == "OPTIMIZE_NSGA3_PARTITIONS":
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
        ):
            raise ConfigError(f"{name} must be None or a positive integer")
        return value
    if name == "EVALUATION_MODE":
        if value not in {"fast", "local", "distributed"}:
            raise ConfigError(
                "EVALUATION_MODE must be 'fast', 'local', or 'distributed'"
            )
        return value
    if name == "HTCONDOR_JOB_TIMEOUT_MODE":
        if value not in {"auto", "fixed"}:
            raise ConfigError("HTCONDOR_JOB_TIMEOUT_MODE must be 'auto' or 'fixed'")
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
        legacy_cost = workspace.job_template_dir / "calc_cost.py"
        if legacy_cost.is_file():
            raise ConfigError(
                "legacy workspace layout detected: move job_template/calc_cost.py "
                "to submit/calc_cost.py and add submit/optimization.py, or create a "
                "fresh workspace and copy the task sources explicitly"
            )
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
    submit_required = ("calc_cost.py", "optimization.py")
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
    values = {name: _validate_value(name, value) for name, value in _DEFAULT_ITEMS}
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
