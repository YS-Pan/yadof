# 2026-08-24 20:44 - Prefix Benchmark Runs With Numeric Date And Time

## Context

- Automatically named benchmark output directories used the compact UTC form
  `YYYYMMDDTHHMMSSZ`, so the boundary between date and time was not the requested
  underscore and the timestamp included non-numeric marker characters.

## Change

- Changed automatic benchmark run IDs to start with `YYYYMMDD_HHMMSS` while
  retaining UTC, the optional sanitized label, and the run-spec fingerprint.
- Added a fixed-time unit test and documented the output-name contract in the
  benchmark operator guide, architecture, and matching project/test blueprints.

## Rationale

- The underscore makes the date/time boundary explicit, and each component now
  consists only of digits without weakening the existing collision-resistant
  specification suffix or changing explicit `--run-id` behavior.

## Impact

- New automatically created benchmark run directories use the new prefix. Existing
  runs and explicitly supplied run IDs remain readable and unchanged.

## Follow-Up

- None.
