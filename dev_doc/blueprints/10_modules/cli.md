# Module blueprint: cli

`yadof.cli` is the installed, repository-independent command package. Its public
`main` and `build_parser` entry points route version, documentation, workspace,
evaluation, optimization, history, viewing, and task utilities. Command modules may
load heavier runtime dependencies lazily, while the documentation command remains a
small read-only path into version-matched package resources.

Documentation uses an explicit `list`, `show`, and `bundle` action model. Paths are
audience-relative and traversal is rejected. CLI code contains no duplicate
documentation body and never requires callers to locate site-packages.
