from __future__ import annotations

import os
from typing import Sequence

from ...surrogate.training import DeterministicPredictionProvider
from ..primitives import (
    CandidatePool,
    CandidateSelection,
    PredictedCostRows,
    SearchCandidate,
    SearchState,
    advance_search,
    bind_predicted_costs,
    bind_surrogate_prediction,
    combine_candidate_pools,
    compose_real_population,
    continue_search_from,
    fork_search_state,
    prepare_search,
    search_candidates,
    select_candidates,
)
from ..strategy import GenerationContext, HistoryRecord, Population


def _progress(message: str) -> None:
    if str(os.environ.get("YADOF_PROGRESS", "")).strip().lower() in {"1", "true", "yes", "on"}:
        print(f"[yadof] {message}", flush=True)


def ensure_surrogate_fresh_enough(
    surrogate,
    context: GenerationContext,
    training_data=None,
) -> dict[str, object]:
    try:
        func = getattr(surrogate, "ensure_fresh_enough", None)
        if not callable(func):
            return {"surrogate_training_gate": "unavailable"}
        status = (
            func(context, training_data)
            if training_data is not None
            else func(context)
        )
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


def surrogate_state_ready(
    surrogate,
    context: GenerationContext,
    training_data=None,
) -> bool:
    try:
        func = getattr(surrogate, "has_trained_state", None)
        if not callable(func):
            return True
        return bool(
            func(context, training_data)
            if training_data is not None
            else func(context)
        )
    except Exception:
        return False


def notify_surrogate_after_submission(
    surrogate,
    context: GenerationContext,
) -> None:
    try:
        func = getattr(surrogate, "start_training", None)
        if callable(func):
            training_data = materialize_surrogate_training_data(surrogate, context)
            status = (
                func(context, training_data)
                if training_data is not None
                else func(context)
            )
            _progress(
                "surrogate: background training request generation "
                f"{context.generation_index}; "
                f"action={getattr(status, 'action', 'unknown')}"
            )
    except Exception as exc:  # noqa: BLE001 - submitted jobs should keep running if scheduling fails.
        _progress(f"surrogate: background training request failed: {exc.__class__.__name__}: {exc}")


def finish_surrogate_training(
    surrogate,
    context: GenerationContext,
) -> dict[str, object]:
    try:
        func = getattr(surrogate, "finish_training", None)
        if not callable(func):
            return {}
        status = func(context)
    except Exception as exc:  # noqa: BLE001 - typed fallback remains generation-local.
        return {
            "surrogate_training_finish": "failed",
            "surrogate_training_finish_error": f"{exc.__class__.__name__}: {exc}",
        }
    return {
        "surrogate_training_finish": str(getattr(status, "action", "unknown")),
        "surrogate_training_finish_error": str(getattr(status, "error", "")),
    }


def materialize_surrogate_training_data(surrogate, context: GenerationContext):
    factory = getattr(surrogate, "training_data", None)
    if not callable(factory):
        return None
    dataset = context.session.evidence_dataset()
    table = context.session.cost_table(context.snapshot)
    return factory(dataset, table)


def predict_pool(
    surrogate,
    context: GenerationContext,
    pool: CandidatePool,
    training_data=None,
) -> PredictedCostRows:
    """Adapt one typed or retained legacy predictor at the explicit pool edge."""

    if not pool.candidates:
        raise ValueError("surrogate prediction requires a non-empty candidate pool")
    _progress(f"surrogate: predicting {len(pool.candidates)} candidates")
    if isinstance(surrogate, DeterministicPredictionProvider):
        prediction = surrogate.predict_for_selection(
            context,
            pool.population,
            training_data,
        )
        return bind_surrogate_prediction(pool, prediction)

    raw = (
        surrogate.predict_population(context, pool.population, training_data)
        if training_data is not None
        else surrogate.predict_population(context, pool.population)
    )
    rows = tuple(raw)
    if len(rows) != len(pool.candidates):
        raise ValueError("legacy surrogate prediction rows do not match the pool")
    costs = tuple(tuple(float(value) for value in item[0]) for item in rows)
    return bind_predicted_costs(
        pool,
        costs,
        source="legacy-gpsaf-prediction-adapter",
        interpretation_fingerprint=context.snapshot.interpretation_fingerprint,
        state_signature=context.strategy_signature,
        diagnostics={"prediction_adapter": "legacy-predict-population-v1"},
    )


def distance_sq(left: Sequence[float], right: Sequence[float]) -> float:
    width = min(len(left), len(right))
    return sum((float(left[idx]) - float(right[idx])) ** 2 for idx in range(width))


def assign_clusters(
    anchors: Sequence[SearchCandidate],
    candidates: Sequence[SearchCandidate],
) -> list[list[SearchCandidate]]:
    clusters = [[] for _ in anchors]
    if not anchors:
        return clusters
    for record in candidates:
        idx = min(
            range(len(anchors)),
            key=lambda anchor_idx: distance_sq(
                record.normalized_variables,
                anchors[anchor_idx].normalized_variables,
            ),
        )
        clusters[idx].append(record)
    return clusters


