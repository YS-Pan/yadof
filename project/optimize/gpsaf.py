from __future__ import annotations

from dataclasses import dataclass, field
import importlib
import math
import random
from typing import Iterable, Sequence

from project import config


Population = tuple[tuple[float, ...], ...]
Costs = tuple[tuple[float, ...], ...]
Intervals = tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class OptimizationResult:
    generation_index: int
    population: Population
    costs: Costs
    history_count: int
    source: str
    surrogate_used: bool = False
    diagnostics: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class HistoryRecord:
    job_name: str
    x: tuple[float, ...]
    costs: tuple[float, ...]


@dataclass(frozen=True)
class CandidateRecord:
    x: tuple[float, ...]
    origin: str
    pred_costs: tuple[float, ...] = ()
    intervals: Intervals = ()


def _call_first(module, names: Iterable[str], *args, **kwargs):
    for name in names:
        func = getattr(module, name, None)
        if callable(func):
            return func(*args, **kwargs)
    raise AttributeError(f"{module.__name__} does not expose any of: {', '.join(names)}")


def _as_costs(values) -> Costs:
    return tuple(tuple(float(value) for value in row) for row in values)


def _history_records() -> tuple[HistoryRecord, ...]:
    try:
        recorded_api = importlib.import_module("project.recorded_data.api")
    except ModuleNotFoundError:
        return ()

    try:
        raw_records = _call_first(
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
                x=tuple(_clip01(value) for value in variables),
                costs=tuple(float(value) for value in costs),
            )
        )
    return tuple(records)


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _clean_costs(costs: Sequence[float]) -> tuple[float, ...]:
    out = []
    for value in costs:
        number = float(value)
        out.append(number if math.isfinite(number) else float("inf"))
    return tuple(out)


def _total_cost(costs: Sequence[float]) -> float:
    values = _clean_costs(costs)
    return float(sum(values)) if values else float("inf")


def _dominates(left: Sequence[float], right: Sequence[float]) -> bool:
    left_values = _clean_costs(left)
    right_values = _clean_costs(right)
    width = min(len(left_values), len(right_values))
    if width == 0:
        return False
    return all(left_values[idx] <= right_values[idx] + 1e-12 for idx in range(width)) and any(
        left_values[idx] < right_values[idx] - 1e-12 for idx in range(width)
    )


def _better_costs(left: Sequence[float], right: Sequence[float], rng: random.Random) -> bool:
    if _dominates(left, right):
        return True
    if _dominates(right, left):
        return False
    left_total = _total_cost(left)
    right_total = _total_cost(right)
    if not math.isclose(left_total, right_total, rel_tol=1e-12, abs_tol=1e-12):
        return left_total < right_total
    return rng.random() < 0.5


def _rank_history(history: tuple[HistoryRecord, ...]) -> list[HistoryRecord]:
    return sorted(history, key=lambda item: (_total_cost(item.costs), item.job_name))


def _random_population(size: int, variable_count: int, seed: int) -> Population:
    rng = random.Random(int(seed))
    return tuple(
        tuple(rng.random() for _ in range(int(variable_count)))
        for _ in range(int(size))
    )


def _population_from_history(
    history: tuple[HistoryRecord, ...],
    size: int,
    seed: int,
) -> Population:
    ranked = _rank_history(history)
    base = [record.x for record in ranked if record.x]
    if not base:
        variable_count = int(config.OPTIMIZE_VARIABLE_COUNT)
        return _random_population(size, variable_count, seed)

    population = list(base[: int(size)])
    rng = random.Random(int(seed))
    while len(population) < int(size):
        parent = base[len(population) % len(base)]
        jittered = tuple(_clip01(value + rng.uniform(-0.05, 0.05)) for value in parent)
        population.append(jittered)
    return tuple(population)


