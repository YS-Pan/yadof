# File blueprint: benchmark_runtime/state.py

Own run/attempt state, append-only attempt preparation, input materialization, and
snapshot copying. Unfinished runs require a complete execution snapshot; completed
legacy runs remain readable without one.
