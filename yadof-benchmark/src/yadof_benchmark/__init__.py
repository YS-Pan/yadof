"""Public code-first benchmark API."""

from ._version import __version__
from .api import (
    BaselineManifest,
    Benchmark,
    BenchmarkError,
    ComparisonSpec,
    PostprocessContext,
    RunSpec,
    WorkflowRequest,
    discover_baselines,
    discover_presets,
    init_workspace,
    inspect_workspace,
    load_workflow,
    load_workspace_preset,
    plan_workspace,
    run_workspace,
    user_doc_root,
)

__all__ = [
    "BaselineManifest",
    "Benchmark",
    "BenchmarkError",
    "ComparisonSpec",
    "PostprocessContext",
    "RunSpec",
    "WorkflowRequest",
    "__version__",
    "discover_baselines",
    "discover_presets",
    "init_workspace",
    "inspect_workspace",
    "load_workflow",
    "load_workspace_preset",
    "plan_workspace",
    "run_workspace",
    "user_doc_root",
]
