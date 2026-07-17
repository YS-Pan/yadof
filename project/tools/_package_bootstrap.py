from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def ensure_project_package() -> None:
    """Make the source-tree project package importable without changing sys.path."""

    if "project" in sys.modules:
        return

    package_dir = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "project",
        package_dir / "__init__.py",
        submodule_search_locations=[str(package_dir)],
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load the project package from {package_dir}")

    module = importlib.util.module_from_spec(spec)
    sys.modules["project"] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop("project", None)
        raise
