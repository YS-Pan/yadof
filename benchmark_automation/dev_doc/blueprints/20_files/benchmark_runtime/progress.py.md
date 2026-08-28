# File blueprint: benchmark_runtime/progress.py

Own the single yadof progress parser, foreground-owned Rich rendering, cumulative
cell/global state, and timestamped event conversion. Pipe threads never render.