def _bind_combined_prediction(
    pool: CandidatePool,
    predictions: Sequence[PredictedCostRows],
    *,
    source: str,
) -> PredictedCostRows:
    by_id: dict[str, tuple[float, ...]] = {}
    interpretation_fingerprint = ""
    state_signature = ""
    for prediction in predictions:
        if not isinstance(prediction, PredictedCostRows):
            raise TypeError("combined prediction inputs must be PredictedCostRows")
        if not interpretation_fingerprint:
            interpretation_fingerprint = prediction.interpretation_fingerprint
            state_signature = prediction.state_signature
        elif (
            prediction.interpretation_fingerprint != interpretation_fingerprint
            or prediction.state_signature != state_signature
        ):
            raise ValueError("combined predictions use different fitted semantics")
        for candidate_id, costs in zip(
            prediction.candidate_ids,
            prediction.costs,
        ):
            if candidate_id in by_id:
                raise ValueError("combined predictions repeat a candidate ID")
            by_id[candidate_id] = costs
    expected = tuple(candidate.candidate_id for candidate in pool.candidates)
    if any(candidate_id not in by_id for candidate_id in expected):
        raise ValueError("combined prediction is missing candidate rows")
    return bind_predicted_costs(
        pool,
        tuple(by_id[candidate_id] for candidate_id in expected),
        source=source,
        interpretation_fingerprint=interpretation_fingerprint,
        state_signature=state_signature,
        diagnostics={
            "combined_prediction_count": len(tuple(predictions)),
            "combined_candidate_count": len(expected),
        },
    )


def run_alpha_phase(
    state: SearchState,
    batch_target: int,
    *,
    surrogate,
    generation_context: GenerationContext,
    settings,
    training_data=None,
) -> tuple[
    CandidateSelection | None,
    PredictedCostRows | None,
    dict[str, object],
]:
    pools: list[CandidatePool] = []
    predictions: list[PredictedCostRows] = []
    current = state
    alpha = max(1, settings.alpha)

    for batch_index in range(alpha):
        pool = search_candidates(
            current,
            batch_target,
            origin=f"gpsaf_alpha_{batch_index + 1}",
        )
        current = pool.state
        pools.append(pool)
        predictions.append(
            predict_pool(
                surrogate,
                generation_context,
                pool,
                training_data=training_data,
            )
        )

    if not pools:
        return None, None, {
            "alpha_batches": 0,
            "alpha_replacements": 0,
            "alpha_candidate_count": 0,
        }

    combined_pool = combine_candidate_pools(current, pools)
    combined_prediction = _bind_combined_prediction(
        combined_pool,
        predictions,
        source="gpsaf-alpha-predicted-costs",
    )
    selected = select_candidates(
        current,
        combined_pool,
        combined_prediction,
        batch_target,
        source="gpsaf-alpha-selection",
    )
    return selected, combined_prediction, {
        "alpha_batches": len(pools),
        "alpha_replacements": 0,
        "alpha_candidate_count": len(combined_pool.candidates),
        "alpha_selection": "nsga3_pooled_survival",
        "alpha_survival_selected": len(selected.candidates),
    }


def run_beta_phase(
    anchors: CandidateSelection,
    anchor_prediction: PredictedCostRows,
    batch_target: int,
    *,
    surrogate,
    generation_context: GenerationContext,
    settings,
    training_data=None,
) -> tuple[CandidateSelection, dict[str, object]]:
    beta = max(0, settings.beta)
    if beta <= 0 or not anchors.candidates:
        return anchors, {
            "beta_iterations": 0,
            "beta_candidate_count": 0,
            "beta_replacements": 0,
            "beta_cluster_size_max": 0,
        }

    sim_state = fork_search_state(anchors.state)
    clusters = [[] for _ in anchors.candidates]
    beta_pools: list[CandidatePool] = []
    beta_predictions: list[PredictedCostRows] = []

    for beta_idx in range(beta):
        pool = search_candidates(
            sim_state,
            batch_target,
            origin=f"gpsaf_beta_{beta_idx + 1}",
        )
        prediction = predict_pool(
            surrogate,
            generation_context,
            pool,
            training_data=training_data,
        )
        local_clusters = assign_clusters(anchors.candidates, pool.candidates)
        for idx, bucket in enumerate(local_clusters):
            clusters[idx].extend(bucket)
        beta_pools.append(pool)
        beta_predictions.append(prediction)
        sim_state = advance_search(pool.state, pool, prediction)

    combined_pool = combine_candidate_pools(
        sim_state,
        (anchors, *beta_pools),
    )
    combined_prediction = _bind_combined_prediction(
        combined_pool,
        (anchor_prediction, *beta_predictions),
        source="gpsaf-beta-predicted-costs",
    )
    final_selection = select_candidates(
        sim_state,
        combined_pool,
        combined_prediction,
        batch_target,
        source="gpsaf-beta-selection",
    )
    anchor_ids = {candidate.candidate_id for candidate in anchors.candidates}
    replacements = sum(
        candidate.candidate_id not in anchor_ids
        for candidate in final_selection.candidates
    )
    cluster_sizes = tuple(len(bucket) for bucket in clusters)

    return final_selection, {
        "beta_iterations": len(beta_pools),
        "beta_candidate_count": sum(len(pool.candidates) for pool in beta_pools),
        "beta_replacements": int(replacements),
        "beta_cluster_size_max": max(cluster_sizes, default=0),
        "beta_cluster_sizes": cluster_sizes,
        "beta_selection": "nsga3_pooled_survival",
        "beta_pool_size": len(combined_pool.candidates),
        "beta_survival_selected": len(final_selection.candidates),
    }


