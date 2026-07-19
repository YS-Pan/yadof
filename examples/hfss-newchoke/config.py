from __future__ import annotations

import os

# Key settings users are most likely to edit for a new optimization campaign.

EVALUATION_MODE = "distributed"  # "local" or "distributed"
EVALUATION_TIMEOUT_SEC = 12 * 60 * 60
OPTIMIZE_SMOKE_TEST_ENABLED = True

HTCONDOR_REQUEST_CPUS = 2
HTCONDOR_REQUEST_MEMORY = "6GB"
HTCONDOR_REQUEST_DISK = "5GB"
# "auto" calibrates each generation from the smoke test or preceding generation.
HTCONDOR_JOB_TIMEOUT_MODE = "auto"  # "auto" or "fixed"
HTCONDOR_JOB_TIMEOUT_SEC = 60 * 60
# Multiplies every effective disk request after automatic calibration.
HTCONDOR_REQUEST_DISK_MULTIPLIER = 1.0
HTCONDOR_REQUIREMENTS = '(OpSys == "WINDOWS") && (TARGET.YADOF_RAMDISK =?= True)'
HTCONDOR_ENVIRONMENT = (
    "USERPROFILE=._home HOME=._home APPDATA=._appdata "
    "LOCALAPPDATA=._localappdata TEMP=._tmp TMP=._tmp "
    "YADOF_HFSS_JOB_CPUCORE=4 YADOF_HFSS_PARALLEL_TASKS=1 "
    "YADOF_HFSS_NON_GRAPHICAL=1 YADOF_HFSS_PIN_RETRIES=1 "
    "YADOF_HFSS_RETRY_CPUCORE=1 "
    f"ANSYSLMD_LICENSE_FILE={os.environ.get('ANSYSLMD_LICENSE_FILE', '1055@localhost')}"
)

OPTIMIZE_POPULATION_SIZE = 200
