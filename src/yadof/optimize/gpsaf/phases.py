from __future__ import annotations

import os
import random
from typing import Sequence

from ...surrogate.training import (
    DeterministicPredictionProvider,
    DeterministicSurrogateComponent,
    SurrogateTrainingData,
    SurrogateContractError,
)
from ..primitives import (
    CandidatePool,
    CandidateSelection,
    PredictedCostRows,
    SearchCandidate,
    SearchState,
    advance_search,
    bind_surrogate_prediction,
    combine_candidate_pools,
    combine_predicted_cost_rows,
    compose_real_population,
    continue_search_from,
    fork_search_state,
    prepare_search,
    search_candidates,
    select_candidate_indices,
)
from ..strategy import GenerationContext, HistoryRecord, Population
from .coverage import select_hypervolume_indices
from .tournament import tournament_winner, probabilistic_knockout, replacement_probabilities


def _progress(message: str) -> None:
    if str(os.environ.get("YADOF_PROGRESS", "")).strip().lower() in {"1", "true", "yes", "on"}:
        print(f"[yadof] {message}", flush=True)


def surrogate_state_ready(
    surrogate: DeterministicSurrogateComponent,
    context: GenerationContext,
    training_data: SurrogateTrainingData,
) -> bool:
    if not isinstance(surrogate, DeterministicSurrogateComponent):
        raise TypeError("GPSAF readiness requires a deterministic surrogate component")
    if not isinstance(training_data, SurrogateTrainingData):
        raise TypeError("GPSAF readiness requires explicit SurrogateTrainingData")
    try:
        return bool(surrogate.has_trained_state(context, training_data))
    except SurrogateContractError:
        raise
    except Exception:
        return False


def predict_pool(
    surrogate: DeterministicPredictionProvider,
    context: GenerationContext,
    pool: CandidatePool,
    training_data: SurrogateTrainingData,
) -> PredictedCostRows:
    """Bind one typed deterministic prediction at the explicit pool edge."""

    if not pool.candidates:
        raise ValueError("surrogate prediction requires a non-empty candidate pool")
    if not isinstance(surrogate, DeterministicPredictionProvider):
        raise TypeError("GPSAF prediction requires a typed prediction provider")
    if not isinstance(training_data, SurrogateTrainingData):
        raise TypeError("GPSAF prediction requires explicit SurrogateTrainingData")
    _progress(f"surrogate: predicting {len(pool.candidates)} candidates")
    prediction = surrogate.predict_for_selection(
        context,
        pool.population,
        training_data,
    )
    return bind_surrogate_prediction(pool, prediction)


