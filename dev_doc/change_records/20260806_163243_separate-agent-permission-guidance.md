# 2026-08-06 16:32 - Separate Agent Permission Guidance

## Context

- Sandbox identity, filesystem ACL, Git repository ownership, and Git index write
  permission are host-agent environment concerns rather than yadof behavior.
- The initial sandbox permission note lived inside the yadof package-foundation
  page, which made that independent boundary less clear.

## Change

- Move generic sandbox/filesystem guidance into the standalone
  `user_doc/agent_environment_permissions.md` reference.
- Add Git index-lock and dubious-ownership diagnosis, per-command exact
  `safe.directory` examples, and safety limits for persistent configuration or
  lock cleanup.
- Link the optional reference from the user README and record the independent file
  role in current development architecture and the documentation blueprint.

## Rationale

- A separate file makes the material discoverable to a user-directed agent without
  presenting unrelated host security behavior as part of yadof's runtime contract.
- Exact, temporary Git trust exceptions preserve Git's ownership safety boundary
  better than broad or global workarounds.

## Impact

- Installed user documentation now covers the permission failures encountered by
  agent-run commands in a project-generic form.
- No yadof CLI, API, workspace, evaluation, or Git behavior changes.

## Follow-Up

- None.
