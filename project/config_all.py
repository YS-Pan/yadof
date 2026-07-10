from __future__ import annotations

import os
from pathlib import Path

try:
    from . import config as key_config
except ImportError:
    import config as key_config

# =============================================================================
# Derived project paths
# =============================================================================

PROJECT_ROOT = Path(__file__).resolve().parent
JOBS_DIR = getattr(key_config, "JOBS_DIR", PROJECT_ROOT / "jobs")
SURROGATE_CHECKPOINT_DIR = getattr(
    key_config,
    "SURROGATE_CHECKPOINT_DIR",
    PROJECT_ROOT / "surrogate" / "checkpoints",
)

# =============================================================================
# Evaluation backend
# =============================================================================

EVALUATION_MODE = getattr(key_config, "EVALUATION_MODE", "local")
EVALUATION_TIMEOUT_SEC = getattr(key_config, "EVALUATION_TIMEOUT_SEC", 6 * 60 * 60)
LOCAL_EVALUATION_MAX_WORKERS = getattr(key_config, "LOCAL_EVALUATION_MAX_WORKERS", 1)

# =============================================================================
# HTCondor backend
# =============================================================================

HTCONDOR_SUBMIT_EXE = getattr(key_config, "HTCONDOR_SUBMIT_EXE", "condor_submit")
HTCONDOR_REMOVE_EXE = getattr(key_config, "HTCONDOR_REMOVE_EXE", "condor_rm")
HTCONDOR_EXECUTABLE_MODE = getattr(key_config, "HTCONDOR_EXECUTABLE_MODE", "workflow")
HTCONDOR_PYTHON_EXE = getattr(key_config, "HTCONDOR_PYTHON_EXE", "python")
HTCONDOR_POLL_SEC = getattr(key_config, "HTCONDOR_POLL_SEC", 30.0)
HTCONDOR_REQUEST_CPUS = getattr(key_config, "HTCONDOR_REQUEST_CPUS", 1)
HTCONDOR_REQUEST_MEMORY = getattr(key_config, "HTCONDOR_REQUEST_MEMORY", "4GB")
HTCONDOR_REQUEST_DISK = getattr(key_config, "HTCONDOR_REQUEST_DISK", "2GB")
HTCONDOR_LOAD_PROFILE = getattr(key_config, "HTCONDOR_LOAD_PROFILE", True)
HTCONDOR_RUN_AS_OWNER = getattr(key_config, "HTCONDOR_RUN_AS_OWNER", False)
HTCONDOR_REQUIREMENTS = getattr(key_config, "HTCONDOR_REQUIREMENTS", '(OpSys == "WINDOWS") && (TARGET.YADOF_RAMDISK =?= True)')
HTCONDOR_ALLOWED_MACHINES = tuple(getattr(key_config, "HTCONDOR_ALLOWED_MACHINES", ()))
HTCONDOR_EXCLUDED_MACHINES = tuple(getattr(key_config, "HTCONDOR_EXCLUDED_MACHINES", ()))

# =============================================================================
# Workflow-side HFSS defaults passed into prepared jobs
# =============================================================================

HFSS_JOB_CPUCORE = getattr(key_config, "HFSS_JOB_CPUCORE", HTCONDOR_REQUEST_CPUS)
HFSS_PARALLEL_TASKS = getattr(key_config, "HFSS_PARALLEL_TASKS", 1)
HFSS_NON_GRAPHICAL = getattr(key_config, "HFSS_NON_GRAPHICAL", True)
HFSS_PIN_RETRIES = getattr(key_config, "HFSS_PIN_RETRIES", 1)
HFSS_RETRY_CPUCORE = getattr(key_config, "HFSS_RETRY_CPUCORE", 1)
ANSYS_LICENSE_SERVER = getattr(
    key_config,
    "ANSYS_LICENSE_SERVER",
    os.environ.get("ANSYSLMD_LICENSE_FILE", "1055@localhost"),
)

