"""Public package foundation and workspace contracts for yadof."""

from ._version import __version__
from .config import ConfigError, LoadedConfig, load_config
from .task_loader import TaskModuleError, load_task_module, task_module
from .workspace import WorkspaceContext, resolve_workspace

__all__ = [
    "ConfigError",
    "LoadedConfig",
    "TaskModuleError",
    "WorkspaceContext",
    "__version__",
    "load_config",
    "load_task_module",
    "resolve_workspace",
    "task_module",
]
