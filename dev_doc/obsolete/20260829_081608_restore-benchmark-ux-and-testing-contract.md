# Superseded benchmark UX and recovery contract

Status: superseded on 2026-08-29 by the user's simpler single-workspace execution
decision.

The earlier plan proposed multi-run workspace indexes, immutable run-owned driver
and input snapshots, resume attempts, cross-run timing matching, and performance
scale floors. The completed replacement deliberately removes those requirements:

- one workspace owns one execution;
- another execution uses another workspace;
- execution uses installed packages and records versions/account once;
- no `runs/`, run ID, resume, attempt hierarchy, copied code snapshot, or
  cross-workspace timing history;
- cells use short `cNNNN` paths;
- default seed count is one;
- standard defaults remain 200×50, while slow-surrogate comparisons default to
  200×15;
- individual simulation errors may be tolerated by the explicit cell-validity
  contract;
- Windows AI-agent launch guidance requires host execution under the interactive
  human account.

The benchmark that motivated the earlier restoration plan was manually stopped by
the user. It is not a recovery target, and old workspace compatibility is outside
the current package contract.
