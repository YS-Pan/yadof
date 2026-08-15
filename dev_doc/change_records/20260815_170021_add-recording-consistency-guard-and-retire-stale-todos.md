# 2026-08-15 17:00 - Add Recording Consistency Guard And Retire Stale ToDos

## Context

- The loss-tolerant evaluation-recording implementation changed persistence,
  backend finalization, campaign lifetime, task snapshots, history consumers, and
  their documentation in one large change. The user requested a recurring check
  for inconsistencies caused by that implementation.
- The user also determined that the pending native-HTCondor-retry restoration and
  Project Chrono integration-validation plans were outdated and should no longer
  remain active planning input.

## Change

- Added a persistent automatic toDo that briefly records the v2 recording change,
  links its completed change record and archived implementation toDo, and defines a
  bounded trigger check over naturally in-scope evidence.
- Required a matched occurrence to report the concrete inconsistency, impact, and
  evidence, then make the smallest complete authorized fix with appropriate tests
  and documentation. It does not authorize an unrelated repository scan, real
  simulator execution, destructive migration, or permission expansion.
- Moved `20260717_193325_restore-native-htcondor-resource-retries.md` and
  `20260804_144509_validate-project-chrono-integration.md` from `dev_doc/toDo/` to
  `dev_doc/obsolete/` without executing them. Their archive reason is that their
  contents are outdated, not that their old completion rules were satisfied.

## Rationale

- A persistent bounded guard lets future tasks correct evidenced cross-module drift
  without turning every task into a broad regression audit.
- Archiving outdated manual plans prevents obsolete assumptions from influencing
  future technical choices while preserving their historical text.

## Impact

- Future work that naturally touches the recording-v2 surface now checks relevant
  local evidence for regressions and repairs a confirmed match within normal task
  authority.
- The two archived plans are historical references only and no longer constitute
  active manual work.
- No runtime code or public behavior changed; software tests are not applicable to
  this documentation/toDo-state update.

## Follow-Up

- Keep the new automatic toDo active after each occurrence unless the user
  explicitly retires it or its completion contract is changed.
