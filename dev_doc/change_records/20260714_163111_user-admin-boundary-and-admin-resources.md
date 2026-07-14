# 2026-07-14 16:31 - Define User And Administrator Boundaries

## Context

`project/tools/` mixed user-facing utilities with scripts that configure Windows
machines and HTCondor pool infrastructure. The top-level `reference/` name also no
longer described its mostly operational HTCondor content.

## Change

- Defined the `user` and `administrator` roles in English in `dev_doc/README.md`
  and `terminology.md`.
- Renamed `reference/` to `admin/` and added `admin/README.md` as its operational
  entry point.
- Moved `project/tools/htcondor_pool/` to `admin/htcondor_pool/`.
- Moved the generic project-bootstrap reference to
  `dev_doc/how_to_create_new_project.md`, where it now describes the `admin/`
  boundary instead of a generic reference folder.
- Updated current architecture views, blueprints, user guidance, HTCondor
  documentation, and generated-script banners to use the new paths and roles.

## Rationale

Users should be able to prepare, run, and inspect optimization campaigns without
being asked to install software or repair infrastructure. System and HTCondor
configuration is a separate administrator responsibility, so its tools and
documentation need an unambiguous location outside the user tool directory.

## Impact

`project/tools/` now contains user tools only. Administrator operations begin at
`admin/README.md`; the HTCondor pool scripts remain unchanged in behavior but have
a new path.

## Follow-Up

None.
