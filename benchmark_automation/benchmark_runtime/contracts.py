"""Contracts services for benchmark automation."""
from __future__ import annotations
import contextlib
import dataclasses
import datetime as dt
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import os
import platform
import queue
import re
import shutil
import statistics
import subprocess
import sys
import threading
import time
import tomllib
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from rich.console import Console
from rich.progress import Progress, ProgressColumn, Task, TextColumn
from rich.table import Column
from rich.text import Text
SCHEMA_VERSION = 1
RUNTIME_PATHS = ('jobs', 'recorded_data', '.yadof/fast_scratch', '.yadof/surrogate/checkpoints', '.yadof/optimization/active.json', '.yadof/campaign.lock', '.yadof/logs')
TERMINAL_CELL_STATES = {'completed', 'failed', 'skipped'}
CONFIG_BLOCK_START = '# >>> benchmark_automation managed overrides >>>'
CONFIG_BLOCK_END = '# <<< benchmark_automation managed overrides <<<'
POSTPROCESS_SCRIPT_NAME = 'postprocess.py'
VISUALIZATION_DIRECTORY_NAME = 'visualizations'
VIEW_COST_DIRECTORY_NAME = 'viewcost'
COST_PLOT_NAME = 'benchmark-cost.png'
TIMING_HISTORY_NAME = 'timing_history.json'
PROGRESS_EVENTS_NAME = 'progress.jsonl'
TIMING_HISTORY_RUN_LIMIT = 64
TIMING_HISTORY_OBSERVATION_LIMIT = 512
PROGRESS_EVENT_TAIL_BYTES = 1048576
BASELINE_NAME_PATTERN = re.compile('[a-z][a-z0-9]*(?:-[a-z0-9]+)*\\Z')
_YADOF_PROGRESS = re.compile('^\\[yadof\\] (?P<phase>smoke|generation (?P<generation>\\d+)) \\([^)]*\\) \\[[#.]+\\] (?P<finished>\\d+)/(?P<total>\\d+) successful=(?P<successful>\\d+) errors=(?P<errors>\\d+) remaining=(?P<remaining>\\d+)\\s*$')
YADOF_PROGRESS = _YADOF_PROGRESS
__all__ = ['SCHEMA_VERSION', 'RUNTIME_PATHS', 'TERMINAL_CELL_STATES', 'CONFIG_BLOCK_START', 'CONFIG_BLOCK_END', 'POSTPROCESS_SCRIPT_NAME', 'VISUALIZATION_DIRECTORY_NAME', 'VIEW_COST_DIRECTORY_NAME', 'COST_PLOT_NAME', 'TIMING_HISTORY_NAME', 'PROGRESS_EVENTS_NAME', 'TIMING_HISTORY_RUN_LIMIT', 'TIMING_HISTORY_OBSERVATION_LIMIT', 'PROGRESS_EVENT_TAIL_BYTES', 'BASELINE_NAME_PATTERN', 'BenchmarkError', 'Paths']

class BenchmarkError(RuntimeError):
    """User-facing benchmark contract violation."""

@dataclasses.dataclass(frozen=True)
class Paths:
    root: Path
    config: Path
    runs: Path
    strategies: Path
    histories: Path
