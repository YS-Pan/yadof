# Module blueprint: tools

## Intent
- Provide optional, user-launched utilities for inspecting or maintaining project data.
- Keep all tool behavior outside the core optimization dependency graph.
- Surface recorded-data history in ways that help long campaigns be explained and debugged.

## Functionalities
- `viewCost.py` reads `recorded_data.api.get_historical_results()`, dynamically calculates current costs, prints a Pareto-oriented summary, and optionally saves a PNG plot.
- Cost plots mark objective series, combined-cost trend, Pareto points, optimization-start metadata, and job-static-hash changes.
- `viewTime.py` reads workflow-owned top-level `started_at`/`ended_at` fields from recorded individual rows when available, with legacy nested metadata only as a fallback.
- `hfss_get_para_and_range.py` reads optimization-enabled variables from a `.aedt` file and regenerates `job_template/parameters_constraints.py` in the current `Parameter` format.
- Future tools may generate parameter files, inspect simulator templates, back up records, or visualize job timing.

## I/O Format
- Tool inputs come through public project APIs or user-provided command-line arguments.
- Tool outputs may include console summaries, PNG plots under `project/tools/`, generated helper files, or external backups.
- Tools may be flexible and inspect internal files when useful, but core runtime must not call tools.

## Non-Obvious Techniques
- `viewCost.py` intentionally reads costs through `recorded_data` instead of legacy `para_cost.jsonl` files.
- Static-hash changes are plotted from job metadata so task definition changes are visible on cost timelines.
- Optimization and generation boundaries can now come directly from individual `optimization_index` and `generation_index` fields, with `optMeta` joins still useful for run-level diagnostics.
- The Pareto table is rendered in ASCII-safe text to keep terminal output robust.
- HFSS/PyAEDT parameter extraction is environment-sensitive. The current `Metal_recon_ant.aedt` design name is `HFSSDesign1`; passing an old design name can make PyAEDT select or create the wrong design context and return no optimization variables. If the project has exactly one design, prefer omitting `--design`, or pass `--design HFSSDesign1` explicitly.
- AEDT startup also depends on the interactive Windows user profile and writable Ansys/PyAEDT folders. A VS Code click-run under the normal desktop user may succeed where a sandboxed or non-graphical command times out while starting gRPC or touching `Documents/Ansoft`. For Codex-run smoke checks, use the correct design name, allow a long timeout, and run outside the sandbox when AEDT needs the real user profile.
- `hfss_get_para_and_range.py` archives the old `parameters_constraints.py` only after it has found variables to write, so a failed extraction should leave the current parameter file intact.

## Mutability Profile
- Tools can change quickly for user convenience.
- Tool changes should not force changes to `optimize`, `evaluate_manager`, `job_template`, `recorded_data`, or `surrogate`.
- If a tool depends on a public API shape, add or update tests before changing that API.
