from __future__ import annotations

import os
import random
from typing import Sequence

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
    history_keys,
)
from .strategy import GenerationContext, HistoryRecord, Population


def _progress(message: str) -> None:
    if str(os.environ.get("YADOF_PROGRESS", "")).strip().lower() in {"1", "true", "yes", "on"}:
        print(f"[yadof] {message}", flush=True)


def ensure_surrogate_fresh_enough(
    surrogate,
    context: GenerationContext,
) -> dict[str, object]:
    try:
        func = getattr(surrogate, "ensure_fresh_enough", None)
        if not callable(func):
            return {"surrogate_training_gate": "unavailable"}
        status = func(context)
    except Exception as exc:  # noqa: BLE001 - a stale model should fall back, not stop the generation.
        return {
            "surrogate_training_gate": "failed",
            "surrogate_training_gate_error": f"{exc.__class__.__name__}: {exc}",
        }
    return {
        "surrogate_training_gate": str(getattr(status, "action", "unknown")),
        "surrogate_training_pending_generation": getattr(status, "pending_generation_index", None),
        "surrogate_training_latest_generation": getattr(status, "latest_completed_generation_index", None),
        "surrogate_training_gate_error": str(getattr(status, "error", "")),
    }


def surrogate_state_ready(surrogate, context: GenerationContext) -> bool:
    try:
        func = getattr(surrogate, "has_trained_state", None)
        return True if not callable(func) else bool(func(context))
    except Exception:
        return False


def notify_surrogate_after_submission(
    surrogate,
    context: GenerationContext,
) -> None:
    try:
        func = getattr(surrogate, "start_training", None)
        if callable(func):
            status = func(context)
            _progress(
                "surrogate: background training request generation "
                f"{context.generation_index}; "
                f"action={getattr(status, 'action', 'unknown')}"
            )
    except Exception as exc:  # noqa: BLE001 - submitted jobs should keep running if scheduling fails.
        _progress(f"surrogate: background training request failed: {exc.__class__.__name__}: {exc}")


def predict_records(
    surrogate,
    context: GenerationContext,
    records: Sequence[CandidateRecord],
) -> list[CandidateRecord]:
    if not records:
        return []
    _progress(f"surrogate: predicting {len(records)} candidates")
    raw = surrogate.predict_population(
        context,
        tuple(record.x for record in records),
    )
    predicted = []
    for record, item in zip(records, raw):
        costs, _member_spread = item
        predicted.append(
            CandidateRecord(
                x=record.x,
                origin=record.origin,
                individual=record.individual,
                pred_costs=tuple(float(value) for value in costs),
            )
        )
    return predicted


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
    *,
    surrogate,
    generation_context: GenerationContext,
) -> tuple[list[CandidateRecord], dict[str, object]]:
    predicted_pool: list[CandidateRecord] = []
    alpha = max(
        1, int(getattr(context.config, "OPTIMIZE_SURROGATE_ALPHA", 4))
    )
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
        predicted_pool.extend(predict_records(surrogate, generation_context, pool))
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
    *,
    surrogate,
    generation_context: GenerationContext,
) -> tuple[list[CandidateRecord], dict[str, object]]:
    beta = max(
        0, int(getattr(context.config, "OPTIMIZE_SURROGATE_BETA", 2))
    )
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
        records = predict_records(surrogate, generation_context, pool)
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


def _exploration_count(context: PymooContext, population_size: int) -> int:
    fraction = max(
        0.0,
        min(
            1.0,
            float(
                getattr(
                    context.config,
                    "OPTIMIZE_SURROGATE_EXPLORATION_FRACTION",
                    0.0,
                )
            ),
        ),
    )
    if fraction <= 0.0:
        return 0
    return min(int(population_size), max(1, int(round(int(population_size) * fraction))))


def surrogate_population(
    history: tuple[HistoryRecord, ...],
    *,
    context: PymooContext,
    generation_context: GenerationContext,
    surrogate,
    generation_index: int,
    population_size: int,
    seed: int,
) -> tuple[Population | None, dict[str, object]]:
    _progress(
        f"surrogate: selecting population; history={len(history)}; "
        f"population_size={int(population_size)}"
    )
    if not surrogate_state_ready(surrogate, generation_context):
        return None, {
            "surrogate_error": "no_trained_surrogate",
            "surrogate_mode": "waiting_for_first_staggered_training",
        }

    rng = random.Random(int(seed) + int(generation_index) * 1009 + 17)
    base_state = survivor_state_from_history(context, history, population_size)
    used_keys = history_keys(
        history,
        int(getattr(context.config, "OPTIMIZE_ARCHIVE_KEY_DECIMALS", 10)),
    )
    diagnostics: dict[str, object] = {"optimizer": "gpsaf"}
    exploration_count = _exploration_count(context, population_size)
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
            getattr(
                context.config,
                "OPTIMIZE_SURROGATE_EXPLORATION_FRACTION",
                0.0,
            )
        )
        if surrogate_target <= 0:
            return tuple(record.x for record in exploration_records[: int(population_size)]), diagnostics

        anchors, alpha_info = run_alpha_phase(
            context,
            base_state,
            surrogate_target,
            used_keys,
            rng,
            surrogate=surrogate,
            generation_context=generation_context,
        )
        diagnostics.update(alpha_info)
        if not anchors:
            return None, {**diagnostics, "surrogate_error": "no_alpha_candidates"}

        final_records, beta_info = run_beta_phase(
            context,
            base_state,
            anchors,
            surrogate_target,
            used_keys,
            rng,
            surrogate=surrogate,
            generation_context=generation_context,
        )
        diagnostics.update(beta_info)
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
