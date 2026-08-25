# 2026-08-25 08:14 - Make PyChrono Windows Launch Paths Safe

## Context

- Performance benchmark run `20260824_125218-dec8826b8054` completed 15 of 18
  cells. All three Chrono GPSAF cells failed in generation zero after every one of
  their 100 candidates reported `launch_failed` with Windows error 267; the three
  NSGA-III Chrono cells used the same physical task and completed.
- The failing arm's representative PyChrono child working directory was about 272
  characters, versus about 256 for the shorter arm identity. A standalone
  `subprocess` reproduction returned the same error for a 287-character working
  directory, including when the directory used a `\\?\` extended-path prefix.
- Shortening a benchmark run ID had previously avoided the limit, but that made
  adapter correctness depend on caller and experiment naming rather than the
  external-runtime boundary.

## Change

- Changed the packaged `chrono_com.py` adapter so every Windows candidate reserves
  a unique short directory in the parent temporary root and turns it into a
  junction targeting the original physical candidate scratch. The child uses that
  alias for `cwd`, request/result arguments, `TEMP`, and `TMP`; parent validation,
  evidence ownership, and cleanup continue to use the original scratch.
- The adapter removes the junction before physical scratch cleanup on success,
  child failure, timeout, cancellation, and launch/filesystem failure. If junction
  creation is unavailable, it falls back only to a physical scratch already within
  the Windows process current-directory limit; an over-limit path fails explicitly
  as `launch_failed` before child creation.
- Added a Windows regression that launches the packaged fake child with a physical
  candidate scratch longer than 280 characters and verifies finite evidence plus
  complete alias/scratch cleanup.
- Updated the normative subprocess contract, physical/process architecture, user
  adapter guidance, terminology, and adapter/test blueprints.
- Preserved the old immutable Chrono benchmark baseline and created selected
  identity `trebuchet-462d1201a592` with only the copied adapter refreshed. The
  benchmark configuration and operator guidance now select the new identity and no
  longer prescribe short run IDs as a correctness workaround.

## Rationale

- A candidate junction keeps the physical scratch below the caller-owned root and
  avoids duplicating or relocating request/result/rawData evidence. Its short path
  removes workspace, run, strategy, and evaluation names from the Windows child
  current-directory budget.
- Directory junction creation uses the Windows filesystem API directly, requires
  no shell command or symbolic-link privilege, remains candidate-unique under
  concurrency, and leaves the absolute interpreter plus process-isolated DLL path
  policy unchanged.
- A new frozen baseline retains reproducibility for old run specifications while
  allowing future benchmark cells to exercise the package-level fix.

## Verification

- Built and force-reinstalled `yadof-0.4.0-py3-none-any.whl`; import origin was the
  sibling `.venv/Lib/site-packages/yadof` installation.
- Packaged PyChrono fake-child contract: `14 passed`, including the new over-280-
  character physical scratch regression.
- Benchmark unit suite: `43 passed`.
- Selected Chrono adapter-smoke plan succeeded; preflight passed 5/5 checks.
- Real PyChrono fast smoke
  `20260825_001100-chrono-adapter-long-path-regression-abcdefghijklmnopqrstuvwxyz0123456789`
  completed through a representative physical child scratch/request path of about
  298/311 characters. Its four midpoint costs exactly matched the previous frozen
  baseline: `(1.0, 0.3304246044224697, 0.39247639835398695,
  0.016402541818995975)`.
- Complete repository pytest discovery passed: `278 passed`.

## Follow-Up

- Existing user workspaces keep their explicitly copied adapter files by design;
  they receive this fix only when the user deliberately replaces or merges their
  local `chrono_com.py`. New copies use the fixed packaged resource.
- The failed benchmark run remains immutable diagnostic evidence. A complete
  performance rerun is a separate long-running action under the benchmark's
  explicit cost/authorization policy.
