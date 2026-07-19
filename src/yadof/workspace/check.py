"""Read-only diagnostics for an initialized yadof workspace."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import sys
from typing import Literal

from .._version import __version__
from ..config import LoadedConfig, load_config
from ..job_template import (
    RAWDATA_SCHEMA_VERSION,
    validate_rawdata_directory,
    validate_task,
)
from .context import WorkspaceContext, resolve_workspace
from .init import load_workspace_template
from .manifest import (
    WORKSPACE_MARKER_RELATIVE_PATH,
    WORKSPACE_SCHEMA_VERSION,
    WorkspaceMarker,
    read_workspace_marker,
)


CheckStatus = Literal["ok", "warning", "error"]


@dataclass(frozen=True, slots=True)
class CheckFinding:
    status: CheckStatus
    subject: str
    message: str

    def format(self) -> str:
        return f"[{self.status.upper()}] {self.subject}: {self.message}"


@dataclass(frozen=True, slots=True)
class CheckReport:
    workspace: WorkspaceContext
    findings: tuple[CheckFinding, ...]

    @property
    def ok(self) -> bool:
        return not any(item.status == "error" for item in self.findings)

    @property
    def error_count(self) -> int:
        return sum(item.status == "error" for item in self.findings)

    @property
    def warning_count(self) -> int:
        return sum(item.status == "warning" for item in self.findings)

    def format(self) -> str:
        lines = [item.format() for item in self.findings]
        if self.ok:
            lines.append(
                f"Workspace check passed: {self.workspace.root} "
                f"({self.warning_count} warning(s))"
            )
        else:
            lines.append(
                f"Workspace check failed: {self.workspace.root} "
                f"({self.error_count} error(s), {self.warning_count} warning(s))"
            )
        return "\n".join(lines)


def _finding(
    findings: list[CheckFinding], status: CheckStatus, subject: str, message: str
) -> None:
    findings.append(CheckFinding(status, subject, message))


def _check_marker(
    workspace: WorkspaceContext, findings: list[CheckFinding]
) -> WorkspaceMarker | None:
    marker_path = workspace.root / WORKSPACE_MARKER_RELATIVE_PATH
    try:
        marker = read_workspace_marker(workspace.root)
    except (Exception, SystemExit) as exc:
        _finding(findings, "error", "workspace marker", str(exc))
        return None
    if marker.workspace_schema_version != WORKSPACE_SCHEMA_VERSION:
        _finding(
            findings,
            "error",
            "workspace marker",
            f"unsupported workspace_schema_version={marker.workspace_schema_version}; "
            f"installed support is {WORKSPACE_SCHEMA_VERSION}",
        )
    else:
        _finding(
            findings,
            "ok",
            "workspace marker",
            f"schema {marker.workspace_schema_version} at {marker_path}",
        )
    if marker.rawdata_schema_version != RAWDATA_SCHEMA_VERSION:
        _finding(
            findings,
            "error",
            "rawData schema",
            f"marker uses {marker.rawdata_schema_version}; installed support is "
            f"{RAWDATA_SCHEMA_VERSION}",
        )
    else:
        _finding(
            findings,
            "ok",
            "rawData schema",
            f"schema {marker.rawdata_schema_version}",
        )
    if marker.yadof_version != __version__:
        _finding(
            findings,
            "warning",
            "yadof version",
            f"workspace was initialized by {marker.yadof_version}; "
            f"installed version is {__version__}",
        )
    else:
        _finding(findings, "ok", "yadof version", __version__)
    try:
        template = load_workspace_template(marker.template_name)
    except (Exception, SystemExit) as exc:
        _finding(findings, "error", "workspace template", str(exc))
        return marker
    if marker.template_version != template.version:
        _finding(
            findings,
            "warning",
            "workspace template",
            f"workspace uses {marker.template_name} version {marker.template_version}; "
            f"installed template version is {template.version}; no automatic upgrade was run",
        )
    else:
        _finding(
            findings,
            "ok",
            "workspace template",
            f"{marker.template_name} version {marker.template_version}",
        )
    for item in template.files:
        path = workspace.root.joinpath(*item.destination.parts)
        if not path.is_file():
            _finding(findings, "error", "workspace structure", f"missing required file: {path}")
    return marker


def _check_config(
    workspace: WorkspaceContext, findings: list[CheckFinding]
) -> LoadedConfig | None:
    try:
        config = load_config(workspace)
    except (Exception, SystemExit) as exc:
        _finding(findings, "error", "config", str(exc))
        return None
    _finding(
        findings,
        "ok",
        "config",
        f"loaded {workspace.config_file}; EVALUATION_MODE={config.EVALUATION_MODE!r}",
    )
    return config


def _check_task(config: LoadedConfig, findings: list[CheckFinding]) -> None:
    try:
        task = validate_task(config.workspace)
    except (Exception, SystemExit) as exc:
        _finding(findings, "error", "task modules", str(exc))
    else:
        _finding(
            findings,
            "ok",
            "task modules",
            f"{task.variable_count} parameter(s), {task.objective_count} objective(s)",
        )

    workflow_path = config.workspace.job_template_dir / "workflow.py"
    try:
        source = workflow_path.read_text(encoding="utf-8")
        ast.parse(source, filename=str(workflow_path))
    except (Exception, SystemExit) as exc:
        _finding(findings, "error", "workflow", f"syntax/read failure: {exc}")
    else:
        _finding(
            findings,
            "ok",
            "workflow",
            "syntax is valid; workflow was not imported or executed",
        )

    static_rawdata = config.workspace.job_template_dir / "rawData"
    if not static_rawdata.exists():
        _finding(
            findings,
            "ok",
            "static rawData",
            "no task-local rawData directory to validate",
        )
    else:
        try:
            files = validate_rawdata_directory(static_rawdata)
        except (Exception, SystemExit) as exc:
            _finding(findings, "error", "static rawData", str(exc))
        else:
            _finding(
                findings,
                "ok",
                "static rawData",
                f"validated {len(files)} schema-conforming .npz file(s)",
            )


def _check_backend(config: LoadedConfig, findings: list[CheckFinding]) -> None:
    mode = str(config.EVALUATION_MODE)
    if mode == "local":
        executable = Path(sys.executable)
        if executable.is_file():
            _finding(findings, "ok", "local backend", f"Python executable: {executable}")
        else:
            _finding(
                findings,
                "error",
                "local backend",
                f"Python executable is missing: {executable}",
            )
        return

    commands = (
        ("condor_submit", str(config.HTCONDOR_SUBMIT_EXE)),
        ("condor_rm", str(config.HTCONDOR_REMOVE_EXE)),
        ("condor_history", str(config.HTCONDOR_HISTORY_EXE)),
    )
    for label, command in commands:
        resolved = shutil.which(command)
        if resolved:
            _finding(findings, "ok", "distributed backend", f"{label}: {resolved}")
        else:
            _finding(
                findings,
                "error",
                "distributed backend",
                f"{label} executable was not found: {command!r}; "
                "ask an administrator to prepare HTCondor",
            )


def check_workspace(
    workspace: WorkspaceContext | str | os.PathLike[str] | None = None,
) -> CheckReport:
    """Inspect a workspace without running workflows or modifying any files."""

    context = resolve_workspace(workspace)
    findings: list[CheckFinding] = []
    if not context.root.is_dir():
        _finding(findings, "error", "workspace", f"directory does not exist: {context.root}")
        return CheckReport(context, tuple(findings))
    if not os.access(context.root, os.R_OK):
        _finding(findings, "error", "workspace", f"directory is not readable: {context.root}")
    else:
        _finding(findings, "ok", "workspace", f"readable directory: {context.root}")
    if not os.access(context.root, os.W_OK):
        _finding(
            findings,
            "error",
            "workspace",
            "directory is not writable for future jobs/runtime state",
        )
    else:
        _finding(findings, "ok", "workspace", "writable for future runtime state")

    _check_marker(context, findings)
    config = _check_config(context, findings)
    if config is not None:
        _check_task(config, findings)
        _check_backend(config, findings)
    return CheckReport(context, tuple(findings))


__all__ = ["CheckFinding", "CheckReport", "CheckStatus", "check_workspace"]
