# toDo Contract

## Reading and authority

When `../toDo/` exists, read every Markdown file below it recursively during the
first context pass. An absent directory means no benchmark-local pending work.
Reading a toDo provides design context but never authorizes real benchmark
execution or unrelated implementation.

## Maintenance

Future work must be a standalone, time-named handoff containing verified current
behavior, desired outcome, scope, prerequisites, open decisions, and a completion
rule. Do not hide pending work in architecture or completed change records. Remove
or archive a toDo only after its whole completion rule is satisfied.
