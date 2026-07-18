from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

import numpy as np


def json_ready(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def now_utc_text() -> str:
    return datetime.now(timezone.utc).isoformat()
