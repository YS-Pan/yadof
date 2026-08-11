# C4 Context

The cost viewer sits between user-facing callers and yadof's public workspace,
recorded-data, task-objective, and configuration APIs. Callers include the CLI,
Python integrations, and a future unified yadof GUI. The tool reads one explicit
workspace and returns text and an optional PNG; it never changes optimization
evidence or executes a job.
