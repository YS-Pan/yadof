"""Runtime settings for the 1 GHz ninth-order SAW ladder task."""

EVALUATION_MODE = "fast"
EVALUATION_TIMEOUT_SEC = 60

FAST_EVALUATION_MAX_WORKERS = 64
FAST_RESOURCE_AUTODETECT_ENABLED = True
FAST_EVALUATION_CPUS_PER_WORKER = 1
FAST_EVALUATION_MEMORY_MIB_PER_WORKER = 256
FAST_EVALUATION_SCRATCH_DISK_KIB_PER_WORKER = 8192

OPTIMIZE_POPULATION_SIZE = 400
OPTIMIZE_SMOKE_TEST_ENABLED = True
OPTIMIZE_RANDOM_SEED = 20260807

# User-confirmed surrogate benchmark case.  The values below describe this working
# directory's current runtime profile; they do not assign an experimental role.
# Benchmark arms and comparison protocol must be confirmed separately.
OPTIMIZE_SURROGATE_ALPHA = 1
OPTIMIZE_SURROGATE_BETA = 0

# The current real-only, field-balanced trainer can use both 1201-point fields as
# full queries; no task-owned weighting is applied.
SURROGATE_INR_EPOCHS = 64
SURROGATE_INR_ENSEMBLE_SIZE = 3
SURROGATE_INR_TRAIN_QUERY_SAMPLE_COUNT = 8192
SURROGATE_INR_BOOTSTRAP_MEMBERS = True
SURROGATE_INR_BOOTSTRAP_FRACTION = 1.0

