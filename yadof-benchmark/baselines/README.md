# Packaged benchmark baselines

Each leaf below this directory owns `baseline.json` and a complete yadof
`workspace/`. Discovery is recursive and keyed by the manifest's semantic ID; no
central registry is required. Runtime state such as jobs, recorded data, caches,
and visualization outputs is excluded from clean run snapshots.

These resources are included in the `yadof-benchmark` wheel and are discoverable
with `yadof-benchmark baselines`. See `user_doc/baselines.md` for the user contract.
