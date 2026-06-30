from __future__ import annotations

import importlib
import math
import os
import random
from typing import Sequence

from project import config

from .gpsaf_pymoo import (
    PymooContext,
    advance_population_with_records,
    clone_algorithm,
    generate_candidate_pool,
    select_records_by_survival,
    survivor_state_from_history,
)
from .gpsaf_misc import (
    CandidateRecord,
    HistoryRecord,
    Population,
    better_costs,
    history_keys,
)


def _progress(message: str) -> None:
    if str(os.environ.get("YADOT_PROGRESS", "")).strip().lower() in {"1", "true", "yes", "on"}:
        print(f"[yadof] {message}", flush=True)


def try_train_surrogate(generation_index: int):
    _progress(f"surrogate: training generation {int(generation_index)} start")
    try:
        surrogate_api = importlib.import_module("project.surrogate.api")
        state = surrogate_api.train(generation_index=int(generation_index))
    except Exception as exc:
        _progress(f"surrogate: training generation {int(generation_index)} failed: {exc.__class__.__name__}: {exc}")
        return None, f"{exc.__class__.__name__}: {exc}"
    history = getattr(state, "train_history", {}) or {}
    sample_count = history.get("train_sample_count", "?")
    query_count = history.get("query_count", "?")
    member_count = history.get("member_count", "?")
    _progress(
        f"surrogate: training generation {int(generation_index)} finished; "
        f"samples={sample_count}; queries={query_count}; members={member_count}"
    )
    return state, None


def notify_surrogate_after_evaluation(generation_index: int) -> None:
    try:
        surrogate_api = importlib.import_module("project.surrogate.api")
        surrogate_api.train(generation_index=int(generation_index))
    except Exception:
        return


def predict_records(records: Sequence[CandidateRecord]) -> list[CandidateRecord]:
    if not records:
        return []
    _progress(f"surrogate: predicting {len(records)} candidates")
    surrogate_api = importlib.import_module("project.surrogate.api")
    raw = surrogate_api.predict_population(tuple(record.x for record in records))
    predicted = []
    for record, item in zip(records, raw):
        costs, intervals = item
        predicted.append(
            CandidateRecord(
                x=record.x,
                origin=record.origin,
                individual=record.individual,
                pred_costs=tuple(float(value) for value in costs),
                intervals=tuple((float(lo), float(hi)) for lo, hi in intervals),
            )
        )
    return predicted


def historical_surrogate_errors() -> tuple[tuple[float, ...], ...]:
    try:
        surrogate_api = importlib.import_module("project.surrogate.api")
        return tuple(tuple(float(value) for value in row) for row in surrogate_api.evaluate_historical_errors())
    except Exception:
        return ()


def noise_scales(record: CandidateRecord, historical_error: tuple[tuple[float, ...], ...]) -> tuple[float, ...]:
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


def noisy_costs(
    record: CandidateRecord,
    historical_error: tuple[tuple[float, ...], ...],
    rng: random.Random,
) -> tuple[float, ...]:
    scales = noise_scales(record, historical_error)
    return tuple(float(value) + rng.gauss(0.0, scale) for value, scale in zip(record.pred_costs, scales))


def pick_record(
    left: CandidateRecord,
    right: CandidateRecord,
    rng: random.Random,
    *,
    noisy: bool = False,
    historical_error: tuple[tuple[float, ...], ...] = (),
) -> CandidateRecord:
    left_costs = noisy_costs(left, historical_error, rng) if noisy else left.pred_costs
    right_costs = noisy_costs(right, historical_error, rng) if noisy else right.pred_costs
    return left if better_costs(left_costs, right_costs, rng) else right


def probabilistic_knockout(
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
            pick_record(pool[idx], pool[idx + 1], rng, noisy=True, historical_error=historical_error)
            for idx in range(0, len(pool), 2)
        ]
    return pool[0]


def distance_sq(left: Sequence[float], right: Sequence[float]) -> float:
    width = min(len(left), len(right))
    return sum((float(left[idx]) - float(right[idx])) ** 2 for idx in range(width))


def assign_clusters(
    anchors: Sequence[CandidateRecord],
    candidates: Sequence[CandidateRecord],
) -> list[list[CandidateRecord]]:
    clusters = [[] for _ in anchors]
    if not anchors:
        return clusters
    for record in candidates:
        idx = min(range(len(anchors)), key=lambda anchor_idx: distance_sq(record.x, anchors[anchor_idx].x))
        clusters[idx].append(record)
    return clusters


def run_alpha_phase(
    context: PymooContext,
    state,
    batch_target: int,
    used_keys: set[tuple[float, ...]],
    rng: random.Random,
) -> tuple[list[CandidateRecord], dict[str, object]]:
    predicted_pool: list[CandidateRecord] = []
    alpha = max(1, int(getattr(config, "OPTIMIZE_SURROGATE_ALPHA", 4)))
    batches_completed = 0

    for batch_index in range(alpha):
        pool = generate_candidate_pool(
            context,
            state,
            batch_target,
            used_keys,
            rng,
            origin=f"gpsaf_alpha_{batch_index + 1}",
        )
        if not pool:
            break
        predicted_pool.extend(predict_records(pool))
        batches_completed += 1

    if not predicted_pool:
        return [], {"alpha_batches": 0, "alpha_replacements": 0, "alpha_candidate_count": 0}

    selected = select_records_by_survival(context, predicted_pool, batch_target)
    return selected[: int(batch_target)], {
        "alpha_batches": int(batches_completed),
        "alpha_replacements": 0,
        "alpha_candidate_count": int(len(predicted_pool)),
        "alpha_selection": "nsga3_pooled_survival",
        "alpha_survival_selected": int(len(selected)),
    }


