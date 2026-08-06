# 2026-08-06 16:23 - Document Agent Sandbox Workspace Permissions

## Context

- An AI agent's command process can use a sandbox identity or restricted security
  token different from the user's interactive terminal.
- A workspace may consequently be readable while an existing generated runtime
  directory is not writable to the evaluation process. Read-only validation does
  not exercise every runtime create, replace, and cleanup operation.

## Change

- Add general user guidance for recognizing agent-sandbox versus user-terminal
  permission differences on workspace runtime paths.
- Document narrowly scoped remedies: explicit user-approved out-of-sandbox
  execution, the user's own terminal, or permissions limited to the intended
  workspace runtime paths.

## Rationale

- Permission symptoms can otherwise be mistaken for task, simulator, or framework
  failures, especially when no first candidate, record, or scratch item appears.
- Broad ACL weakening is unnecessary and would violate the package/workspace
  safety boundary.

## Impact

- User-directed agents now have version-matched guidance for diagnosing runtime
  write access without relying on a particular workspace name or machine layout.
- No CLI, API, workspace schema, or execution behavior changes.

## Follow-Up

- None.
