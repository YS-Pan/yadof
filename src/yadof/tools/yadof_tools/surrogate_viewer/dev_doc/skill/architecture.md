# Architecture Contract

## Purpose And Authority

`../architecture/` describes the viewer's current boundaries, runtime flows,
component ownership, concurrency, failure behavior, and core invariants. It is the
highest-priority current-view documentation in this tree.

Architecture is a map, not a line-by-line source summary. Use it to answer:

- Which parts of the viewer exist and how do they communicate?
- Where do workspace data and model predictions flow?
- Which thread owns UI state?
- Which operations may persist data?
- What must change when the viewer is integrated into yadof?

## Reading Contract

Read every file in `../architecture/` in the order listed by
`../architecture/00_architecture_index.md` during the first context pass.

This compact tree intentionally omits separate logical and physical 4+1 files when
their useful content is already covered by the C4, development, and process views.

## File Roles

```text
00_architecture_index.md      overview, invariants, and reading order
c4_context.md                 users and external systems
c4_container.md               major runtime boundaries and data flow
c4_component.md               source component responsibilities
4plus1_process_view.md        asynchronous sequences and failure flows
4plus1_development_view.md    source layout, dependencies, and doc rules
4plus1_scenarios.md           concrete use cases and acceptance behavior
```

## Maintenance Contract

Update the relevant files when a change alters module responsibilities, data
ownership, public APIs, persistence, thread/cancellation behavior, failure
semantics, checkpoint compatibility, or core UI/runtime invariants.

Documentation-only changes require an architecture update only when this
documentation system or its reading contract changes.
