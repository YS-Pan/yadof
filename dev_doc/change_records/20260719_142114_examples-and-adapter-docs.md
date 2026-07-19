# 2026-07-19 14:21 - Align examples and adapter documentation with the package layout

## Context

- The checked-in HFSS workspace still lived under `workspaces/`, which blurred the
  boundary between a repository reference and a user-owned runtime workspace.
- User adapter documentation retained the historical `com_lib` directory name even
  though authoritative adapter sources now live in package resources.
- Packagify can leave other small or difficult inconsistencies that should be
  handled consistently when encountered.

## Change

- Renamed `workspaces/` to `examples/`, kept the example fully Git-tracked, removed
  the obsolete workspace ignore rules, and added the example index and usage guide.
- Renamed `user_doc/com_lib/` to `user_doc/adapters/`, updated current links, and
  documented `src/yadof/_resources/adapters/` as the authoritative source location.
- Updated the root README, development architecture, and package/workspace and
  adapter blueprints to describe the new boundaries.
- Corrected stale package-migration wording in both HFSS adapter copies and updated
  the artifact test to reject `examples/` from the sdist.
- Added an automatic toDo that fixes and reports simple packagify inconsistencies
  while only reporting difficult ones.

## Rationale

- Examples should be discoverable, reviewable repository assets without becoming
  mutable production workspaces or distribution members.
- Current documentation should name the package resource that users actually list
  and copy through the CLI.
- Opportunistic cleanup needs an explicit safety boundary so it does not expand
  unrelated work or perform risky migrations automatically.

## Impact

- Source users now find complete workspace references under `examples/` and adapter
  documentation under `user_doc/adapters/`.
- Wheel and sdist contents and runtime workspace behavior are unchanged.

## Follow-Up

- Report future packagify inconsistencies according to the automatic toDo.
