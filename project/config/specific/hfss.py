"""HFSS/PyAEDT settings for the current task adapter."""

from __future__ import annotations

import os

from .. import key as key_config


HFSS_CPUCORE_MULTIPLIER = max(1, int(getattr(key_config, "HFSS_CPUCORE_MULTIPLIER", 2)))
HFSS_JOB_CPUCORE = max(1, int(getattr(key_config, "HTCONDOR_REQUEST_CPUS", 1)) * HFSS_CPUCORE_MULTIPLIER)
HFSS_PARALLEL_TASKS = 1
HFSS_NON_GRAPHICAL = True
HFSS_PIN_RETRIES = 1
HFSS_RETRY_CPUCORE = 1
ANSYS_LICENSE_SERVER = os.environ.get("ANSYSLMD_LICENSE_FILE", "1055@localhost")


def htcondor_environment_entries() -> tuple[str, ...]:
    """Return the HTCondor environment needed by the HFSS workflow."""

    entries = (
        f"YADOF_HFSS_JOB_CPUCORE={int(HFSS_JOB_CPUCORE)}",
        f"YADOF_HFSS_PARALLEL_TASKS={int(HFSS_PARALLEL_TASKS)}",
        f"YADOF_HFSS_NON_GRAPHICAL={1 if bool(HFSS_NON_GRAPHICAL) else 0}",
        f"YADOF_HFSS_PIN_RETRIES={int(HFSS_PIN_RETRIES)}",
        f"YADOF_HFSS_RETRY_CPUCORE={int(HFSS_RETRY_CPUCORE)}",
    )
    if ANSYS_LICENSE_SERVER:
        return entries + (f"ANSYSLMD_LICENSE_FILE={ANSYS_LICENSE_SERVER}",)
    return entries