_HTCONDOR_BASE_ENVIRONMENT = (
    "USERPROFILE=._home",
    "HOME=._home",
    "APPDATA=._appdata",
    "LOCALAPPDATA=._localappdata",
    "TEMP=._tmp",
    "TMP=._tmp",
    f"YADOF_HFSS_JOB_CPUCORE={int(HFSS_JOB_CPUCORE)}",
    f"YADOF_HFSS_PARALLEL_TASKS={int(HFSS_PARALLEL_TASKS)}",
    f"YADOF_HFSS_NON_GRAPHICAL={1 if bool(HFSS_NON_GRAPHICAL) else 0}",
    f"YADOF_HFSS_PIN_RETRIES={int(HFSS_PIN_RETRIES)}",
    f"YADOF_HFSS_RETRY_CPUCORE={int(HFSS_RETRY_CPUCORE)}",
)
HTCONDOR_ENVIRONMENT = getattr(
    key_config,
    "HTCONDOR_ENVIRONMENT",
    " ".join(
        _HTCONDOR_BASE_ENVIRONMENT
        + ((f"ANSYSLMD_LICENSE_FILE={ANSYS_LICENSE_SERVER}",) if ANSYS_LICENSE_SERVER else ())
    ),
)

# =============================================================================
# Optimizer
# =============================================================================

OPTIMIZE_POPULATION_SIZE = getattr(key_config, "OPTIMIZE_POPULATION_SIZE", 200)
OPTIMIZE_RANDOM_SEED = getattr(key_config, "OPTIMIZE_RANDOM_SEED", 20260624)
OPTIMIZE_NSGA3_REF_DIR_METHOD = getattr(key_config, "OPTIMIZE_NSGA3_REF_DIR_METHOD", "das-dennis")
OPTIMIZE_NSGA3_PARTITIONS = getattr(key_config, "OPTIMIZE_NSGA3_PARTITIONS", None)
OPTIMIZE_REFILL_ATTEMPTS = getattr(key_config, "OPTIMIZE_REFILL_ATTEMPTS", 8)
OPTIMIZE_ARCHIVE_KEY_DECIMALS = getattr(key_config, "OPTIMIZE_ARCHIVE_KEY_DECIMALS", 10)
OPTIMIZE_CROSSOVER_PROBABILITY = getattr(key_config, "OPTIMIZE_CROSSOVER_PROBABILITY", 0.85)
OPTIMIZE_MUTATION_PROBABILITY = getattr(key_config, "OPTIMIZE_MUTATION_PROBABILITY", 0.35)
OPTIMIZE_CROSSOVER_ETA = getattr(key_config, "OPTIMIZE_CROSSOVER_ETA", 10.0)
OPTIMIZE_MUTATION_ETA = getattr(key_config, "OPTIMIZE_MUTATION_ETA", 10.0)
OPTIMIZE_DIM_MUT_PER_INDIVIDUAL = getattr(key_config, "OPTIMIZE_DIM_MUT_PER_INDIVIDUAL", 7)

# =============================================================================
# GPSAF surrogate assistance
# =============================================================================

OPTIMIZE_SURROGATE_ALPHA = getattr(key_config, "OPTIMIZE_SURROGATE_ALPHA", 3)
OPTIMIZE_SURROGATE_BETA = getattr(key_config, "OPTIMIZE_SURROGATE_BETA", 3)
OPTIMIZE_SURROGATE_GAMMA = getattr(key_config, "OPTIMIZE_SURROGATE_GAMMA", 0.5)
OPTIMIZE_SURROGATE_EXPLORATION_FRACTION = getattr(
    key_config,
    "OPTIMIZE_SURROGATE_EXPLORATION_FRACTION",
    0.10,
)
OPTIMIZE_SURROGATE_MAX_TRAINING_LAG = getattr(key_config, "OPTIMIZE_SURROGATE_MAX_TRAINING_LAG", 2)

# =============================================================================
# Surrogate model
# =============================================================================

