# 2026-08-29 11:37 - Restore Benchmark Performance Scale

## Context

Historical benchmark runs and the rewritten public example allowed a dozen
individuals and only a few generations to be presented as performance evidence.
The originating user decisions set a hard performance-cell floor of 100
individuals per generation and 20 generations, while separately requiring
baseline difficulty that takes a pure NSGA-III reference nearer 10000 evaluations
to converge. Later algorithm-debugging work explicitly reduced a state/arm to one
seed for speed; that evidence was exploratory rather than a replacement for a
stronger multi-seed campaign.

## Change

- Made workflow freeze reject every `evidence="performance"` comparison with
  population below 100 or generations below 20. The error names the invalid
  comparison and the 2000-planned-real-evaluation floor, then directs smaller work
  to the structural class.
- Derived a separate replication scope from each explicit seed list. Single-seed
  performance comparisons are `exploratory`; performance comparisons with two or
  more seeds are `multi-seed`; structural comparisons remain `structural` because
  their seeds cannot support a performance claim.
- Propagated that scope and its fixed notice through full and bounded plans, cells,
  result rows, CSV/JSON reports, Markdown, workspace indexes, and read-only inspect.
- Replaced the scaffold and API's former 12 × 20 example with an explicitly
  structural-only 12 × 3 example. User and developer documents now distinguish
  the hard 2000-evaluation validity floor from the roughly 10000-evaluation
  non-surrogate difficulty calibration and state that seed count remains explicit
  and configurable rather than fixed at three.
- Updated the root project blueprint, terminology, and active restoration toDo to
  record completion of subsection 6 without claiming paired metrics, recovery, or
  concurrency work from subsections 7--9.

## Rationale

Evidence classification remains an explicit author decision, but a performance
label is invalid when its budget cannot meet the user's minimum. Enforcing the two
dimensions independently prevents a one-generation oversized population from
evading the convergence-length requirement. Difficulty itself stays task-owned:
the generic runner cannot decide from counts whether a baseline is easily solved.

Deriving exploratory scope from the objective fact of one configured seed avoids
adding another authoring switch that could contradict the plan. Multiple seeds do
not automatically prove robustness or significance, so the runner reports their
scope without turning the historical count of three into a scientific constant.

## Impact

Existing immutable runs continue through their run-owned drivers. New structural
workflows may retain any positive budget. New performance workflows below either
hard floor fail during load/plan before run creation or simulator execution.
Single-seed performance workflows remain supported for fast iteration, but their
artifacts carry an explicit exploratory boundary.

## Verification

- Parsed all changed Python files successfully before packaging.
- Built `yadof_benchmark-0.1.0-py3-none-any.whl`, force-reinstalled it without
  dependencies, and confirmed version `0.1.0` imported from
  `.venv/Lib/site-packages/yadof_benchmark`.
- The complete installed-wheel focused suite passed: `37 passed in 4.01s`, with
  repository-source injection removed, pytest cache disabled, bytecode writes
  disabled, and a fresh absolute pytest base temp directory.
- Installed `docs show api.md` exposed the 100 × 20 floor, 10000-evaluation
  difficulty reference, and exploratory single-seed rule.
- No simulator, adapter smoke, structural canary, or performance campaign was
  executed. All behavior verification used deterministic package/contract tests.

## Recurring Checks

The bounded in-scope review found no component-configuration migration omission,
incidental release marker, reliable-recording inconsistency, or safely removable
code redundancy. The results module centralizes historical fallback and
replication summarization rather than repeating seed interpretation across output
surfaces; all recurring automatic toDos remain active.
