# Create the code-first yadof-benchmark package

## Problem

The repository benchmark runner was a source-checkout tool whose external study
file imposed one fixed comparison matrix. That format could not naturally express
future multi-stage comparisons, different budgets, conditional setup, or durable
user postprocessing. Its two root entry files also prevented normal Python package
installation and did not provide workspace initialization or version-matched user
documentation.

## Decision

Replace the source-checkout tool with the independent `yadof-benchmark`
distribution, developed beside yadof. The distribution imports only public yadof
behavior; yadof does not depend on benchmark orchestration or concrete baseline
resources. This preserves the framework/task boundary while making the benchmark
CLI, API, baselines, and user documents installable together.

Adopt a hard Python-only workflow contract. `yadof-benchmark init` creates a
workspace whose user-owned `benchmark.py` declares complete strategies, any number
of comparison matrices, execution policy, and named top-level postprocessors
through a small `Benchmark` builder. Remove the former study parser and public
study functions without aliases or migration behavior. Change the serialized run
identity to `yadof.benchmark.workflow-run` so old plans fail closed instead of
being partially interpreted.

Rename the old command and facade responsibilities directly to package `cli.py`
and `api.py`. Keep opaque complete `optimization.py` modules as the algorithm
boundary; no algorithm registry or algorithm-specific configuration was added.

## Implementation

- Added distribution metadata, the `yadof-benchmark` console script, explicit
  `yadof_benchmark` public API, module entry point, and authoritative package
  version.
- Added non-overwriting workspace initialization with `.benchmark/workspace.json`,
  `benchmark.py`, and empty `resources`, `runs`, `visualizations`, `reports`, and
  `temp` directories.
- Added code-first workflow loading, validation, immutable request contracts, and
  deterministic expansion across multiple comparison calls and heterogeneous
  budgets.
- Extended run provenance to snapshot `benchmark.py`, resources, baselines,
  complete strategies, `api.py`, `cli.py`, and the bounded run driver.
- Added attempt-based postprocessing after collection. Resume skips collected cells
  and successful callbacks while retrying failed or interrupted callbacks from the
  run-owned workflow snapshot.
- Packaged all three baseline workspaces, including their hidden yadof markers, and
  added five installed user documents exposed through `yadof-benchmark docs`.
- Replaced the old `benchmark_automation/` tree with `yadof-benchmark/`; the six
  ignored bytecode caches left after tracked-file migration were moved intact to
  the outer workspace `temp/legacy-benchmark-automation-caches-20260828` rather
  than deleted.
- Updated current yadof user/developer documentation, architecture vocabulary,
  module blueprints, and the active PCA/SVD acceptance handoff for the independent
  package and Python workspace contract. Historical change records and obsolete
  documents remain unchanged.

## Verification

- Source-tree focused suite: `13 passed` with a fresh absolute pytest base temp.
- Force-installed-wheel focused suite with source injection disabled: `13 passed`.
- Final `yadof_benchmark-0.1.0-py3-none-any.whl` contained 63 entries, including
  `api.py`, `cli.py`, five user documents, all three baseline markers, and no old
  entry filenames.
- The source distribution built successfully with 69 entries, including its
  `pyproject.toml`, two focused test files, five user documents, and all three
  hidden baseline markers.
- Force-installed the wheel without dependencies into the workspace `.venv`.
  Import origin resolved below `.venv/Lib/site-packages/yadof_benchmark` and
  reported version `0.1.0`.
- Installed console acceptance passed for help, documentation display, packaged
  discovery of all three baseline IDs, and creation of a fresh benchmark workspace.
- No simulator or measured benchmark run was started. Root yadof changes are
  content-only documentation, so the documented documentation-only validation
  exception applies; yadof itself was not rebuilt or reinstalled.

## Incidental-review result

The in-scope code/diff audit found no additional redundant compatibility branch,
algorithm registry, recorder schema, or release-generation marker requiring
removal. The package build temporarily exposed a missing hidden baseline marker;
the markers were recovered byte-for-byte from the current Git HEAD and the final
wheel inventory verifies them.
