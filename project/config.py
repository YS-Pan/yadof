from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
# Submit-side staging directory. Worker scratch disk is controlled by HTCondor
# EXECUTE on each worker, not by this path.
JOBS_DIR = PROJECT_ROOT / "jobs"
SURROGATE_CHECKPOINT_DIR = PROJECT_ROOT / "surrogate" / "checkpoints"

EVALUATION_MODE = "distributed"  # "local" or "distributed"
EVALUATION_TIMEOUT_SEC = 6 * 60 * 60
# Number of local workflow subprocesses to run at once. Keep this at 1 for
# simulator adapters that cannot safely run concurrently; raise it for pure
# Python or otherwise parallel-safe workflows.
LOCAL_EVALUATION_MAX_WORKERS = 10


def _env_csv_tuple(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.environ.get(name)
    if raw is None:
        return tuple(default)
    text = raw.strip()
    if not text or text.lower() in {"*", "all", "none"}:
        return ()
    return tuple(item.strip() for item in text.split(",") if item.strip())


HTCONDOR_SUBMIT_EXE = "condor_submit"
HTCONDOR_REMOVE_EXE = "condor_rm"
HTCONDOR_EXECUTABLE_MODE = "python"  # Direct yadof python executable; no cmd wrapper.
HTCONDOR_PYTHON_EXE = "C:/ProgramData/miniconda3/envs/yadof/python.exe"
HTCONDOR_POLL_SEC = 30.0
HTCONDOR_REQUEST_CPUS = 4
HTCONDOR_REQUEST_MEMORY = "8GB"
HTCONDOR_REQUEST_DISK = "5GB"
ANSYS_LICENSE_SERVER = os.environ.get("YADOF_HTCONDOR_ANSYS_LICENSE_SERVER") or "1055@localhost"
HTCONDOR_ENVIRONMENT = (
    "USERPROFILE=._home;"
    "HOME=._home;"
    "APPDATA=._appdata;"
    "LOCALAPPDATA=._localappdata;"
    "TEMP=._tmp;"
    "TMP=._tmp;"
    f"ANSYSLMD_LICENSE_FILE={ANSYS_LICENSE_SERVER};"
    "YADOF_HFSS_JOB_CPUCORE=4;"
    "YADOF_HFSS_PARALLEL_TASKS=1;"
    "YADOF_HFSS_NON_GRAPHICAL=1;"
    "YADOF_HFSS_PIN_RETRIES=1;"
    "YADOF_HFSS_RETRY_CPUCORE=1"
)
HTCONDOR_LOAD_PROFILE = True
HTCONDOR_RUN_AS_OWNER = False
HTCONDOR_REQUIREMENTS = '(OpSys == "WINDOWS") && (TARGET.YADOF_RAMDISK =?= True)'
# The current HFSS logs show DESKTOP-A2091 completing slot-account solves, while
# A2093/A2096 start AEDT but fail in HFSS engine/post-processing. Keep this as a
# configurable guardrail until those worker environments pass the same smoke test.
HTCONDOR_ALLOWED_MACHINES = _env_csv_tuple("YADOF_HTCONDOR_ALLOWED_MACHINES",())
HTCONDOR_EXCLUDED_MACHINES = _env_csv_tuple("YADOF_HTCONDOR_EXCLUDED_MACHINES", ())

OPTIMIZE_POPULATION_SIZE = 200
getenv = False
OPTIMIZE_RANDOM_SEED = 20260624

# Conditional INR deep-ensemble surrogate settings.
SURROGATE_RELATIVE_ERROR_EPS = 1e-8
SURROGATE_CONSTANT_ATOL = 1e-12
SURROGATE_TARGET_SCALE_FLOOR = 1e-6
SURROGATE_TORCH_DEVICE = "auto"
SURROGATE_INR_EPOCHS = 32
SURROGATE_INR_ENSEMBLE_SIZE = 3
SURROGATE_INR_BATCH_SIZE = 16
SURROGATE_INR_LR = 1e-3
SURROGATE_INR_WEIGHT_DECAY = 1e-5
SURROGATE_INR_LOSS_BETA = 0.05
SURROGATE_INR_RELATIVE_LOSS_WEIGHT = 0.15
SURROGATE_INR_RELATIVE_LOSS_EPS = 0.05
SURROGATE_RAWDATA_IMPORTANCE_FLOOR = 0.25
SURROGATE_RAWDATA_IMPORTANCE_BOOST = 2.0
SURROGATE_MAX_NONFINITE_FRACTION = 0.20
SURROGATE_INR_X_LATENT_DIM = 96
SURROGATE_INR_FIELD_EMB_DIM = 12
SURROGATE_INR_COORD_FOURIER_FEATURES = 24
SURROGATE_INR_HIDDEN_DIM = 192
SURROGATE_INR_HIDDEN_LAYERS = 3
SURROGATE_INR_TRAIN_QUERY_CHUNK = 4096
# Maximum sampled high-dimensional rawData query points used per training step.
# Scalar and 1D rawData slots are always included; full rawData is still
# retained and predicted. This limits stochastic training backprop for large
# 2D/3D fields on CPU-only machines.
SURROGATE_INR_TRAIN_QUERY_SAMPLE_COUNT = 8192
SURROGATE_INR_SAMPLE_BATCH_EVAL = 64
SURROGATE_INR_QUERY_BATCH_EVAL = 8192
SURROGATE_INR_BOOTSTRAP_MEMBERS = True
SURROGATE_INR_BOOTSTRAP_FRACTION = 1.0

# GPSAF surrogate-assistance controls.
# Set OPTIMIZE_SURROGATE_ALPHA = 1 and OPTIMIZE_SURROGATE_BETA = 0 to run the
# same GPSAF entrypoint without importing or calling project.surrogate.
# Increase alpha above 1 to add surrogate tournament pressure; increase beta
# above 0 to run simulated baseline-optimizer iterations on surrogate costs.
OPTIMIZE_SURROGATE_ALPHA = 3
OPTIMIZE_SURROGATE_BETA = 3
OPTIMIZE_SURROGATE_GAMMA = 0.5
OPTIMIZE_SURROGATE_EXPLORATION_FRACTION = 0.10
# The staggered surrogate schedule may use a model one or two generations behind
# real evaluations. Before submitting work that would use a three-generation-old
# model, the optimizer blocks until training catches up.
OPTIMIZE_SURROGATE_MAX_TRAINING_LAG = 2

OPTIMIZE_NSGA3_REF_DIR_METHOD = "das-dennis"
OPTIMIZE_NSGA3_PARTITIONS = None
OPTIMIZE_REFILL_ATTEMPTS = 8
OPTIMIZE_ARCHIVE_KEY_DECIMALS = 10
OPTIMIZE_CROSSOVER_PROBABILITY = 0.85
OPTIMIZE_MUTATION_PROBABILITY = 0.35
OPTIMIZE_CROSSOVER_ETA = 10.0
OPTIMIZE_MUTATION_ETA = 10.0
OPTIMIZE_DIM_MUT_PER_INDIVIDUAL = 7
