# Module blueprint: packaged adapter resources

Reusable `*_com.py` references live in `src/yadof/_resources/adapters/`. The `task
adapters` CLI lists resources and `task copy-adapter` copies one selected file into
the workspace `job_template/` without overwriting user edits. Active jobs import
only task-local copies. Framework adapters contain no concrete project/design,
objective, secret, or credential assumptions. Agent-facing adapter references live
under `agent_doc/adapters/`. The pure-Python `test_com` resource provides compact
generic and HFSS-shaped profiles plus a deterministic 30-input large-scale profile
with separate 0D, 1D, 2D, and 3D blocks. Profile output shape belongs to the adapter;
objective windows and cost policy remain workspace task concerns.
