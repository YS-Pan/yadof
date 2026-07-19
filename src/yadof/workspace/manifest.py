"""Versioned, portable metadata for initialized yadof workspaces."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping

from .._version import __version__
from ..job_template.rawdata_contract import RAWDATA_SCHEMA_VERSION


WORKSPACE_SCHEMA_VERSION = 1
WORKSPACE_MARKER_RELATIVE_PATH = Path(".yadof") / "workspace.json"


class WorkspaceMarkerError(ValueError):
    """Raised when workspace marker metadata is missing or invalid."""


@dataclass(frozen=True, slots=True)
class WorkspaceMarker:
    workspace_schema_version: int
    yadof_version: str
    template_name: str
    template_version: int
    rawdata_schema_version: int

    @classmethod
    def current(cls, *, template_name: str, template_version: int) -> "WorkspaceMarker":
        return cls(
            workspace_schema_version=WORKSPACE_SCHEMA_VERSION,
            yadof_version=__version__,
            template_name=template_name,
            template_version=int(template_version),
            rawdata_schema_version=RAWDATA_SCHEMA_VERSION,
        )

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, object], *, source: str = "workspace marker"
    ) -> "WorkspaceMarker":
        required = {
            "workspace_schema_version",
            "yadof_version",
            "template_name",
            "template_version",
            "rawdata_schema_version",
        }
        missing = sorted(required - set(payload))
        if missing:
            raise WorkspaceMarkerError(
                f"{source} is missing field(s): {', '.join(missing)}"
            )
        version_fields = (
            payload["workspace_schema_version"],
            payload["template_version"],
            payload["rawdata_schema_version"],
        )
        if not all(
            isinstance(value, int) and not isinstance(value, bool)
            for value in version_fields
        ):
            raise WorkspaceMarkerError(
                f"{source} schema/template versions must be integers"
            )
        workspace_schema_version = payload["workspace_schema_version"]
        template_version = payload["template_version"]
        rawdata_schema_version = payload["rawdata_schema_version"]
        yadof_version = payload["yadof_version"]
        template_name = payload["template_name"]
        if not isinstance(yadof_version, str) or not yadof_version:
            raise WorkspaceMarkerError(f"{source} yadof_version must be a string")
        if not isinstance(template_name, str) or not template_name:
            raise WorkspaceMarkerError(f"{source} template_name must be a string")
        if workspace_schema_version <= 0 or template_version <= 0:
            raise WorkspaceMarkerError(
                f"{source} workspace/template versions must be positive"
            )
        if rawdata_schema_version <= 0:
            raise WorkspaceMarkerError(
                f"{source} rawdata_schema_version must be positive"
            )
        return cls(
            workspace_schema_version=workspace_schema_version,
            yadof_version=yadof_version,
            template_name=template_name,
            template_version=template_version,
            rawdata_schema_version=rawdata_schema_version,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "workspace_schema_version": self.workspace_schema_version,
            "yadof_version": self.yadof_version,
            "template_name": self.template_name,
            "template_version": self.template_version,
            "rawdata_schema_version": self.rawdata_schema_version,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"


def read_workspace_marker(workspace_root: str | Path) -> WorkspaceMarker:
    marker_path = Path(workspace_root) / WORKSPACE_MARKER_RELATIVE_PATH
    if not marker_path.is_file():
        raise WorkspaceMarkerError(f"workspace marker does not exist: {marker_path}")
    try:
        payload = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise WorkspaceMarkerError(
            f"workspace marker is not valid JSON: {marker_path}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise WorkspaceMarkerError(f"workspace marker must be a JSON object: {marker_path}")
    return WorkspaceMarker.from_mapping(payload, source=str(marker_path))


__all__ = [
    "WORKSPACE_MARKER_RELATIVE_PATH",
    "WORKSPACE_SCHEMA_VERSION",
    "WorkspaceMarker",
    "WorkspaceMarkerError",
    "read_workspace_marker",
]
