# Module blueprint: package/workspace foundation

Distribution metadata has one version source and console entry point. Init safely
publishes a versioned generic template and marker without overwrite/repair. Check is
read-only. `WorkspaceContext` resolves all task/runtime paths. Task loading compiles
fresh source in temporary namespaces without lasting `sys.path` or module-cache
pollution. Package resources (docs/templates/adapters/worker support) are read-only.
Repository examples are tracked reference workspaces, not package resources or
runtime write locations, and are excluded from wheel and sdist artifacts.

Workspace implementation lives under `yadof.workspace`: `context`, `manifest`,
`init`, and `check` separate the public path value from creation and diagnostics.
