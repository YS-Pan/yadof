"""Small output helpers shared by CLI command modules."""

from __future__ import annotations

import sys


def write_text(value: str) -> None:
    """Write one text value with exactly one trailing line boundary."""

    sys.stdout.write(value)
    if not value.endswith("\n"):
        sys.stdout.write("\n")


__all__ = ["write_text"]
