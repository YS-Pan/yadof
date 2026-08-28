# 2026-08-28 10:48 - Implement Component-Owned Configuration

## Context

- Core `yadof.config` still declared search, GPSAF, and conditional-INR settings
  even though workspaces already selected and composed those components in
  `submit/optimization.py`.
- Component implementations consequently mixed ambient `LoadedConfig` reads,
  module defaults, and runtime fallbacks. This duplicated ownership and provided a
  temporary-override path around the strategy factory.
- The accepted migration is a direct cutover: no Pydantic, aliases, deprecation
  period, automatic rewrite, `UNSET` conflict handling, or algorithm temporary
  overrides.

## Ownership inventory

- `OPTIMIZE_POPULATION_SIZE`, `OPTIMIZE_RANDOM_SEED`,
  `OPTIMIZE_SMOKE_TEST_ENABLED`, and
  `OPTIMIZE_SURROGATE_MAX_TRAINING_LAG` remain generation-hot campaign policy.
- `OPTIMIZE_ARCHIVE_KEY_DECIMALS` remains core because archive lookup and
  posterior-assisted candidate exclusion share the same campaign identity rule.
- `SURROGATE_RELATIVE_ERROR_EPS` remains core because the public surrogate viewer,
  rather than one trainable component, owns that diagnostic policy.
- Recorder paths/capacities remain session-frozen core policy. Workspace path
  resolution, layer precedence, provenance, and generation reload remain core.
- Pymoo crossover, mutation, refill, and NSGA-III reference-direction values are
  owned by `pymoo_ga()` / `pymoo_nsga3()`.
- GPSAF assistance values are owned by `gpsaf()`.
- Conditional-INR validation, device, architecture, training, batching, and
  bootstrap values are owned by `conditional_inr()` and its internal frozen
  settings snapshot.
- Hierarchical-CAE device and training values are explicit
  `hierarchical_cae()` kwargs; the former `train_config=` factory ingress was
  removed. Task rawData schema and quality-policy value objects remain task-owned.
- The surrogate viewer now selects its own available device and does not consume a
  trainable component setting.

## Change

- Replaced parallel core default/type/name declarations with one standard-library
  `SettingSpec` table that derives defaults, legal names, primitive validation,
  reload/path metadata, and `describe()` data while preserving per-layer eager
  validation and immutable `LoadedConfig` behavior.
- Added a small primitive validation module and module-local frozen settings for
  Pymoo, GPSAF, and conditional-INR. Public factories expose explicit keyword-only
  parameters; they accept neither `settings=` nor unrestricted `**kwargs`.
- Bound resolved settings to component instances and passed them narrowly through
  strategy identity, Pymoo/GPSAF backends, surrogate scheduler/runtime, checkpoint
  recovery, and posterior sampling. Population, random seed, archive precision,
  and maximum training lag are added separately as campaign policy.
- Replaced conditional-INR semantic payload labels with factory keyword names.
  This is the one-time direct-cutover namespace representation; it leaves the
  checkpoint artifact schema unchanged and thereafter changes only with resolved
  semantic values. Pre-cutover workspaces already require source migration and do
  not recover through a compatibility namespace.
- Migrated the package starter workspace, examples, editable benchmark baselines,
  strategy templates, tests, architecture, module/file blueprints, terminology,
  and user documentation. Benchmark strategy templates are now selected per case
  so each complete `optimization.py` owns the case's component parameters.
- Left tracked preregistrations, canary evidence, prior run artifacts, and baseline
  creation fingerprints unchanged. Those fingerprints record creation provenance;
  the runner freezes the actual current baseline fingerprint in each new run.

## One-time manual migration

Move these values from workspace `config.py` to
`submit/optimization.py:build_optimization()`:

