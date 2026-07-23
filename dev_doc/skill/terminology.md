# Terminology Contract

## Purpose And Reading

`../terminology.md` defines project-specific words whose meanings are not obvious
from common software usage. Read it in full during the first `dev_doc/` context
pass.

Use it to answer:

- What exactly does this project mean by a name?
- Is a term durable data, derived data, runtime state, or a workflow concept?

Only terms that require project context belong in the glossary. Recommended shape:

```text
# Project-Specific Terminology

| Term | Meaning In This Project |
|---|---|
| `term` | Definition and boundary notes. |
```

## Maintenance Contract

Update `../terminology.md` when a change corrects a mistaken concept, introduces a
non-obvious name, or clarifies a term that could otherwise be misused. Do not add
ordinary software vocabulary that has no project-specific meaning.
