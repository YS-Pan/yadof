# 4+1 process view

Local mode prepares jobs and runs workflow subprocesses with bounded concurrency and
per-individual timeout. Distributed mode prepares the same payload, submits each job
to HTCondor, invokes after-submit surrogate scheduling, polls job-local output, owns
bounded memory/disk resubmission, enforces a separate whole-generation deadline, and
collects final ClassAd provenance.

Surrogate training has at most one background task per workspace. Scheduler and
model state maps are workspace-keyed and protected by locks. Clearing one workspace
waits/resets only its schedule/state. Persistence uses workspace-local locks and
atomic replacement for mutable files.

Completed population results are recorded as one atomic batch when possible. The
archive and manifest are copied/published once per batch, then costs are derived in
one query. A failed batch falls back to individual recording so one malformed result
does not discard otherwise valid evidence.