SURROGATE_RELATIVE_ERROR_EPS = getattr(key_config, "SURROGATE_RELATIVE_ERROR_EPS", 1e-8)
SURROGATE_CONSTANT_ATOL = getattr(key_config, "SURROGATE_CONSTANT_ATOL", 1e-12)
SURROGATE_TARGET_SCALE_FLOOR = getattr(key_config, "SURROGATE_TARGET_SCALE_FLOOR", 1e-6)
SURROGATE_TORCH_DEVICE = getattr(key_config, "SURROGATE_TORCH_DEVICE", "auto")
SURROGATE_INR_EPOCHS = getattr(key_config, "SURROGATE_INR_EPOCHS", 32)
SURROGATE_INR_ENSEMBLE_SIZE = getattr(key_config, "SURROGATE_INR_ENSEMBLE_SIZE", 3)
SURROGATE_INR_BATCH_SIZE = getattr(key_config, "SURROGATE_INR_BATCH_SIZE", 16)
SURROGATE_INR_LR = getattr(key_config, "SURROGATE_INR_LR", 1e-3)
SURROGATE_INR_WEIGHT_DECAY = getattr(key_config, "SURROGATE_INR_WEIGHT_DECAY", 1e-5)
SURROGATE_INR_LOSS_BETA = getattr(key_config, "SURROGATE_INR_LOSS_BETA", 0.05)
SURROGATE_INR_RELATIVE_LOSS_WEIGHT = getattr(key_config, "SURROGATE_INR_RELATIVE_LOSS_WEIGHT", 0.15)
SURROGATE_INR_RELATIVE_LOSS_EPS = getattr(key_config, "SURROGATE_INR_RELATIVE_LOSS_EPS", 0.05)
SURROGATE_RAWDATA_IMPORTANCE_FLOOR = getattr(key_config, "SURROGATE_RAWDATA_IMPORTANCE_FLOOR", 0.25)
SURROGATE_RAWDATA_IMPORTANCE_BOOST = getattr(key_config, "SURROGATE_RAWDATA_IMPORTANCE_BOOST", 2.0)
SURROGATE_MAX_NONFINITE_FRACTION = getattr(key_config, "SURROGATE_MAX_NONFINITE_FRACTION", 0.20)
SURROGATE_INR_X_LATENT_DIM = getattr(key_config, "SURROGATE_INR_X_LATENT_DIM", 96)
SURROGATE_INR_FIELD_EMB_DIM = getattr(key_config, "SURROGATE_INR_FIELD_EMB_DIM", 12)
SURROGATE_INR_COORD_FOURIER_FEATURES = getattr(key_config, "SURROGATE_INR_COORD_FOURIER_FEATURES", 24)
SURROGATE_INR_HIDDEN_DIM = getattr(key_config, "SURROGATE_INR_HIDDEN_DIM", 192)
SURROGATE_INR_HIDDEN_LAYERS = getattr(key_config, "SURROGATE_INR_HIDDEN_LAYERS", 3)
SURROGATE_INR_TRAIN_QUERY_CHUNK = getattr(key_config, "SURROGATE_INR_TRAIN_QUERY_CHUNK", 4096)
SURROGATE_INR_TRAIN_QUERY_SAMPLE_COUNT = getattr(key_config, "SURROGATE_INR_TRAIN_QUERY_SAMPLE_COUNT", 8192)
SURROGATE_INR_SAMPLE_BATCH_EVAL = getattr(key_config, "SURROGATE_INR_SAMPLE_BATCH_EVAL", 64)
SURROGATE_INR_QUERY_BATCH_EVAL = getattr(key_config, "SURROGATE_INR_QUERY_BATCH_EVAL", 8192)
SURROGATE_INR_BOOTSTRAP_MEMBERS = getattr(key_config, "SURROGATE_INR_BOOTSTRAP_MEMBERS", True)
SURROGATE_INR_BOOTSTRAP_FRACTION = getattr(key_config, "SURROGATE_INR_BOOTSTRAP_FRACTION", 1.0)