def run_beta_phase(
    context: PymooContext,
    state,
    anchors: Sequence[CandidateRecord],
    batch_target: int,
    used_keys: set[tuple[float, ...]],
    rng: random.Random,
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

    sim_state = clone_algorithm(state)
    clusters = [[] for _ in anchors]
    beta_records: list[CandidateRecord] = []
    candidate_count = 0
    iterations = 0

    for beta_idx in range(beta):
        pool = generate_candidate_pool(
            context,
            sim_state,
            batch_target,
            used_keys,
            rng,
            origin=f"gpsaf_beta_{beta_idx + 1}",
        )
        if not pool:
            break
        records = predict_records(pool)
        iterations += 1
        candidate_count += len(records)

        local_clusters = assign_clusters(anchors, records)
        for idx, bucket in enumerate(local_clusters):
            clusters[idx].extend(bucket)
        beta_records.extend(records)
        sim_state = advance_population_with_records(context, sim_state, records, batch_target)

    cluster_sizes = [len(bucket) for bucket in clusters]
    cluster_max = max(cluster_sizes) if cluster_sizes else 0
    pooled = list(anchors) + beta_records
    final_records = select_records_by_survival(context, pooled, batch_target)
    if len(final_records) < int(batch_target):
        existing = {id(record) for record in final_records}
        for record in anchors:
            if id(record) in existing:
                continue
            final_records.append(record)
            if len(final_records) >= int(batch_target):
                break
    anchor_ids = {id(record) for record in anchors}
    replacements = sum(1 for record in final_records if id(record) not in anchor_ids)

    return final_records[: int(batch_target)], {
        "beta_iterations": int(iterations),
        "beta_candidate_count": int(candidate_count),
        "beta_replacements": int(replacements),
        "beta_cluster_size_max": int(cluster_max),
        "beta_cluster_sizes": tuple(int(value) for value in cluster_sizes),
        "beta_selection": "nsga3_pooled_survival",
        "beta_pool_size": int(len(pooled)),
        "beta_survival_selected": int(len(final_records)),
    }


def _exploration_count(population_size: int) -> int:
    fraction = max(0.0, min(1.0, float(getattr(config, "OPTIMIZE_SURROGATE_EXPLORATION_FRACTION", 0.0))))
    if fraction <= 0.0:
        return 0
    return min(int(population_size), max(1, int(round(int(population_size) * fraction))))


def surrogate_population(
    history: tuple[HistoryRecord, ...],
    *,
    context: PymooContext,
    generation_index: int,
    population_size: int,
    seed: int,
) -> tuple[Population | None, dict[str, object]]:
    _progress(
        f"surrogate: selecting population; history={len(history)}; "
        f"population_size={int(population_size)}"
    )
    _state, error = try_train_surrogate(generation_index)
    if error is not None:
        return None, {"surrogate_error": error}

    rng = random.Random(int(seed) + int(generation_index) * 1009 + 17)
    base_state = survivor_state_from_history(context, history, population_size)
    used_keys = history_keys(history)
    diagnostics: dict[str, object] = {"optimizer": "gpsaf"}
    exploration_count = _exploration_count(population_size)
    surrogate_target = max(0, int(population_size) - int(exploration_count))

    try:
        exploration_records = (
            generate_candidate_pool(
                context,
                clone_algorithm(base_state),
                exploration_count,
                used_keys,
                rng,
                origin="gpsaf_exploration",
            )
            if exploration_count > 0
            else []
        )
        diagnostics["exploration_count"] = int(len(exploration_records))
        diagnostics["exploration_fraction"] = float(
            getattr(config, "OPTIMIZE_SURROGATE_EXPLORATION_FRACTION", 0.0)
        )
        if surrogate_target <= 0:
            return tuple(record.x for record in exploration_records[: int(population_size)]), diagnostics

        anchors, alpha_info = run_alpha_phase(context, base_state, surrogate_target, used_keys, rng)
        diagnostics.update(alpha_info)
        if not anchors:
            return None, {**diagnostics, "surrogate_error": "no_alpha_candidates"}

        historical_error = historical_surrogate_errors()
        final_records, beta_info = run_beta_phase(
            context,
            base_state,
            anchors,
            surrogate_target,
            used_keys,
            rng,
            historical_error,
        )
        diagnostics.update(beta_info)
        diagnostics["historical_error_rows"] = len(historical_error)
        final_records = list(final_records) + list(exploration_records)
        if len(final_records) < int(population_size):
            final_records.extend(
                generate_candidate_pool(
                    context,
                    clone_algorithm(base_state),
                    int(population_size) - len(final_records),
                    used_keys,
                    rng,
                    origin="gpsaf_exploration_refill",
                )
            )
    except Exception as exc:
        return None, {**diagnostics, "surrogate_error": f"{exc.__class__.__name__}: {exc}"}

    return tuple(record.x for record in final_records[: int(population_size)]), diagnostics
