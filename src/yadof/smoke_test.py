"""Safety policy for standalone real-workflow smoke execution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .workspace import WorkspaceContext, resolve_workspace
from .workspace.init import WorkspaceInitError, load_workspace_template
from .workspace.manifest import WorkspaceMarkerError, read_workspace_marker


_IGNORED_TASK_PARTS = {"__pycache__", ".pytest_cache", "rawData"}


@dataclass(frozen=True, slots=True)
class SmokeTaskAssessment:
    is_unchanged_generic_starter: bool
    reason: str


def assess_smoke_task(
    workspace: WorkspaceContext | str | Path,
) -> SmokeTaskAssessment:
    """Identify only an unchanged bundled generic task as safe by default."""

    context = resolve_workspace(workspace)
    try:
        marker = read_workspace_marker(context.root)
        template = load_workspace_template(marker.template_name)
    except (WorkspaceMarkerError, WorkspaceInitError) as exc:
        return SmokeTaskAssessment(False, str(exc))
    if marker.template_version != template.version:
        return SmokeTaskAssessment(
            False,
            "workspace template version does not match the installed generic template",
        )

    prefix = PurePosixPath("job_template")
    expected = {
        Path(*file.destination.relative_to(prefix).parts): file.content
        for file in template.files
        if file.destination.is_relative_to(prefix)
    }
    actual = {
        path.relative_to(context.job_template_dir): path.read_bytes()
        for path in context.job_template_dir.rglob("*")
        if path.is_file()
        and not any(part in _IGNORED_TASK_PARTS for part in path.relative_to(context.job_template_dir).parts)
        and path.suffix.lower() not in {".pyc", ".pyo"}
    }
    if set(actual) != set(expected):
        added = sorted(path.as_posix() for path in set(actual) - set(expected))
        missing = sorted(path.as_posix() for path in set(expected) - set(actual))
        details = []
        if added:
            details.append("additional task files: " + ", ".join(added))
        if missing:
            details.append("missing starter files: " + ", ".join(missing))
        return SmokeTaskAssessment(False, "; ".join(details))
    changed = sorted(
        path.as_posix() for path, content in actual.items() if content != expected[path]
    )
    if changed:
        return SmokeTaskAssessment(
            False,
            "starter task files were edited: " + ", ".join(changed),
        )
    return SmokeTaskAssessment(
        True,
        "task files exactly match the installed generic starter",
    )


__all__ = ["SmokeTaskAssessment", "assess_smoke_task"]