def _history_population_state(
    history: tuple[HistoryRecord, ...],
    size: int,
    seed: int,
) -> list[CandidateRecord]:
    ranked = _rank_history(history)
    state = [
        CandidateRecord(x=record.x, origin="recorded_data", pred_costs=record.costs)
        for record in ranked[: int(size)]
        if record.x
    ]
    if not state and history:
        state = [
            CandidateRecord(x=record.x, origin="recorded_data", pred_costs=record.costs)
            for record in history[: int(size)]
            if record.x
        ]
    if not state:
        return []

    rng = random.Random(int(seed))
    while len(state) < int(size):
        parent = state[len(state) % len(state)].x
        x = tuple(_clip01(value + rng.uniform(-0.05, 0.05)) for value in parent)
        state.append(CandidateRecord(x=x, origin="history_jitter", pred_costs=state[0].pred_costs))
    return state


def _evaluate(population: Population) -> Costs:
    evaluate_api = importlib.import_module("project.evaluate_manager.api")
    try:
        raw_costs = _call_first(
            evaluate_api,
            ("evaluate_generation", "evaluate_population", "evaluate"),
            population,
            mode=config.EVALUATION_MODE,
        )
    except TypeError:
        raw_costs = _call_first(
            evaluate_api,
            ("evaluate_generation", "evaluate_population", "evaluate"),
            population,
        )
    return _as_costs(raw_costs)


def _key(x: Sequence[float]) -> tuple[float, ...]:
    decimals = int(getattr(config, "OPTIMIZE_ARCHIVE_KEY_DECIMALS", 10))
    return tuple(round(float(value), decimals) for value in x)


def _history_keys(history: tuple[HistoryRecord, ...]) -> set[tuple[float, ...]]:
    return {_key(record.x) for record in history if record.x}


def _select_parent(state: Sequence[CandidateRecord], rng: random.Random) -> CandidateRecord:
    if not state:
        raise ValueError("cannot select parent from an empty population")
    left = state[rng.randrange(len(state))]
    right = state[rng.randrange(len(state))]
    return left if _better_costs(left.pred_costs, right.pred_costs, rng) else right


def _mate(left: tuple[float, ...], right: tuple[float, ...], rng: random.Random) -> tuple[float, ...]:
    if len(left) != len(right):
        width = min(len(left), len(right))
        left = left[:width]
        right = right[:width]
    if rng.random() > float(getattr(config, "OPTIMIZE_CROSSOVER_PROBABILITY", 0.8)):
        return tuple(left)
    return tuple(
        _clip01(value if rng.random() < 0.5 else other)
        for value, other in zip(left, right)
    )


def _mutate(x: tuple[float, ...], rng: random.Random) -> tuple[float, ...]:
    if not x:
        return x
    sigma = float(getattr(config, "OPTIMIZE_MUTATION_SIGMA", 0.12))
    mutation_probability = float(getattr(config, "OPTIMIZE_MUTATION_PROBABILITY", 0.35))
    per_dim = min(1.0, max(mutation_probability, 1.0 / float(len(x))))
    values = []
    changed = False
    for value in x:
        if rng.random() < per_dim:
            values.append(_clip01(value + rng.gauss(0.0, sigma)))
            changed = True
        else:
            values.append(_clip01(value))
    if not changed:
        idx = rng.randrange(len(values))
        values[idx] = _clip01(values[idx] + rng.gauss(0.0, sigma))
    return tuple(values)


def _generate_candidate_pool(
    state: Sequence[CandidateRecord],
    need: int,
    used_keys: set[tuple[float, ...]],
    rng: random.Random,
    variable_count: int,
    origin: str,
) -> list[CandidateRecord]:
    if need <= 0:
        return []

    accepted: list[CandidateRecord] = []
    attempts = max(1, int(need) * int(getattr(config, "OPTIMIZE_REFILL_ATTEMPTS", 8)))
    for _ in range(attempts):
        if state:
            p1 = _select_parent(state, rng).x
            p2 = _select_parent(state, rng).x
            x = _mutate(_mate(p1, p2, rng), rng)
        else:
            x = tuple(rng.random() for _ in range(int(variable_count)))
        key = _key(x)
        if key in used_keys:
            continue
        used_keys.add(key)
        accepted.append(CandidateRecord(x=x, origin=origin))
        if len(accepted) >= int(need):
            return accepted

    while len(accepted) < int(need):
        x = tuple(rng.random() for _ in range(int(variable_count)))
        key = _key(x)
        if key in used_keys:
            continue
        used_keys.add(key)
        accepted.append(CandidateRecord(x=x, origin=f"{origin}_random_refill"))
    return accepted


