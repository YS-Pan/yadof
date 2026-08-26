# Operator Documentation Contract

## Purpose

The benchmark root `README.md` is the operator contract for planning, preflight,
execution, progress, status/ETA inspection, resume, collection, reporting, output
retention, risk, and interpretation. `AGENTS.md` is the coding-agent route through
that contract and generated evidence. Developer documents must not force an
operator to infer behavior from source.

## Reading

Every benchmark-development context pass reads both root documents before source.
For a runtime question, begin with the documented command and bounded output; do
not inspect private files merely because they exist.

## Maintenance

Update the root README when a change affects commands, options, configuration,
preconditions, progress, ETA fields, output structure, recovery, or scientific
interpretation. Update `AGENTS.md` when the safest first command, disclosure layer,
or targeted diagnosis route changes. Keep developer implementation detail in
`dev_doc/` and user-facing action/semantics in the root documents.
