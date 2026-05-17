# Module prompt: config

## Intent
- Provide a small shared configuration surface for cross-module settings that are not task-specific source code.
- Keep problem shape and objective schema out of config; those belong to `job_template.api`.
- Make local/default behavior explicit while leaving future distributed and surrogate-assisted tuning paths visible.

## Functionalities
- Defines root paths such as `PROJECT_ROOT`, `JOBS_DIR`, `SURROGATE_CHECKPOINT_DIR`, and `OPTIMIZE_CHECKPOINT_DIR`.
- Selects `EVALUATION_MODE`.
- Defines optimizer population, random seed, pymoo operator parameters, duplicate-key rounding, and refill behavior.
- Defines surrogate model, torch device selection, conditional-INR training, target scaling, interval, and error hyperparameters.
- Defines GPSAF surrogate assistance controls: `OPTIMIZE_SURROGATE_ALPHA`, `OPTIMIZE_SURROGATE_BETA`, and `OPTIMIZE_SURROGATE_GAMMA`.

## I/O Format
- Config values are imported directly by modules that need them.
- Paths are `Path` objects rooted in `project/`.
- Numeric controls should be simple Python scalars.

## Non-Obvious Techniques
- `OPTIMIZE_SURROGATE_ALPHA = 1` and `OPTIMIZE_SURROGATE_BETA = 0` keep the GPSAF entry point available while disabling surrogate calls.
- Variable count and objective count are deliberately absent from config and resolved through `job_template.api`.
- `JOBS_DIR` is a runtime location and may later point outside `project/jobs/`, such as to a memory disk.
- `SURROGATE_TORCH_DEVICE = "auto"` prefers CUDA, then XPU, then CPU; tests may force CPU and smaller INR dimensions for speed.
- `SURROGATE_ALPHA` is the minimum prediction interval width and is separate from GPSAF's `OPTIMIZE_SURROGATE_ALPHA`.

## Mutability Profile
- Users may tune config often during experiments.
- Avoid adding task-specific workflow logic or cost definitions here.
- When a new config value affects stored history interpretation, document the consequence in prompt and architecture docs.