def _try_train_surrogate(generation_index: int):
    if not bool(getattr(config, "OPTIMIZE_SURROGATE_ENABLED", True)):
        return None, "disabled"
    try:
        surrogate_api = importlib.import_module("project.surrogate.api")
        state = surrogate_api.train(generation_index=int(generation_index))
    except Exception as exc:  # Surrogate assistance must never bypass true evaluation.
        return None, f"{exc.__class__.__name__}: {exc}"
    return state, None


def _predict_records(records: Sequence[CandidateRecord]) -> list[CandidateRecord]:
    if not records:
        return []
    surrogate_api = importlib.import_module("project.surrogate.api")
    raw = surrogate_api.predict_population(tuple(record.x for record in records))
    predicted = []
    for record, item in zip(records, raw):
        costs, intervals = item
        predicted.append(
            CandidateRecord(
                x=record.x,
                origin=record.origin,
                pred_costs=tuple(float(value) for value in costs),
                intervals=tuple((float(lo), float(hi)) for lo, hi in intervals),
            )
        )
    return predicted


def _noise_scales(record: CandidateRecord, historical_error: tuple[tuple[float, ...], ...]) -> tuple[float, ...]:
    scales = []
    for idx, value in enumerate(record.pred_costs):
        interval_scale = 0.0
        if idx < len(record.intervals):
            lo, hi = record.intervals[idx]
            interval_scale = max(0.0, 0.5 * abs(float(hi) - float(lo)))
        historical_values = [
            float(row[idx])
            for row in historical_error
            if idx < len(row) and math.isfinite(float(row[idx]))
        ]
        rel_error = sum(historical_values) / len(historical_values) if historical_values else 0.0
        scales.append(max(interval_scale, abs(float(value)) * rel_error, rel_error))
    return tuple(scales)


def _noisy_costs(
    record: CandidateRecord,
    historical_error: tuple[tuple[float, ...], ...],
    rng: random.Random,
) -> tuple[float, ...]:
    scales = _noise_scales(record, historical_error)
    return tuple(float(value) + rng.gauss(0.0, scale) for value, scale in zip(record.pred_costs, scales))


def _pick_record(
    left: CandidateRecord,
    right: CandidateRecord,
    rng: random.Random,
    *,
    noisy: bool = False,
    historical_error: tuple[tuple[float, ...], ...] = (),
) -> CandidateRecord:
    left_costs = _noisy_costs(left, historical_error, rng) if noisy else left.pred_costs
    right_costs = _noisy_costs(right, historical_error, rng) if noisy else right.pred_costs
    return left if _better_costs(left_costs, right_costs, rng) else right


def _probabilistic_knockout(
    records: Sequence[CandidateRecord],
    rng: random.Random,
    historical_error: tuple[tuple[float, ...], ...],
) -> CandidateRecord:
    if not records:
        raise ValueError("probabilistic knockout needs at least one candidate")
    pool = list(records)
    rng.shuffle(pool)
    while len(pool) > 1:
        if len(pool) % 2 == 1:
            pool.append(pool[rng.randrange(len(pool))])
        pool = [
            _pick_record(pool[idx], pool[idx + 1], rng, noisy=True, historical_error=historical_error)
            for idx in range(0, len(pool), 2)
        ]
    return pool[0]


def _distance_sq(left: Sequence[float], right: Sequence[float]) -> float:
    width = min(len(left), len(right))
    return sum((float(left[idx]) - float(right[idx])) ** 2 for idx in range(width))


