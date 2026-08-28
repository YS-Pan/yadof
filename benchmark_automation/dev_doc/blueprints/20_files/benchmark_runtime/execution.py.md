# File blueprint: benchmark_runtime/execution.py

Own subprocess logging, explicit cell lifecycle stages, resume/fail-fast, and
attempt sealing. It consumes state/planning services through public names and does
not compare current source or artifact hashes.
