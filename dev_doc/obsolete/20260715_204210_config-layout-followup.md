# Follow Up The Config Package Layout

> Automatically archived on 2026-07-18 because the configured two-day lifetime
> expired strictly after 2026-07-17 20:42:10 local time.

## Context
- The 2026-07-15 config-boundary change moved campaign settings to
  `project/config/key.py`, `project/config/all.py`, and
  `project/config/specific/`.
- That change touches runtime imports, job preparation, job-local workflow imports,
  tests, current documentation, and the boundary between generic and
  software-specific code. A focused review has already fixed the terminology entry
  and a generic reload path that named the HFSS extension, but other incidental
  references may remain.

## Goal
- Current config-related code and current documentation encountered during normal
  work consistently use the config package layout and preserve the generic/specific
  boundary.
- Prepared jobs continue to receive the complete cache-free `config/` package,
  including active specific extensions.

## Guidance
- Apply this toDo only when normal work already opens a config module,
  `evaluate_manager` configuration/job-preparation code, a workflow that consumes
  job-local config, related tests, or current user/developer documentation. Do not
  perform a repository-wide search solely for this toDo.
- Replace an encountered current-view reference to retired `project/config.py` or
  `project/config_all.py` with the appropriate `config/key.py`, `config/all.py`, or
  `config/specific/` location. Do not rewrite historical change records or future
  package-design text merely because it describes a different layout.
- Keep `key.py` and `all.py` generic. Simulator- or vendor-specific settings,
  environment entries, and workflow defaults belong under `config/specific/`.
- Generic consumers may use the public `project.config.specific` extension boundary
  but must not import a concrete `specific/<software>.py` module. When changing a
  refresh path, preserve the order in which generic overrides, active extensions,
  and `all.py` are refreshed.
- When changing config-copy or refresh behavior, add or update a focused test that
  verifies the relevant prepared-job or runtime contract, then run the affected
  test path.

## Completion Rule
- Correct each safe, in-scope inconsistency found while this automatic toDo is
  active, and record any issue that needs a larger design decision.
- Keep this toDo active for incidental occurrences; do not treat one local fix as a
  complete audit.

## Obsolete Rule
- Automatic: archive two days after the timestamp in this filename. No
  user-defined condition applies.
