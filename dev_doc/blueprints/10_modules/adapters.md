# Module blueprint: packaged adapter resources

Reusable `*_com.py` references live in `src/yadof/_resources/adapters/`. The `task
adapters` CLI lists resources and `task copy-adapter` copies one selected file into
the workspace `job_template/` without overwriting user edits. Active jobs import
only task-local copies. Framework adapters contain no concrete project/design,
objective, secret, or credential assumptions. User-facing adapter references live
under `user_doc/adapters/`.
