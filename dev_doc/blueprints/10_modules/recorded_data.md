# Module blueprint: recorded_data

`yadof.recorded_data` stores workspace-local append-only individual metadata,
optimization/surrogate metadata, and zip-archived rawData under locks and atomic
publication. It stores raw variables once and scrubs duplicate variable payloads.
Public queries derive normalized variables, costs, and training bundles from current
task semantics. Invalid/legacy/corrupt rawData is skipped with diagnostics. No API
implicitly accesses another workspace.
