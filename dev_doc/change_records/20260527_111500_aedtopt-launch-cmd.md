# 2026-05-27 11:15 - AedtOPT Launch CMD

## Context
- Distributed optimization should be started from a double-clickable Windows command script.
- The previous PowerShell test launcher could pick up the WindowsApps Python alias instead of the intended `AedtOPT` environment.

## Change
- Added `start_optimization_aedtopt.cmd` at the project root.
- Added `start_optimization_from_config.py` as the small Python launcher called by the CMD file.
- The CMD file activates the Conda environment named `AedtOPT`, sets only generation-count launch variables, and lets `project/config.py` provide optimizer/evaluation settings such as population size, random seed, evaluation mode, jobs directory, and HTCondor settings.

## Rationale
- Keeping environment activation in CMD avoids relying on the shell's default `python` command.
- Keeping optimizer settings in `project/config.py` avoids hard-coded population-size overrides in ad hoc launch scripts.

## Impact
- Run `start_optimization_aedtopt.cmd` from the submit machine after the HTCondor pool is configured.
- Edit `GENERATION_COUNT` and `START_GENERATION` near the top of the CMD file when changing the launch length.
