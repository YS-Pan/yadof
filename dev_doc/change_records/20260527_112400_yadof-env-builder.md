# 2026-05-27 11:24 - yadof Environment Builder

## Context
- The project needs a repeatable Windows command script to create the Python environment used by distributed AEDT optimization.
- Dependency scanning showed core runtime dependencies on NumPy, pymoo, PyTorch, and PyAEDT/AEDT bindings, with optional plotting and test packages.

## Change
- Added `build_yadof_env.cmd` at the project root.
- The script creates or updates a Conda environment named `yadof`, installs runtime/test dependencies, verifies imports, and packs the environment to `yadof.tar.gz` in the project root.
- Runtime dependencies are installed with pip, while `conda-pack` and the base packaging tools are installed or repaired through Conda before packing.
- The script recreates an existing `yadof` environment by default and repairs Conda-managed `pip`, `setuptools`, and `wheel` before packing, avoiding `conda-pack` conflicts from pip-overwritten package metadata.

## Rationale
- A double-clickable CMD keeps setup consistent with the project's Windows-only operating assumptions.
- Packing with `conda-pack` creates a portable archive for deployment to machines whose project path may differ.

## Impact
- Run `build_yadof_env.cmd` on a machine with Conda and network access.
- The script recreates an existing `yadof` environment by default. Set `RECREATE_EXISTING_ENV=0` near the top of the CMD file to repair/update in place instead.

## Follow-Up
- If GPU-enabled PyTorch wheels are required for surrogate training performance, adjust the PyTorch install line to use the appropriate PyTorch CUDA wheel index for the target machines.
