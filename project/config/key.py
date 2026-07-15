from __future__ import annotations

# Key settings users are most likely to edit for a new optimization campaign.

EVALUATION_MODE = "distributed"  # "local" or "distributed"
EVALUATION_TIMEOUT_SEC = 12 * 60 * 60

HTCONDOR_REQUEST_CPUS = 1
HTCONDOR_REQUEST_MEMORY = "12GB"
HTCONDOR_REQUEST_DISK = "5GB"
# Multiplies every effective disk request after automatic calibration.
HTCONDOR_REQUEST_DISK_MULTIPLIER = 1.0

OPTIMIZE_POPULATION_SIZE = 200
