"""Public package foundation and workspace contracts for yadof."""

from ._version import __version__
from .config import ConfigError, LoadedConfig, load_config
from .task_loader import TaskModuleError, load_task_module, task_module
from .workspace import WorkspaceContext, resolve_workspace


def __getattr__(name: str):
    if name in {"evaluate_population", "prepare_job", "run_smoke_test"}:
        from . import evaluate_manager

        return getattr(evaluate_manager, name)
    raise AttributeError(name)

__all__ = [
    "ConfigError",
    "LoadedConfig",
    "TaskModuleError",
    "WorkspaceContext",
    "__version__",
    "evaluate_population",
    "load_config",
    "load_task_module",
    "prepare_job",
    "resolve_workspace",
    "run_smoke_test",
    "task_module",
]
