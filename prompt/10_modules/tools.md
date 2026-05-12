# Module prompt: tools

## Intent
- Provide optional, user-launched utilities for inspecting or maintaining project data.
- Keep all tool behavior outside the core optimization dependency graph.
- Surface recorded-data history in ways that help long campaigns be explained and debugged.

## Functionalities
- `viewCost.py` reads `recorded_data.api.get_historical_results()`, dynamically calculates current costs, prints a Pareto-oriented summary, and optionally saves a PNG plot.
- Cost plots mark objective series, combined-cost trend, Pareto points, optimization-start metadata, and job-static-hash changes.
- Future tools may generate parameter files, inspect simulator templates, back up records, or visualize job timing.

## I/O Format
- Tool inputs come through public project APIs or user-provided command-line arguments.
- Tool outputs may include console summaries, PNG plots under `project/tools/`, generated helper files, or external backups.
- Tools may be flexible and inspect internal files when useful, but core runtime must not call tools.

## Non-Obvious Techniques
- `viewCost.py` intentionally reads costs through `recorded_data` instead of legacy `para_cost.jsonl` files.
- Static-hash changes are plotted from job metadata so task definition changes are visible on cost timelines.
- The Pareto table is rendered in ASCII-safe text to keep terminal output robust.

## Mutability Profile
- Tools can change quickly for user convenience.
- Tool changes should not force changes to `optimize`, `evaluate_manager`, `job_template`, `recorded_data`, or `surrogate`.
- If a tool depends on a public API shape, add or update tests before changing that API.