def _assign_clusters(
    anchors: Sequence[CandidateRecord],
    candidates: Sequence[CandidateRecord],
) -> list[list[CandidateRecord]]:
    clusters = [[] for _ in anchors]
    if not anchors:
        return clusters
    for record in candidates:
        idx = min(range(len(anchors)), key=lambda anchor_idx: _distance_sq(record.x, anchors[anchor_idx].x))
        clusters[idx].append(record)
    return clusters


def _select_surrogate_state(
    state: Sequence[CandidateRecord],
    additions: Sequence[CandidateRecord],
    size: int,
    rng: random.Random,
) -> list[CandidateRecord]:
    pool = [record for record in tuple(state) + tuple(additions) if record.pred_costs]
    selected: list[CandidateRecord] = []
    while pool and len(selected) < int(size):
        best = pool[0]
        for record in pool[1:]:
            best = _pick_record(best, record, rng, noisy=False)
        selected.append(best)
        pool.remove(best)
    return selected


def _run_alpha_phase(
    state: Sequence[CandidateRecord],
    batch_target: int,
    used_keys: set[tuple[float, ...]],
    rng: random.Random,
    variable_count: int,
) -> tuple[list[CandidateRecord], dict[str, object]]:
    batches: list[list[CandidateRecord]] = []
    alpha = max(1, int(getattr(config, "OPTIMIZE_SURROGATE_ALPHA", 4)))

    for batch_index in range(alpha):
        pool = _generate_candidate_pool(
            state,
            batch_target,
            used_keys,
            rng,
            variable_count,
            origin=f"gpsaf_alpha_{batch_index + 1}",
        )
        if not pool:
            break
        batches.append(_predict_records(pool))

    if not batches:
        return [], {"alpha_batches": 0, "alpha_replacements": 0, "alpha_candidate_count": 0}

    selected = list(batches[0])
    replacements = 0
    for batch in batches[1:]:
        width = min(len(selected), len(batch))
        selected = selected[:width]
        for idx in range(width):
            winner = _pick_record(selected[idx], batch[idx], rng)
            if winner is not selected[idx]:
                replacements += 1
            selected[idx] = winner

    return selected[: int(batch_target)], {
        "alpha_batches": int(len(batches)),
        "alpha_replacements": int(replacements),
        "alpha_candidate_count": int(sum(len(batch) for batch in batches)),
    }


def _run_beta_phase(
    state: Sequence[CandidateRecord],
    anchors: Sequence[CandidateRecord],
    batch_target: int,
    used_keys: set[tuple[float, ...]],
    rng: random.Random,
    variable_count: int,
    historical_error: tuple[tuple[float, ...], ...],
) -> tuple[list[CandidateRecord], dict[str, object]]:
    beta = max(0, int(getattr(config, "OPTIMIZE_SURROGATE_BETA", 2)))
    if beta <= 0 or not anchors:
        return list(anchors), {
            "beta_iterations": 0,
            "beta_candidate_count": 0,
            "beta_replacements": 0,
            "beta_cluster_size_max": 0,
        }

    sim_state = list(state)
    clusters = [[] for _ in anchors]
    candidate_count = 0
    iterations = 0

    for beta_idx in range(beta):
        pool = _generate_candidate_pool(
            sim_state,
            batch_target,
            used_keys,
            rng,
            variable_count,
            origin=f"gpsaf_beta_{beta_idx + 1}",
        )
        if not pool:
            break
        records = _predict_records(pool)
        iterations += 1
        candidate_count += len(records)

        local_clusters = _assign_clusters(anchors, records)
        for idx, bucket in enumerate(local_clusters):
            clusters[idx].extend(bucket)
        sim_state = _select_surrogate_state(sim_state, records, max(1, len(state)), rng)

    cluster_sizes = [len(bucket) for bucket in clusters]
    cluster_max = max(cluster_sizes) if cluster_sizes else 0
    gamma = float(getattr(config, "OPTIMIZE_SURROGATE_GAMMA", 0.5))
    final_records = []
    replacements = 0

    for anchor, bucket in zip(anchors, clusters):
        if not bucket or cluster_max <= 0:
            final_records.append(anchor)
            continue
        winner = _probabilistic_knockout(bucket, rng, historical_error)
        rho = (float(len(bucket)) / float(cluster_max)) ** gamma
        if rng.random() < rho:
            final_records.append(winner)
            replacements += 1
        else:
            final_records.append(anchor)

    return final_records[: int(batch_target)], {
        "beta_iterations": int(iterations),
        "beta_candidate_count": int(candidate_count),
        "beta_replacements": int(replacements),
        "beta_cluster_size_max": int(cluster_max),
    }