def _exploration_count(settings, population_size: int) -> int:
    fraction = settings.exploration_fraction
    if fraction <= 0.0:
        return 0
    return min(int(population_size), max(1, int(round(int(population_size) * fraction))))


def surrogate_population(
    history: tuple[HistoryRecord, ...],
    *,
    generation_context: GenerationContext,
    search,
    surrogate,
    generation_index: int,
    population_size: int,
    seed: int,
    settings,
    training_data=None,
) -> tuple[Population | None, dict[str, object]]:
    _progress(
        f"surrogate: selecting population; history={len(history)}; "
        f"population_size={int(population_size)}"
    )
    if not surrogate_state_ready(
        surrogate,
        generation_context,
        training_data,
    ):
        return None, {
            "surrogate_error": "no_trained_surrogate",
            "surrogate_mode": "waiting_for_first_staggered_training",
        }

    diagnostics: dict[str, object] = {"optimizer": "gpsaf"}
    try:
        base_state = prepare_search(
            generation_context,
            search,
            population_size=population_size,
            algorithm_seed=seed,
            random_seed=seed + generation_index * 1009 + 17,
            history_policy="survivor",
        )
        diagnostics.update(dict(base_state.diagnostics))
        exploration_count = _exploration_count(settings, population_size)
        surrogate_target = max(0, int(population_size) - exploration_count)
        exploration_pool = None
        main_state = base_state
        if exploration_count > 0:
            exploration_pool = search_candidates(
                fork_search_state(base_state),
                exploration_count,
                origin="gpsaf_exploration",
            )
            main_state = continue_search_from(base_state, exploration_pool.state)
        diagnostics["exploration_count"] = (
            0 if exploration_pool is None else len(exploration_pool.candidates)
        )
        diagnostics["exploration_fraction"] = settings.exploration_fraction

        if surrogate_target <= 0:
            if exploration_pool is None:
                return None, {
                    **diagnostics,
                    "surrogate_error": "empty_surrogate_and_exploration_targets",
                }
            selected = compose_real_population(
                exploration_pool.state,
                (exploration_pool,),
                size=population_size,
                source="gpsaf-surrogate-selection",
                refill_origin="gpsaf_exploration_refill",
            )
            diagnostics.update(dict(selected.state.diagnostics))
            diagnostics["search_selection_source"] = selected.source
            return selected.population, diagnostics

        anchors, alpha_prediction, alpha_info = run_alpha_phase(
            main_state,
            surrogate_target,
            surrogate=surrogate,
            generation_context=generation_context,
            settings=settings,
            training_data=training_data,
        )
        diagnostics.update(alpha_info)
        if anchors is None or alpha_prediction is None:
            return None, {**diagnostics, "surrogate_error": "no_alpha_candidates"}

        final_selection, beta_info = run_beta_phase(
            anchors,
            alpha_prediction,
            surrogate_target,
            surrogate=surrogate,
            generation_context=generation_context,
            settings=settings,
            training_data=training_data,
        )
        diagnostics.update(beta_info)
        groups: tuple[CandidatePool | CandidateSelection, ...] = (
            (final_selection,)
            if exploration_pool is None
            else (final_selection, exploration_pool)
        )
        selected = compose_real_population(
            final_selection.state,
            groups,
            size=population_size,
            source="gpsaf-surrogate-selection",
            refill_origin="gpsaf_exploration_refill",
        )
        diagnostics.update(dict(selected.state.diagnostics))
        diagnostics["search_selection_source"] = selected.source
        diagnostics["search_candidate_id_count"] = len(selected.candidates)
    except Exception as exc:  # noqa: BLE001 - surrogate selection has a generation-local real fallback.
        return None, {
            **diagnostics,
            "surrogate_error": f"{exc.__class__.__name__}: {exc}",
        }

    return selected.population, diagnostics
