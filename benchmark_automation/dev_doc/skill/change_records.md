# Change Record Contract

## Authority

The yadof repository keeps one historical record per completed repository change
under root `dev_doc/change_records/`. Benchmark changes use that shared location so
one commit does not acquire duplicate narratives. The record must name the
benchmark files and link to nested current-view documents when useful.

## Reading

Do not read records by default. Read a targeted record only when the reason behind
a past benchmark decision is necessary, current work conflicts with prior intent,
or the user requests history. Current architecture and blueprints override it.

## Maintenance

Follow the root naming/content contract. Record the completed problem, change,
rationale, impact, verification, and remaining work. Unresolved future work belongs
in a benchmark-local toDo, not in a change record.
