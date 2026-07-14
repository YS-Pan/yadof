# 2026-07-14 16:46 - Rename Administrator Resources And Remove Bootstrap Reference

## Context

The short `admin/` directory name could be confused with an account or an
application component. The generic project-bootstrap document was no longer needed
as part of the current development documentation set.

## Change

- Renamed `admin/` to `admin_tool/` and updated current documentation, HTCondor
  guidance, and script banners to use the new path.
- Removed `dev_doc/how_to_create_new_project.md` and its documentation references.

## Rationale

`admin_tool/` is explicit that the folder holds administrator-only operational
resources, without implying that it is an application module or user account. The
deleted bootstrap document did not describe a current operational contract.

## Impact

Administrator resources now begin at `admin_tool/README.md`. User tools remain in
`project/tools/`.

## Follow-Up

The historical, one-purpose HFSS multicore diagnosis script is assessed separately;
this change does not delete it.