def distance_sq(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("cluster parameter widths must match")
    return sum((float(a) - float(b)) ** 2 for a, b in zip(left, right))


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


def run_alpha_phase(
    state: SearchState,
    batch_target: int,
    *,
    surrogate: DeterministicSurrogateComponent,
    generation_context: GenerationContext,
    settings,
    training_data: SurrogateTrainingData,
    rng=None,
) -> tuple[
    CandidateSelection | None,
    PredictedCostRows | None,
    dict[str, object],
]:
    pools: list[CandidatePool] = []
    predictions: list[PredictedCostRows] = []
    current = state
    alpha = max(1, settings.alpha)
    rng = rng if rng is not None else random.Random(generation_context.random_seed + 313)

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
    combined_prediction = combine_predicted_cost_rows(
        combined_pool,
        predictions,
        source="gpsaf-alpha-predicted-costs",
    )
    indices = []
    for position in range(batch_target):
        competitors = [batch * batch_target + position for batch in range(alpha)]
        winner = tournament_winner(
            [combined_prediction.costs[i] for i in competitors], rng,
            valid=[combined_prediction.valid_mask[i] for i in competitors],
        )
        indices.append(competitors[winner])
    selected = select_candidate_indices(
        current, combined_pool, indices, source="gpsaf-alpha-selection",
    )
    return selected, combined_prediction, {
        "alpha_batches": len(pools),
        "alpha_replacements": sum(index >= batch_target for index in indices),
        "alpha_candidate_count": len(combined_pool.candidates),
        "alpha_selection": "positional-feasibility-pareto-tournament",
        "alpha_selected_indices": tuple(indices),
    }


def run_beta_phase(
    anchors: CandidateSelection,
    anchor_prediction: PredictedCostRows,
    batch_target: int,
    *,
    surrogate: DeterministicSurrogateComponent,
    generation_context: GenerationContext,
    settings,
    training_data: SurrogateTrainingData,
    error_scales=None,
    rng=None,
) -> tuple[CandidateSelection, dict[str, object]]:
    beta = max(0, settings.beta)
    rng = rng if rng is not None else random.Random(generation_context.random_seed + 317)
    anchor_costs = dict(zip(anchor_prediction.candidate_ids, anchor_prediction.costs))
    if beta <= 0 or not anchors.candidates or error_scales is None:
        return anchors, {
            "beta_iterations": 0,
            "beta_candidate_count": 0,
            "beta_replacements": 0,
            "beta_cluster_size_max": 0,
            "beta_error_ready": error_scales is not None,
            "_prediction_rows": tuple(anchor_costs[c.candidate_id] for c in anchors.candidates),
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

    real_state = continue_search_from(anchors.state, sim_state)
    combined_pool = combine_candidate_pools(
        real_state,
        (anchors, *beta_pools),
    )
    combined_prediction = combine_predicted_cost_rows(
        combined_pool,
        (anchor_prediction, *beta_predictions),
        source="gpsaf-beta-predicted-costs",
    )
    index_by_id = {candidate.candidate_id: i for i, candidate in enumerate(combined_pool.candidates)}
    cluster_sizes = tuple(len(bucket) for bucket in clusters)
    probabilities = replacement_probabilities(cluster_sizes, settings.gamma)
    indices = []
    for position, bucket in enumerate(clusters):
        chosen = position
        if bucket:
            local_indices = [index_by_id[candidate.candidate_id] for candidate in bucket]
            winner = probabilistic_knockout(
                [combined_prediction.costs[i] for i in local_indices], error_scales, rng,
                valid=[combined_prediction.valid_mask[i] for i in local_indices],
            )
            if rng.random() < probabilities[position]:
                chosen = local_indices[winner]
        indices.append(chosen)
    coverage_info = {}
    if settings.infill_selection == "hypervolume":
        indices, coverage_info = select_hypervolume_indices(
            combined_prediction.costs,
            combined_prediction.valid_mask,
            [row.costs for row in generation_context.history],
            len(anchors.candidates),
            indices,
        )
    final_selection = select_candidate_indices(
        real_state, combined_pool, indices, source="gpsaf-beta-selection"
    )
    anchor_ids = {candidate.candidate_id for candidate in anchors.candidates}
    replacements = sum(
        candidate.candidate_id not in anchor_ids
        for candidate in final_selection.candidates
    )

    return final_selection, {
        "beta_error_ready": True,
        "beta_replacement_probabilities": probabilities,
        "beta_prediction_error": tuple(error_scales),
        "beta_noise": "independent-normal-max-error-scale",
        "_prediction_rows": tuple(combined_prediction.costs[i] for i in indices),
        "beta_iterations": len(beta_pools),
        "beta_candidate_count": sum(len(pool.candidates) for pool in beta_pools),
        "beta_replacements": int(replacements),
        "beta_cluster_size_max": max(cluster_sizes, default=0),
        "beta_cluster_sizes": cluster_sizes,
        "beta_selection": (
            "history-hypervolume-greedy"
            if settings.infill_selection == "hypervolume"
            else "nearest-alpha-cluster-pkt-gamma-replacement"
        ),
        "beta_pool_size": len(combined_pool.candidates),
        "beta_selected_count": len(final_selection.candidates),
        **coverage_info,
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
    surrogate: DeterministicSurrogateComponent,
    generation_index: int,
    population_size: int,
    seed: int,
    settings,
    training_data: SurrogateTrainingData,
    error_scales=None,
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
        rng = random.Random(seed + generation_index * 1009 + 313)
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
            main_state = exploration_pool.state
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
            rng=rng,
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
            error_scales=error_scales,
            rng=rng,
        )
        prediction_rows = beta_info.pop("_prediction_rows")
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
        diagnostics["_prediction_rows"] = prediction_rows + (None,) * diagnostics["exploration_count"]
    except SurrogateContractError:
        raise
    except Exception as exc:  # noqa: BLE001 - surrogate selection has a generation-local real fallback.
        return None, {
            **diagnostics,
            "surrogate_error": f"{exc.__class__.__name__}: {exc}",
        }

    return selected.population, diagnostics
