# Architecture Contract

## Purpose And Authority

`architecture/` describes the current system from several viewpoints: how the
project is organized now, which boundaries matter, and how runtime and development
flows work. It is the highest-priority current-view contract for system boundaries,
persistence rules, runtime flows, recovery behavior, and core invariants.

Use architecture documents to answer:

- Which modules exist and how do they communicate?
- Where does data flow at runtime?
- Which files own which responsibilities?
- What must be updated when a contract changes?

Write architecture as current-view maps. Documents may describe the current
implementation, but should emphasize stable relationships and invariants instead of
line-by-line details.

## Reading Contract

Read every file in `../architecture/` in full during the first `dev_doc/` context
pass. Current architecture overrides historical change records and obsolete plans.

## File Roles

```text
00_architecture_index.md      overview and reading order
c4_context.md                 system boundary and external actors
c4_container.md               major modules and data flow
c4_component.md               important internal components
4plus1_logical_view.md        concepts, responsibilities, invariants
4plus1_process_view.md        runtime sequences and failure flows
4plus1_development_view.md    source layout, dependency rules, doc rules
4plus1_physical_view.md       filesystem and deployment layout
4plus1_scenarios.md           concrete use cases
```

Recommended section shape:

```text
# View Name
## Scope
## Diagram Or Structure
## Responsibilities
## Rules / Invariants
## Notes
```

## Maintenance Contract

Update the relevant architecture files after a code or documentation change alters
module responsibilities, public APIs, system boundaries, data persistence,
execution topology, recovery behavior, core invariants, or the development and
documentation workflow. Documentation-only changes require an architecture update
when the documentation system itself changes.
