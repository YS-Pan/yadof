"""Runtime settings for the external-PyChrono trebuchet task."""

EVALUATION_MODE = "fast"
EVALUATION_TIMEOUT_SEC = 120.0
FAST_EVALUATION_MAX_WORKERS = 4
FAST_EVALUATION_MEMORY_MIB_PER_WORKER = 768
FAST_EVALUATION_SCRATCH_DISK_KIB_PER_WORKER = 16384
OPTIMIZE_POPULATION_SIZE = 100
OPTIMIZE_SMOKE_TEST_ENABLED = True
OPTIMIZE_RANDOM_SEED = 20260811

# User-confirmed surrogate benchmark case. The values below describe this working
# directory's current runtime profile; they do not assign an experimental role.
# Benchmark arms and comparison protocol are selected by the benchmark runner.
OPTIMIZE_SURROGATE_ALPHA = 3
OPTIMIZE_SURROGATE_BETA = 3
