# 4+1 Scenarios

## Resume after checkout changes

A run created before a checkout edit resumes through its own execution, strategy,
history, and baseline snapshots. Current hashes may differ without invalidating the
run. An unfinished legacy run without a complete execution snapshot stops with an
explicit restart/migration diagnostic; completed legacy evidence stays readable.

## Plan and preflight

An agent runs bounded `plan`, confirms full performance scale and risk, then runs
`preflight`. Neither launches a simulator. Expanded JSON is requested only for a
named omitted field.

## Detached performance run

After explicit authorization, the agent starts foreground `run` in a visible
separate PowerShell window and ends its turn without polling. Rich shows one active
cell row above global cells; early evaluations visibly advance even in a 2,000-row
cell. All child output remains in command logs.

## Scheduled status loop

A later turn runs `inspect --run-id ...` with the same runs root. If execution is
running, it reads `run.timing.estimated_remaining_sec`, completion UTC, confidence,
active phase/progress, inactivity age, and basis support. A matched prior-run cell
normally anchors the whole-cell remainder; timestamped completed generations can
raise it when later phases are growing. The automation schedules another check near
that estimate; a low-confidence lower-bound result may justify an earlier check.
It does not resume, kill, collect, or modify the run merely because it is still
active.

If the run is terminal, the turn collects and reports, evaluates descriptive
results and validity, modifies tracked algorithms only under the full-performance
policy, then starts a new immutable run when authorized. Each iteration receives a
new run ID and never rewrites earlier evidence.

## Failure diagnosis

`inspect` first exposes failed cells and latest command metadata. The agent reads
only that cell's finished metadata and one relevant log tail. It fixes a reusable
yadof or tracked input issue, never a measured workspace. Resume creates a linked
replacement attempt.

## Completed reporting

After completion, `collect` consumes public yadof surfaces and `report` builds
descriptive evidence. The agent starts with bounded JSON and the HV table, then
opens narrative or targeted stable fields only when needed. ETA and wall-clock
operation facts are not used to rank algorithms.
