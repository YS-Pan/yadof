"""Fresh, isolated loading of user-owned workspace task modules."""

from __future__ import annotations

from contextlib import contextmanager
import importlib
from importlib.abc import Loader, MetaPathFinder
from importlib.machinery import ModuleSpec
from importlib.util import spec_from_loader
import os
from pathlib import Path
import sys
import threading
from types import ModuleType
from typing import Iterator
import uuid

from .workspace import WorkspaceContext, resolve_workspace


class TaskModuleError(ImportError):
    """Raised when a workspace task module cannot be loaded safely."""


_IMPORT_LOCK = threading.RLock()


def _module_parts(module_name: str) -> tuple[str, ...]:
    parts = tuple(module_name.split("."))
    if not parts or any(not part.isidentifier() for part in parts):
        raise TaskModuleError(f"invalid task module name: {module_name!r}")
    return parts


def _source_for(root: Path, parts: tuple[str, ...]) -> tuple[Path, bool] | None:
    package_init = root.joinpath(*parts, "__init__.py")
    module_file = root.joinpath(*parts).with_suffix(".py")
    if package_init.is_file():
        return package_init, True
    if module_file.is_file():
        return module_file, False
    return None


class _FreshSourceLoader(Loader):
    def __init__(self, source: Path, *, is_package: bool) -> None:
        self.source = source
        self.is_package = is_package

    def create_module(self, spec: ModuleSpec) -> ModuleType | None:
        return None

    def exec_module(self, module: ModuleType) -> None:
        module.__file__ = str(self.source)
        module.__cached__ = None
        if self.is_package:
            module.__path__ = [str(self.source.parent)]
        code = compile(self.source.read_bytes(), str(self.source), "exec")
        exec(code, module.__dict__)


class _WorkspaceFinder(MetaPathFinder):
    def __init__(self, root: Path, namespace: str, local_names: set[str]) -> None:
        self.root = root
        self.namespace = namespace
        self.local_names = local_names

    def find_spec(
        self,
        fullname: str,
        path: object = None,
        target: ModuleType | None = None,
    ) -> ModuleSpec | None:
        prefix = self.namespace + "."
        if fullname.startswith(prefix):
            parts = _module_parts(fullname[len(prefix) :])
        else:
            parts = _module_parts(fullname)
            if parts[0] not in self.local_names:
                return None
        located = _source_for(self.root, parts)
        if located is None:
            return None
        source, is_package = located
        loader = _FreshSourceLoader(source, is_package=is_package)
        return spec_from_loader(
            fullname,
            loader,
            origin=str(source),
            is_package=is_package,
        )


def _local_top_level_names(root: Path) -> set[str]:
    names = {
        path.stem
        for path in root.glob("*.py")
        if path.name != "__init__.py" and path.stem.isidentifier()
    }
    names.update(
        path.name
        for path in root.iterdir()
        if path.is_dir() and path.name.isidentifier() and (path / "__init__.py").is_file()
    )
    return names


@contextmanager
def task_module(
    workspace: WorkspaceContext | str | os.PathLike[str],
    module_name: str,
) -> Iterator[ModuleType]:
    """Yield one freshly compiled task module in a temporary import namespace.

    Sibling absolute and relative imports are resolved from the same task directory.
    The workspace is never added to ``sys.path``. All temporary module-cache entries
    are removed, and any pre-existing same-named modules are restored, on exit.
    """

    context = resolve_workspace(workspace)
    root = context.job_template_dir.resolve()
    parts = _module_parts(module_name)
    if not root.is_dir():
        raise TaskModuleError(f"workspace job_template directory does not exist: {root}")
    located = _source_for(root, parts)
    if located is None:
        expected = root.joinpath(*parts).with_suffix(".py")
        raise TaskModuleError(f"task module does not exist: {expected}")

    namespace = f"_yadof_workspace_{uuid.uuid4().hex}"
    local_names = _local_top_level_names(root)
    finder = _WorkspaceFinder(root, namespace, local_names)
    stashed: dict[str, ModuleType] = {}

    with _IMPORT_LOCK:
        for loaded_name in tuple(sys.modules):
            top_level = loaded_name.split(".", 1)[0]
            if top_level in local_names:
                stashed[loaded_name] = sys.modules.pop(loaded_name)

        package = ModuleType(namespace)
        package.__file__ = str(root)
        package.__package__ = namespace
        package.__path__ = [str(root)]
        package.__spec__ = ModuleSpec(namespace, loader=None, is_package=True)
        sys.modules[namespace] = package
        sys.meta_path.insert(0, finder)
        try:
            try:
                importlib.invalidate_caches()
                loaded = importlib.import_module(f"{namespace}.{module_name}")
            except TaskModuleError:
                raise
            except (Exception, SystemExit) as exc:
                source = located[0]
                raise TaskModuleError(
                    f"failed to load task module {source}: {exc}"
                ) from exc
            yield loaded
        finally:
            if finder in sys.meta_path:
                sys.meta_path.remove(finder)
            prefix = namespace + "."
            for loaded_name in tuple(sys.modules):
                top_level = loaded_name.split(".", 1)[0]
                if (
                    loaded_name == namespace
                    or loaded_name.startswith(prefix)
                    or top_level in local_names
                ):
                    sys.modules.pop(loaded_name, None)
            sys.modules.update(stashed)
            importlib.invalidate_caches()


def load_task_module(
    workspace: WorkspaceContext | str | os.PathLike[str],
    module_name: str,
) -> ModuleType:
    """Load and return a fresh task module snapshot."""

    with task_module(workspace, module_name) as loaded:
        return loaded


__all__ = ["TaskModuleError", "load_task_module", "task_module"]
