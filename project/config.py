from __future__ import annotations

# Key settings users are most likely to edit for a new optimization campaign.

EVALUATION_MODE = "distributed"  # "local" or "distributed"
EVALUATION_TIMEOUT_SEC = 12 * 60 * 60

HTCONDOR_REQUEST_CPUS = 1
HTCONDOR_REQUEST_MEMORY = "12GB"
HTCONDOR_REQUEST_DISK = "5GB"

HFSS_JOB_CPUCORE = HTCONDOR_REQUEST_CPUS
HFSS_PARALLEL_TASKS = 1
HFSS_NON_GRAPHICAL = True

OPTIMIZE_POPULATION_SIZE = 200
