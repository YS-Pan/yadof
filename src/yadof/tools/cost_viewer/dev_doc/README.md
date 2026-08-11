# Cost Viewer Developer Documentation

This tree is the maintenance entry point for `yadof.tools.cost_viewer`. The tool
is a reusable, read-only cost-history analysis package; it does not own a GUI.

Read in this order before changing the package:

1. [Architecture instructions](skill/architecture.md), then every document under
   `architecture/`.
2. [Terminology instructions](skill/terminology.md), then
   [terminology.md](terminology.md).
3. [Blueprint instructions](skill/blueprints.md), then the project blueprint and
   every module blueprint relevant to the change.

Root yadof contracts, user documentation, change records, active todos, packaging,
and tests remain authoritative in the repository-level `dev_doc/`. This local tree
does not duplicate those lifecycle documents.

The package intentionally contains no `ui/` or `app.py`. A future unified yadof
GUI should call the stable functions exported by `yadof.tools.cost_viewer`, or the
CLI service boundary where terminal-compatible behavior is required.
