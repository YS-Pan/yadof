# Architecture Contract

## Purpose and authority

`../architecture/` is the highest-priority current view of benchmark boundaries,
data flow, persistence, execution, recovery, progress, ETA, and evidence
invariants. It describes the system as it is, not the sequence of historical
changes.

## Reading

Read every Markdown file below `../architecture/` in full on the first benchmark-
development context pass. Begin with `00_architecture_index.md`. The root yadof
architecture remains authoritative where the installed package or workspace
contract is involved.

## Maintenance

Update the affected view when a change alters responsibilities, public JSON,
filesystem layout, state transitions, subprocess topology, terminal behavior,
timing estimation, recovery, or core invariants. Do not place future work here.
Historical records never override current architecture.
