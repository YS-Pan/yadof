"""Human-visible benchmark workspace, run, and output names."""
from __future__ import annotations

import datetime as dt
import re

from .contracts import BenchmarkError

_TIMESTAMP_PREFIX = re.compile(r"\d{8}_\d{6}(?:[-_]|$)")


def slug(value: str) -> str:
    """Return a filesystem-safe semantic name."""

    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value)).strip("-._")
    if not normalized:
        raise BenchmarkError(f"cannot derive a path name from {value!r}")
    return normalized


def timestamp_prefix(now: dt.datetime | None = None) -> str:
    """Return the local wall-clock prefix used by human-visible outputs."""

    selected = now or dt.datetime.now()
    return selected.strftime("%Y%m%d_%H%M%S")


def timestamped_name(value: str, *, now: dt.datetime | None = None) -> str:
    """Prefix a semantic name once with ``YYYYMMDD_HHMMSS``."""

    selected = slug(value)
    if _TIMESTAMP_PREFIX.match(selected):
        return selected
    return f"{timestamp_prefix(now)}-{selected}"


__all__ = ["slug", "timestamp_prefix", "timestamped_name"]
