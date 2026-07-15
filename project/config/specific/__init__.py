"""Active software-specific configuration extensions."""

from __future__ import annotations

from . import hfss


def htcondor_environment_entries() -> tuple[str, ...]:
    """Return environment entries contributed by active specific configs."""

    return hfss.htcondor_environment_entries()
