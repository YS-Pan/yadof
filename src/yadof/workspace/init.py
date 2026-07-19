"""Safe, idempotent creation of a user-owned yadof workspace."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from typing import Mapping, Sequence

from ..config import load_config
from ..job_template import validate_task
from ..resources import ResourceNotFoundError, read_template_manifest, template_root
from .context import WorkspaceContext
from .manifest import (
    WORKSPACE_MARKER_RELATIVE_PATH,
    WORKSPACE_SCHEMA_VERSION,
    WorkspaceMarker,
    WorkspaceMarkerError,
    read_workspace_marker,
)


TEMPLATE_MANIFEST_SCHEMA_VERSION = 1
DEFAULT_TEMPLATE_NAME = "default"


class WorkspaceInitError(RuntimeError):
    """Raised when initialization cannot proceed without risking user content."""


@dataclass(frozen=True, slots=True)
class TemplateFile:
    source: PurePosixPath
    destination: PurePosixPath
    content: bytes


@dataclass(frozen=True, slots=True)
class WorkspaceTemplate:
    name: str
    version: int
    rawdata_schema_version: int
    files: tuple[TemplateFile, ...]


@dataclass(frozen=True, slots=True)
class InitResult:
    workspace: WorkspaceContext
    template_name: str
    template_version: int
    created: bool


def _positive_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise WorkspaceInitError(f"template manifest {label} must be a positive integer")
    return value


def _safe_relative_path(value: object, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise WorkspaceInitError(f"template manifest {label} must be a non-empty string")
    path = PurePosixPath(value)
    if (
        not path.parts
        or path.is_absolute()
        or "\\" in value
        or any(part in {"", ".", ".."} or ":" in part for part in path.parts)
    ):
        raise WorkspaceInitError(
            f"template manifest {label} is not a safe relative path: {value!r}"
        )
    return path


def load_workspace_template(name: str = DEFAULT_TEMPLATE_NAME) -> WorkspaceTemplate:
    """Load and validate one bundled workspace template entirely in memory."""

    try:
        manifest = read_template_manifest(name)
    except ResourceNotFoundError as exc:
        raise WorkspaceInitError(str(exc)) from exc
    schema_version = _positive_int(manifest.get("schema_version"), "schema_version")
    if schema_version != TEMPLATE_MANIFEST_SCHEMA_VERSION:
        raise WorkspaceInitError(
            f"unsupported template manifest schema_version: {schema_version}"
        )
    manifest_name = manifest.get("name")
    if manifest_name != name:
        raise WorkspaceInitError(
            f"template manifest name {manifest_name!r} does not match requested {name!r}"
        )
    version = _positive_int(manifest.get("template_version"), "template_version")
    rawdata_schema_version = _positive_int(
        manifest.get("rawdata_schema_version"), "rawdata_schema_version"
    )
    raw_files = manifest.get("files")
    if not isinstance(raw_files, Sequence) or isinstance(raw_files, (str, bytes)):
        raise WorkspaceInitError("template manifest files must be a sequence")

    try:
        resource_root = template_root(name)
    except ResourceNotFoundError as exc:
        raise WorkspaceInitError(str(exc)) from exc
    files: list[TemplateFile] = []
    destinations: set[PurePosixPath] = set()
    for index, entry in enumerate(raw_files):
        if not isinstance(entry, Mapping):
            raise WorkspaceInitError(f"template manifest files[{index}] must be an object")
        source = _safe_relative_path(entry.get("source"), f"files[{index}].source")
        destination = _safe_relative_path(
            entry.get("destination"), f"files[{index}].destination"
        )
        if destination == PurePosixPath(WORKSPACE_MARKER_RELATIVE_PATH.as_posix()):
            raise WorkspaceInitError("template files must not provide the workspace marker")
        if destination in destinations:
            raise WorkspaceInitError(
                f"template manifest repeats destination: {destination.as_posix()}"
            )
        resource = resource_root
        for part in source.parts:
            resource = resource.joinpath(part)
        if not resource.is_file():
            raise WorkspaceInitError(
                f"template resource is missing: {name}/{source.as_posix()}"
            )
        try:
            content = resource.read_bytes()
        except OSError as exc:
            raise WorkspaceInitError(
                f"could not read template resource {source.as_posix()}: {exc}"
            ) from exc
        destinations.add(destination)
        files.append(TemplateFile(source, destination, content))
    if not files:
        raise WorkspaceInitError("template manifest must define at least one file")
    return WorkspaceTemplate(
        name=name,
        version=version,
        rawdata_schema_version=rawdata_schema_version,
        files=tuple(files),
    )


def _target_path(root: Path, relative: PurePosixPath | Path) -> Path:
    return root.joinpath(*relative.parts)


def _obstructions(root: Path, template: WorkspaceTemplate) -> tuple[Path, ...]:
    found: set[Path] = set()
    for item in template.files:
        target = _target_path(root, item.destination)
        if target.exists():
            found.add(target)
        parent = target.parent
        while parent != root and root in parent.parents:
            if parent.exists() and not parent.is_dir():
                found.add(parent)
                break
            parent = parent.parent
    return tuple(sorted(found, key=lambda path: str(path).lower()))


def _validate_existing_workspace(root: Path, template: WorkspaceTemplate) -> InitResult:
    try:
        marker = read_workspace_marker(root)
    except WorkspaceMarkerError as exc:
        raise WorkspaceInitError(str(exc)) from exc
    if marker.workspace_schema_version != WORKSPACE_SCHEMA_VERSION:
        raise WorkspaceInitError(
            f"workspace marker uses unsupported schema version "
            f"{marker.workspace_schema_version}: {root / WORKSPACE_MARKER_RELATIVE_PATH}"
        )
    if marker.template_name != template.name or marker.template_version != template.version:
        raise WorkspaceInitError(
            "workspace uses a different template/version; automatic upgrade is not supported: "
            f"{root / WORKSPACE_MARKER_RELATIVE_PATH}"
        )
    missing = [
        _target_path(root, item.destination)
        for item in template.files
        if not _target_path(root, item.destination).is_file()
    ]
    if missing:
        listing = "\n".join(f"- {path}" for path in missing)
        raise WorkspaceInitError(
            "initialized workspace is incomplete; init will not recreate user files:\n"
            + listing
        )
    return InitResult(
        workspace=WorkspaceContext.from_path(root),
        template_name=marker.template_name,
        template_version=marker.template_version,
        created=False,
    )


def _write_stage(stage: Path, template: WorkspaceTemplate) -> None:
    for item in template.files:
        target = _target_path(stage, item.destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(item.content)
    marker = WorkspaceMarker.current(
        template_name=template.name, template_version=template.version
    )
    if marker.rawdata_schema_version != template.rawdata_schema_version:
        raise WorkspaceInitError(
            "template rawData schema version does not match the installed framework"
        )
    marker_path = stage / WORKSPACE_MARKER_RELATIVE_PATH
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_text(marker.to_json(), encoding="utf-8", newline="\n")


def _validate_staged_workspace(stage: Path, template: WorkspaceTemplate) -> None:
    marker = read_workspace_marker(stage)
    if marker.template_name != template.name or marker.template_version != template.version:
        raise WorkspaceInitError("staged workspace marker does not match its template")
    config = load_config(stage)
    validate_task(config.workspace)
    workflow_path = config.workspace.job_template_dir / "workflow.py"
    ast.parse(workflow_path.read_text(encoding="utf-8"), filename=str(workflow_path))


def _ensure_parent_directories(root: Path, parent: Path, created: list[Path]) -> None:
    missing: list[Path] = []
    cursor = parent
    while cursor != root and not cursor.exists():
        missing.append(cursor)
        cursor = cursor.parent
    if cursor.exists() and not cursor.is_dir():
        raise FileExistsError(f"workspace path blocks a required directory: {cursor}")
    for directory in reversed(missing):
        directory.mkdir()
        created.append(directory)


def _publish_file_exclusive(source: Path, target: Path) -> None:
    """Publish one staged file without overwriting a concurrent/user file."""

    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(source.read_bytes())
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        target.unlink(missing_ok=True)
        raise


def _publish_into_existing(stage: Path, root: Path, template: WorkspaceTemplate) -> None:
    created_files: list[Path] = []
    created_dirs: list[Path] = []
    ordered = [item.destination for item in template.files]
    ordered.append(PurePosixPath(WORKSPACE_MARKER_RELATIVE_PATH.as_posix()))
    try:
        for relative in ordered:
            source = _target_path(stage, relative)
            target = _target_path(root, relative)
            _ensure_parent_directories(root, target.parent, created_dirs)
            _publish_file_exclusive(source, target)
            created_files.append(target)
    except BaseException:
        for path in reversed(created_files):
            path.unlink(missing_ok=True)
        for directory in reversed(created_dirs):
            try:
                directory.rmdir()
            except OSError:
                pass
        raise


def init_workspace(
    path: str | os.PathLike[str] | None = None,
    *,
    template_name: str = DEFAULT_TEMPLATE_NAME,
) -> InitResult:
    """Initialize a workspace without overwriting existing user content."""

    workspace = WorkspaceContext.from_path(path)
    root = workspace.root
    template = load_workspace_template(template_name)
    marker_path = root / WORKSPACE_MARKER_RELATIVE_PATH
    if root.exists() and not root.is_dir():
        raise WorkspaceInitError(f"workspace path is not a directory: {root}")
    if marker_path.exists():
        return _validate_existing_workspace(root, template)

    conflicts = _obstructions(root, template) if root.exists() else ()
    if conflicts:
        listing = "\n".join(f"- {path}" for path in conflicts)
        raise WorkspaceInitError(
            "workspace initialization would overwrite existing target(s):\n" + listing
        )

    created_parents: list[Path] = []
    missing_parents: list[Path] = []
    cursor = root.parent
    while not cursor.exists():
        missing_parents.append(cursor)
        cursor = cursor.parent
    stage: Path | None = None
    completed = False
    try:
        for parent in reversed(missing_parents):
            parent.mkdir()
            created_parents.append(parent)
        stage = Path(
            tempfile.mkdtemp(prefix=f".{root.name}.yadof-init-", dir=str(root.parent))
        )
        _write_stage(stage, template)
        _validate_staged_workspace(stage, template)
        if root.exists():
            _publish_into_existing(stage, root, template)
        else:
            os.replace(stage, root)
            stage = None
        completed = True
    except WorkspaceInitError:
        raise
    except (Exception, SystemExit) as exc:
        raise WorkspaceInitError(f"workspace initialization failed: {exc}") from exc
    finally:
        if stage is not None and stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        if not completed:
            for parent in reversed(created_parents):
                try:
                    parent.rmdir()
                except OSError:
                    pass
    return InitResult(
        workspace=WorkspaceContext.from_path(root),
        template_name=template.name,
        template_version=template.version,
        created=True,
    )


__all__ = [
    "DEFAULT_TEMPLATE_NAME",
    "InitResult",
    "TemplateFile",
    "WorkspaceInitError",
    "WorkspaceTemplate",
    "init_workspace",
    "load_workspace_template",
]
