# Module Blueprint: Application

`api.py` coordinates existing package services. It resolves the workspace config,
collects row-level issues, builds display rows, formats the summary, and optionally
renders a PNG. It does not parse CLI arguments or render progress. `__init__.py`
exports the stable callable surface, and the legacy flat module forwards to it.
