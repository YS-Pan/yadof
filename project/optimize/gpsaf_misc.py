from __future__ import annotations

from dataclasses import dataclass
import importlib
import math
import random
from typing import Callable, Iterable, Sequence

from project import config_all as config


Population = tuple[tuple[float, ...], ...]
Costs = tuple[tuple[float, ...], ...]
Intervals = tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class HistoryRecord:
    job_name: str
    x: tuple[float, ...]
    costs: tuple[float, ...]


@dataclass(frozen=True)
class CandidateRecord:
    x: tuple[float, ...]
    origin: str
    individual: object | None = None
    pred_costs: tuple[float, ...] = ()
    intervals: Intervals = ()


def call_first(module, names: Iterable[str], *args, **kwargs):
    for name in names:
        func = getattr(module, name, None)
        if callable(func):
            return func(*args, **kwargs)
    raise AttributeError(f"{module.__name__} does not expose any of: {', '.join(names)}")


def clip01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def as_costs(values) -> Costs:
    return tuple(tuple(float(value) for value in row) for row in values)


def clean_costs(costs: Sequence[float]) -> tuple[float, ...]:
    out = []
    for value in costs:
        number = float(value)
        out.append(number if math.isfinite(number) else float("inf"))
    return tuple(out)


def total_cost(costs: Sequence[float]) -> float:
    values = clean_costs(costs)
    return float(sum(values)) if values else float("inf")


def dominates(left: Sequence[float], right: Sequence[float]) -> bool:
    left_values = clean_costs(left)
    right_values = clean_costs(right)
    width = min(len(left_values), len(right_values))
    if width == 0:
        return False
    return all(left_values[idx] <= right_values[idx] + 1e-12 for idx in range(width)) and any(
        left_values[idx] < right_values[idx] - 1e-12 for idx in range(width)
    )


def better_costs(left: Sequence[float], right: Sequence[float], rng: random.Random) -> bool:
    if dominates(left, right):
        return True
    if dominates(right, left):
        return False
    left_total = total_cost(left)
    right_total = total_cost(right)
    if not math.isclose(left_total, right_total, rel_tol=1e-12, abs_tol=1e-12):
        return left_total < right_total
    return rng.random() < 0.5


def history_records() -> tuple[HistoryRecord, ...]:
    try:
        recorded_api = importlib.import_module("project.recorded_data.api")
    except ModuleNotFoundError:
        return ()

    try:
        raw_records = call_first(
            recorded_api,
            (
                "get_optimization_history",
                "get_historical_optimization_results",
                "get_history_for_optimize",
                "get_historical_results",
            ),
        )
    except AttributeError:
        return ()

    records = []
    for item in raw_records or ():
        if isinstance(item, dict):
            name = str(item.get("job_name", item.get("name", "")))
            variables = item.get("normalized_variables", item.get("variables", ()))
            costs = item.get("costs", ())
        else:
            name, variables, costs = item
        records.append(
            HistoryRecord(
                job_name=str(name),
                x=tuple(clip01(value) for value in variables),
                costs=tuple(float(value) for value in costs),
            )
        )
    return tuple(records)


def job_template_variable_count() -> int | None:
    try:
        job_template_api = importlib.import_module("project.job_template.api")
        get_variable_count = getattr(job_template_api, "get_variable_count", None)
        if callable(get_variable_count):
            return int(get_variable_count())
        names = tuple(job_template_api.get_parameter_names())
    except Exception:
        return None
    return len(names) if names else None


def history_variable_count(history: Sequence[HistoryRecord]) -> int | None:
    for record in history:
        if record.x:
            return len(record.x)
    return None


def resolve_variable_count(
    variable_count: int | None = None,
    history: Sequence[HistoryRecord] = (),
) -> int:
    if variable_count is not None:
        return int(variable_count)
    count = history_variable_count(history) or job_template_variable_count()
    if count is not None:
        return int(count)
    raise RuntimeError("job_template.api must provide optimization variable count")


def evaluate(
    population: Population,
    *,
    run_id: str | None = None,
    optimization_index: int | None = None,
    generation_index: int | None = None,
    after_jobs_submitted: Callable[[], object] | None = None,
) -> Costs:
    evaluate_api = importlib.import_module("project.evaluate_manager.api")
    callback_ran = False

    def wrapped_after_jobs_submitted():
        nonlocal callback_ran
        callback_ran = True
        if after_jobs_submitted is not None:
            return after_jobs_submitted()
        return None

    try:
        raw_costs = call_first(
            evaluate_api,
            ("evaluate_generation", "evaluate_population", "evaluate"),
            population,
            mode=config.EVALUATION_MODE,
            run_id=run_id,
            optimization_index=optimization_index,
            generation_index=generation_index,
            after_jobs_submitted=wrapped_after_jobs_submitted if after_jobs_submitted is not None else None,
        )
    except TypeError:
        raw_costs = call_first(
            evaluate_api,
            ("evaluate_generation", "evaluate_population", "evaluate"),
            population,
        )
    if after_jobs_submitted is not None and not callback_ran:
        after_jobs_submitted()
    return as_costs(raw_costs)


def key(x: Sequence[float]) -> tuple[float, ...]:
    decimals = int(getattr(config, "OPTIMIZE_ARCHIVE_KEY_DECIMALS", 10))
    return tuple(round(float(value), decimals) for value in x)


def history_keys(history: tuple[HistoryRecord, ...]) -> set[tuple[float, ...]]:
    return {key(record.x) for record in history if record.x}
