from __future__ import annotations

import importlib
import json
import math
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from optConfig import ERROR_COST

_TMP_DIR_NAME = "_tmp"
_DOLLAR_VAR_RE = re.compile(r"\$([A-Za-z_]\w*)")

SOFTMAX_EDGE_COST = 0.1     # the softmax output will be 1-SOFTMAX_EDGE_COST at the worst value and SOFTMAX_EDGE_COST at the goal value
SOFTMAX_TANH_SLOPE = None   # if None, it will be set to the value that makes the softmax output 0.5 at (goal + worst) / 2

CONSTRAINT_SOFTMAX_EDGE_COST = SOFTMAX_EDGE_COST
CONSTRAINT_SOFTMAX_TANH_SLOPE = SOFTMAX_TANH_SLOPE


def _now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def _read_json(path: str | Path, default):
    path = Path(path)
    return default if not path.is_file() or path.stat().st_size == 0 else json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: str | Path, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8", newline="\n")


def bootstrap_home_dirs(base: Path) -> None:
    tmp = base / _TMP_DIR_NAME
    for k, p in {
        "USERPROFILE": base / "_home",
        "HOME": base / "_home",
        "APPDATA": base / "_appdata",
        "LOCALAPPDATA": base / "_localappdata",
        "TEMP": tmp,
        "TMP": tmp,
        "TMPDIR": tmp,
    }.items():
        os.environ[k] = str(p)
        p.mkdir(parents=True, exist_ok=True)


def cleanup_tmp_dir(base: str | Path) -> None:
    shutil.rmtree(Path(base) / _TMP_DIR_NAME, ignore_errors=True)


def update_metadata_json(meta_json_path: str | Path, **fields) -> dict:
    data = _read_json(meta_json_path, {})
    data = data if isinstance(data, dict) else {}
    data.update(fields)
    _write_json(meta_json_path, data)
    return data


def begin_solver_metadata(
    meta_json_path: str | Path, *, workflow_pid: int, workflow_child_pid: int, non_graphical: bool
) -> dict:
    return update_metadata_json(
        meta_json_path,
        status="running",
        engine="solver",
        is_surrogate=False,
        surrogate_uncertainty=None,
        non_graphical=bool(non_graphical),
        workflow_pid=int(workflow_pid),
        workflow_child_pid=int(workflow_child_pid),
        desktop_pid=None,
        timed_out=False,
        job_start_time=_now_text(),
        job_end_time=None,
    )


def finish_solver_metadata(
    meta_json_path: str | Path, *, status: str, timed_out: bool = False, desktop_pid=None
) -> dict:
    return update_metadata_json(
        meta_json_path,
        status=str(status),
        engine="solver",
        is_surrogate=False,
        surrogate_uncertainty=None,
        timed_out=bool(timed_out),
        desktop_pid=desktop_pid,
        job_end_time=_now_text(),
    )


def _append_cost_to_cost_json(cost_json_path: str | Path, cost: float) -> None:
    data = _read_json(cost_json_path, [])
    data.append(float(cost))
    _write_json(cost_json_path, data)


def finalize_cost_json(cost_json_path: str | Path, cost_keys_in_order, *, default_cost: float = ERROR_COST) -> None:
    data = [float(x) for x in _read_json(cost_json_path, [])[: len(cost_keys_in_order)]]
    data += [float(default_cost)] * max(0, len(cost_keys_in_order) - len(data))
    _write_json(cost_json_path, data)


def softmax(
    result: Any,
    goal: float,
    worst: float,
    *,
    error_cost: float = ERROR_COST,
    edge_cost: float | None = None,
    tanh_slope: float | None = None,
) -> float:
    if result is False or result is None:
        return float(error_cost)

    r, goal, worst = float(result), float(goal), float(worst)
    edge = float(SOFTMAX_EDGE_COST if edge_cost is None else edge_cost)
    slope = (
        2.0 * math.atanh(1.0 - 2.0 * edge)
        if tanh_slope is None and SOFTMAX_TANH_SLOPE is None
        else float(SOFTMAX_TANH_SLOPE if tanh_slope is None else tanh_slope)
    )

    if (
        not (math.isfinite(r) and math.isfinite(goal) and math.isfinite(worst))
        or goal == worst
        or not (0.0 < edge < 0.5)
        or not (math.isfinite(slope) and slope > 0.0)
    ):
        return float(error_cost)

    u = (r - goal) / (worst - goal)
    return float((math.tanh(slope * (u - 0.5)) + 1.0) / 2.0)


def _normalize_constraint_expr(expr: str) -> str:
    expr = expr.replace("^", "**")
    return _DOLLAR_VAR_RE.sub(
        lambda m: f"__get_var__({m.group(1)!r})",
        expr,
    )


def evaluate_constraints(module_name="parameters_constraints", *, extra_env=None):
    pc = importlib.reload(importlib.import_module(module_name))

    # math function support
    env: dict[str, Any] = {name: getattr(math, name) for name in dir(math) if not name.startswith("_")}
    env.update({"abs": abs, "min": min, "max": max, "pow": pow, "round": round, **(extra_env or {})})

    # module-level numeric constants
    for name, value in vars(pc).items():
        if name.startswith("_") or callable(value):
            continue
        if isinstance(value, (int, float, bool)):
            env[name] = value

    # parameters
    for p in getattr(pc, "PARAMETERS", ()):
        name = str(getattr(p, "name"))
        value = float(getattr(p, "value"))
        if math.isnan(value) and hasattr(p, "denorm"):
            try:
                value = float(p.denorm(update=False))
            except Exception:
                pass

        env[name] = float(value)
        env[f"${name}"] = float(value)
        if name.startswith("$"):
            base = name[1:]
            if base:
                env[base] = float(value)

    def _get_var(name: str) -> float:
        if name in env:
            return float(env[name])
        key = f"${name}"
        if key in env:
            return float(env[key])
        raise NameError(f"Variable '{name}' not found in constraint evaluation environment")

    scope = dict(env)
    scope["__get_var__"] = _get_var

    return [
        float(eval(_normalize_constraint_expr(expr), {"__builtins__": {}}, scope))
        for expr in getattr(pc, "CONSTRAINTS")
        if isinstance(expr, str) and expr.strip()
    ]


def cost_constraints(module_name="parameters_constraints", *, cost_json_path="cost.json") -> float:
    vals = [v if v <= 0 else 0.0 for v in evaluate_constraints(module_name)]
    if not vals:
        return 0.0
    cost = float(
        sum(
            softmax(
                v,
                goal=0.0,
                worst=-1.0,
                edge_cost=CONSTRAINT_SOFTMAX_EDGE_COST,
                tanh_slope=CONSTRAINT_SOFTMAX_TANH_SLOPE,
            )
            for v in vals
        )
        / len(vals)
    )
    _append_cost_to_cost_json(cost_json_path, cost)
    return cost