def _historical_surrogate_errors() -> tuple[tuple[float, ...], ...]:
    try:
        surrogate_api = importlib.import_module("project.surrogate.api")
        return tuple(tuple(float(value) for value in row) for row in surrogate_api.evaluate_historical_errors())
    except Exception:
        return ()


def _surrogate_population(
    history: tuple[HistoryRecord, ...],
    *,
    generation_index: int,
    population_size: int,
    variable_count: int,
    seed: int,
) -> tuple[Population | None, dict[str, object]]:
    _state, error = _try_train_surrogate(generation_index)
    if error is not None:
        return None, {"surrogate_error": error}

    rng = random.Random(int(seed) + int(generation_index) * 1009 + 17)
    base_state = _history_population_state(history, population_size, seed)
    used_keys = _history_keys(history)
    diagnostics: dict[str, object] = {}

    try:
        anchors, alpha_info = _run_alpha_phase(
            base_state,
            population_size,
            used_keys,
            rng,
            variable_count,
        )
        diagnostics.update(alpha_info)
        if not anchors:
            return None, {**diagnostics, "surrogate_error": "no_alpha_candidates"}

        historical_error = _historical_surrogate_errors()
        final_records, beta_info = _run_beta_phase(
            base_state,
            anchors,
            population_size,
            used_keys,
            rng,
            variable_count,
            historical_error,
        )
        diagnostics.update(beta_info)
        diagnostics["historical_error_rows"] = len(historical_error)
    except Exception as exc:
        return None, {**diagnostics, "surrogate_error": f"{exc.__class__.__name__}: {exc}"}

    return tuple(record.x for record in final_records), diagnostics


def _notify_surrogate_after_evaluation(generation_index: int) -> None:
    try:
        surrogate_api = importlib.import_module("project.surrogate.api")
        surrogate_api.train(generation_index=int(generation_index))
    except Exception:
        return


def run_one_generation(
    *,
    generation_index: int = 0,
    population_size: int | None = None,
    variable_count: int | None = None,
    random_seed: int | None = None,
) -> OptimizationResult:
    size = int(population_size or config.OPTIMIZE_POPULATION_SIZE)
    seed = int(config.OPTIMIZE_RANDOM_SEED if random_seed is None else random_seed)
    history = _history_records()
    diagnostics: dict[str, object] = {}
    surrogate_used = False

    if history:
        count = len(history[0].x) if history[0].x else int(variable_count or config.OPTIMIZE_VARIABLE_COUNT)
        population, surrogate_info = _surrogate_population(
            history,
            generation_index=int(generation_index),
            population_size=size,
            variable_count=count,
            seed=seed,
        )
        diagnostics.update(surrogate_info)
        if population is None:
            population = _population_from_history(history, size, seed)
            source = "recorded_data"
        else:
            surrogate_used = True
            source = "gpsaf_surrogate"
    else:
        count = int(variable_count or config.OPTIMIZE_VARIABLE_COUNT)
        population = _random_population(size, count, seed)
        source = "random"

    costs = _evaluate(population)
    _notify_surrogate_after_evaluation(int(generation_index))
    return OptimizationResult(
        generation_index=int(generation_index),
        population=population,
        costs=costs,
        history_count=len(history),
        source=source,
        surrogate_used=surrogate_used,
        diagnostics=diagnostics,
    )
