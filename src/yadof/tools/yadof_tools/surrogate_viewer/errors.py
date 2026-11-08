"""Structured runtime errors for terminal surrogate-viewer commands."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
import math
from typing import Any


ERROR_SCHEMA_VERSION = 1


class SurrogateToolError(ValueError):
    """A stable, user-facing surrogate-tool failure."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: Mapping[str, object] | None = None,
        hints: Sequence[str] = (),
    ) -> None:
        super().__init__(message)
        self.code = str(code)
        self.message = str(message)
        self.details = dict(details or {})
        self.hints = tuple(str(hint) for hint in hints)


class NoCompatibleCheckpointError(FileNotFoundError):
    """The active strategy has no viewer-compatible checkpoint."""

    code = "NO_COMPATIBLE_CHECKPOINT"

    def __init__(
        self,
        message: str,
        *,
        details: Mapping[str, object] | None = None,
        hints: Sequence[str] = (),
    ) -> None:
        super().__init__(message)
        self.message = str(message)
        self.details = dict(details or {})
        self.hints = tuple(str(hint) for hint in hints)


def _json_safe(value: object) -> Any:
    """Convert nested values to finite, standard-JSON data."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return [_json_safe(item) for item in value]
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return str(value)
    return parsed if math.isfinite(parsed) else None


def normalize_surrogate_error(
    error: BaseException,
    *,
    operation: str,
) -> SurrogateToolError:
    """Map a runtime exception to the stable terminal error taxonomy."""

    if isinstance(error, SurrogateToolError):
        return error
    if isinstance(error, NoCompatibleCheckpointError):
        return SurrogateToolError(
            error.code,
            error.message,
            details=error.details,
            hints=error.hints,
        )

    try:
        from yadof.config import ConfigError
    except ImportError:  # pragma: no cover - yadof owns this module.
        ConfigError = ()  # type: ignore[assignment]

    if isinstance(error, (ImportError, ModuleNotFoundError)):
        missing = getattr(error, "name", None)
        return SurrogateToolError(
            "MISSING_OPTIONAL_DEPENDENCY",
            "The surrogate tool's optional runtime dependencies are unavailable.",
            details={
                "operation": operation,
                "dependency": missing,
            },
            hints=("Install yadof with the 'viewer' extra and retry.",),
        )
    if ConfigError and isinstance(error, ConfigError):
        return SurrogateToolError(
            "INVALID_WORKSPACE_CONFIG",
            str(error),
            details={"operation": operation},
            hints=(
                "Select a valid yadof workspace and run 'yadof check' for details.",
            ),
        )
    if operation == "summary" and isinstance(error, (OSError, ValueError)):
        return SurrogateToolError(
            "INVALID_WORKSPACE_CONFIG",
            str(error),
            details={"operation": operation},
            hints=("Verify the workspace, completed records, and active strategy.",),
        )
    if operation == "audit" and isinstance(error, ValueError):
        return SurrogateToolError(
            "INVALID_AUDIT_REQUEST",
            str(error),
            details={"operation": operation},
            hints=("Check the requested quantity and audit options.",),
        )
    if operation in {"audit", "inspect"}:
        return SurrogateToolError(
            "INFERENCE_FAILED",
            "Surrogate inference did not complete.",
            details={
                "operation": operation,
                "exception_type": type(error).__name__,
            },
            hints=(
                "Verify checkpoint compatibility and retry with the same selection.",
            ),
        )
    return SurrogateToolError(
        "INTERNAL_ERROR",
        "The surrogate tool did not complete.",
        details={
            "operation": operation,
            "exception_type": type(error).__name__,
        },
        hints=("Retry in text mode for a concise human-readable diagnostic.",),
    )


def surrogate_error_payload(error: SurrogateToolError) -> dict[str, object]:
    """Return the schema-versioned terminal error payload."""

    return {
        "schema_version": ERROR_SCHEMA_VERSION,
        "analysis": "surrogate_tool_error",
        "error": {
            "code": error.code,
            "message": error.message,
            "details": _json_safe(error.details),
            "hints": list(error.hints),
        },
    }


def format_surrogate_error(
    error: SurrogateToolError,
    *,
    output_format: str,
) -> str:
    """Format one normalized failure for stderr."""

    if output_format == "json":
        return json.dumps(
            surrogate_error_payload(error),
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
        )
    if output_format != "text":
        raise ValueError("output_format must be text or json")
    lines = [f"[{error.code}] {error.message}"]
    if error.details:
        details = ", ".join(
            f"{key}={value!r}"
            for key, value in error.details.items()
        )
        lines.append(f"details: {details}")
    lines.extend(f"hint: {hint}" for hint in error.hints)
    return "\n".join(lines)


__all__ = [
    "ERROR_SCHEMA_VERSION",
    "NoCompatibleCheckpointError",
    "SurrogateToolError",
    "format_surrogate_error",
    "normalize_surrogate_error",
    "surrogate_error_payload",
]