| Removed config name | Explicit factory keyword |
| --- | --- |
| `OPTIMIZE_NSGA3_REF_DIR_METHOD` | `pymoo_nsga3(reference_direction_method=...)` |
| `OPTIMIZE_NSGA3_PARTITIONS` | `pymoo_nsga3(reference_direction_partitions=...)` |
| `OPTIMIZE_REFILL_ATTEMPTS` | `pymoo_ga(refill_attempts=...)` / `pymoo_nsga3(refill_attempts=...)` |
| `OPTIMIZE_CROSSOVER_PROBABILITY` | Pymoo factories: `crossover_probability=...` |
| `OPTIMIZE_MUTATION_PROBABILITY` | Pymoo factories: `mutation_probability=...` |
| `OPTIMIZE_CROSSOVER_ETA` | Pymoo factories: `crossover_eta=...` |
| `OPTIMIZE_MUTATION_ETA` | Pymoo factories: `mutation_eta=...` |
| `OPTIMIZE_DIM_MUT_PER_INDIVIDUAL` | Pymoo factories: `mutated_dimensions_per_individual=...` |
| `OPTIMIZE_SURROGATE_ALPHA` | `gpsaf(alpha=...)` |
| `OPTIMIZE_SURROGATE_BETA` | `gpsaf(beta=...)` |
| `OPTIMIZE_SURROGATE_GAMMA` | `gpsaf(gamma=...)` |
| `OPTIMIZE_SURROGATE_EXPLORATION_FRACTION` | `gpsaf(exploration_fraction=...)` |
| `SURROGATE_CONSTANT_ATOL` | `conditional_inr(constant_atol=...)` |
| `SURROGATE_TARGET_SCALE_FLOOR` | `conditional_inr(target_scale_floor=...)` |
| `SURROGATE_TORCH_DEVICE` | Selected surrogate factory: `device=...` |
| `SURROGATE_INR_EPOCHS` | `conditional_inr(epochs=...)` |
| `SURROGATE_INR_ENSEMBLE_SIZE` | `conditional_inr(ensemble_size=...)` |
| `SURROGATE_INR_BATCH_SIZE` | `conditional_inr(batch_size=...)` |
| `SURROGATE_INR_LR` | `conditional_inr(learning_rate=...)` |
| `SURROGATE_INR_WEIGHT_DECAY` | `conditional_inr(weight_decay=...)` |
| `SURROGATE_INR_LOSS_BETA` | `conditional_inr(loss_beta=...)` |
| `SURROGATE_MAX_NONFINITE_FRACTION` | `conditional_inr(max_nonfinite_fraction=...)` |
| `SURROGATE_INR_X_LATENT_DIM` | `conditional_inr(x_latent_dim=...)` |
| `SURROGATE_INR_FIELD_EMB_DIM` | `conditional_inr(field_embedding_dim=...)` |
| `SURROGATE_INR_COORD_FOURIER_FEATURES` | `conditional_inr(coordinate_fourier_features=...)` |
| `SURROGATE_INR_HIDDEN_DIM` | `conditional_inr(hidden_dim=...)` |
| `SURROGATE_INR_HIDDEN_LAYERS` | `conditional_inr(hidden_layers=...)` |
| `SURROGATE_INR_TRAIN_QUERY_CHUNK` | `conditional_inr(train_query_chunk=...)` |
| `SURROGATE_INR_TRAIN_QUERY_SAMPLE_COUNT` | `conditional_inr(train_query_sample_count=...)` |
| `SURROGATE_INR_SAMPLE_BATCH_EVAL` | `conditional_inr(sample_batch_eval=...)` |
| `SURROGATE_INR_QUERY_BATCH_EVAL` | `conditional_inr(query_batch_eval=...)` |
| `SURROGATE_INR_BOOTSTRAP_MEMBERS` | `conditional_inr(bootstrap_members=...)` |
| `SURROGATE_INR_BOOTSTRAP_FRACTION` | `conditional_inr(bootstrap_fraction=...)` |

The core keys listed in the ownership inventory stay in `config.py`. The old
component names now fail as unknown core settings in workspace files and temporary
overrides.

## Validation

- Built `dist/yadof-0.4.1-py3-none-any.whl`, force-reinstalled it with no editable
  source path, and verified import origin under the outer workspace `.venv`.
- Verified the new settings modules are wheel members and all five public factory
  signatures are explicit. An isolated ordinary import loaded none of Torch,
  BoTorch, or `pymoo.algorithms`.
- Parsed all non-frozen Python sources with `ast` and verified no active source or
  editable benchmark template retained a removed uppercase component key.
- Installed-wheel focused matrix: 156 passed.
- Installed-wheel full suite: 350 passed.
- `structural-canary` no-write plan succeeded with three cells and 37 planned
  attempted evaluations. Preflight passed 7/7 checks, including both migrated
  strategies and the installed package. No simulator or benchmark run was started.

## Impact

- Repository workspaces now have one algorithm-parameter source:
  `submit/optimization.py` factory kwargs. External workspaces using a removed key
  fail until manually migrated with the table above.
- Core precedence, provenance, path safety, campaign reload, recorder freezing,
  strategy-switch, checkpoint publication/recovery, and real-data-only surrogate
  contracts remain covered by the passing installed-wheel suite.
- Adding another algorithm or surrogate no longer requires registering its
  dedicated parameters in `yadof.config`.
