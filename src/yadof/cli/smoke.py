"""Standalone smoke command and edited-task execution safety policy."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path, PurePosixPath
import sys

from .. import evaluate_manager
from ..config import ConfigError, load_config
from ..workspace import WorkspaceContext, resolve_workspace
from ..workspace.init import WorkspaceInitError, load_workspace_template
from ..workspace.manifest import WorkspaceMarkerError, read_workspace_marker
from ._output import write_text


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

    expected = {
        Path(*file.destination.parts): file.content
        for file in template.files
        if file.destination.is_relative_to(PurePosixPath("job_template"))
        or file.destination.is_relative_to(PurePosixPath("submit"))
    }
    actual: dict[Path, bytes] = {}
    for label, root in (
        ("job_template", context.job_template_dir),
        ("submit", context.submit_dir),
    ):
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(root)
            if any(part in _IGNORED_TASK_PARTS for part in relative.parts):
                continue
            if path.suffix.lower() in {".pyc", ".pyo"}:
                continue
            actual[Path(label) / relative] = path.read_bytes()
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
        "submit and evaluate task sources exactly match the installed generic starter",
    )


def smoke_command(args) -> int:
    """Run the standalone smoke command from one parsed CLI namespace."""

    try:
        config = load_config(
            args.workspace,
            overrides={"EVALUATION_MODE": args.mode},
        )
        assessment = assess_smoke_task(config.workspace)
        if not assessment.is_unchanged_generic_starter and not args.real_task:
            print(
                "yadof: error: refusing to execute an edited or external task "
                f"without --real-task ({assessment.reason}). This command runs "
                "workflow.py and may launch expensive external software.",
                file=sys.stderr,
            )
            return 1
        print(
            f"Starting smoke test in {config.workspace.root} "
            f"(mode={config.EVALUATION_MODE}).",
            flush=True,
        )
        print(
            "Exactly one midpoint individual will run with no timeout; "
            + (
                "fast mode creates no durable per-job folder; ephemeral scratch is "
                f"under {config.workspace.fast_evaluation_scratch_dir}."
                if str(config.EVALUATION_MODE) == "fast"
                else f"live job files are under {config.workspace.jobs_dir}."
            ),
            flush=True,
        )
        costs = evaluate_manager.run_smoke_test(config.workspace, mode=args.mode)
    except (
        ConfigError,
        evaluate_manager.JobPreparationError,
        ImportError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        print(f"yadof: error: smoke test could not run: {exc}", file=sys.stderr)
        return 1

    finite = any(math.isfinite(value) for row in costs for value in row)
    if not finite:
        diagnostic_location = (
            "inspect workspace recorded history"
            if str(config.EVALUATION_MODE) == "fast"
            else f"inspect recent jobs under {config.workspace.jobs_dir}"
        )
        print(
            "yadof: error: smoke test failed: no finite objective cost was returned; "
            f"{diagnostic_location}",
            file=sys.stderr,
        )
        return 1
    write_text(
        f"Smoke test succeeded for exactly one individual in {config.workspace.root}: "
        f"costs={costs[0]!r}"
    )
    return 0


__all__ = ["SmokeTaskAssessment", "assess_smoke_task", "smoke_command"]
