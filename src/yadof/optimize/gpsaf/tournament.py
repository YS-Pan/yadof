"""GPSAF paper, Sections III-A/B: positional selection and noisy cluster PKT.

Objectives are minimized; separate constraints, when supplied, satisfy G <= 0.
The application adapter normally folds task constraints into its cost objectives.
"""
from __future__ import annotations

import math
from typing import Sequence


def dominates(left: Sequence[float], right: Sequence[float]) -> bool:
    if len(left) != len(right):
        raise ValueError("objective widths must match")
    return all(a <= b for a, b in zip(left, right)) and any(
        a < b for a, b in zip(left, right)
    )


def tournament_winner(costs, rng, *, constraints=None, valid=None) -> int:
    """Least violation if all infeasible, otherwise random nondominated feasible."""
    if not costs:
        raise ValueError("a tournament must have competitors")
    width = len(costs[0])
    if not width or any(len(row) != width for row in costs):
        raise ValueError("tournament objectives must have one positive width")
    flags = (True,) * len(costs) if valid is None else tuple(valid)
    gs = ((),) * len(costs) if constraints is None else tuple(constraints)
    if len(flags) != len(costs) or len(gs) != len(costs):
        raise ValueError("tournament constraints and validity must align")
    if any(math.isnan(float(v)) for row in (*costs, *gs) for v in row):
        raise ValueError("NaN is not a tournament score")
    violation = [
        math.fsum(max(0.0, float(v)) for v in g) if ok else math.inf
        for g, ok in zip(gs, flags)
    ]
    feasible = [i for i, cv in enumerate(violation) if cv == 0.0]
    if not feasible:
        minimum = min(violation)
        winners = [i for i, cv in enumerate(violation) if cv == minimum]
    else:
        winners = [
            i for i in feasible
            if not any(dominates(costs[j], costs[i]) for j in feasible if j != i)
        ]
    return winners[0] if len(winners) == 1 else rng.choice(winners)


def replacement_probabilities(cluster_sizes: Sequence[int], gamma: float) -> tuple[float, ...]:
    if not math.isfinite(gamma) or gamma < 0:
        raise ValueError("gamma must be finite and nonnegative")
    if any(type(size) is not int or size < 0 for size in cluster_sizes):
        raise ValueError("cluster sizes must be nonnegative integers")
    largest = max(cluster_sizes, default=0)
    return tuple(0.0 if size == 0 else (size / largest) ** gamma for size in cluster_sizes)


def probabilistic_knockout(costs, error, rng, *, constraints=None, constraint_error=(), valid=None) -> int:
    """One winner: shuffle once, duplicate a random competitor for odd rounds.

    The paper leaves the noise distribution unspecified. This adapter uses
    independent zero-mean normal perturbations with maximum-error scale, freshly
    sampled per competitor, objective/constraint and match. Zero scale is exact.
    """
    if not costs or len(error) != len(costs[0]):
        raise ValueError("PKT requires competitors and one error scale per objective")
    gs = ((),) * len(costs) if constraints is None else tuple(constraints)
    flags = (True,) * len(costs) if valid is None else tuple(valid)
    scales = tuple(float(value) for value in (*error, *constraint_error))
    if any(not math.isfinite(value) or value < 0 for value in scales):
        raise ValueError("prediction errors must be finite and nonnegative")
    if len(gs) != len(costs) or len(flags) != len(costs):
        raise ValueError("PKT rows must align")
    if any(len(row) != len(error) for row in costs) or any(len(g) != len(constraint_error) for g in gs):
        raise ValueError("PKT error widths must match the scores")

    def perturb(row, sigma, ok):
        return tuple(
            float(value) + (rng.gauss(0.0, scale) if ok and scale > 0 else 0.0)
            for value, scale in zip(row, sigma)
        )

    participants = list(range(len(costs)))
    rng.shuffle(participants)
    while len(participants) > 1:
        if len(participants) % 2:
            participants.append(rng.choice(participants))
        winners = []
        for offset in range(0, len(participants), 2):
            pair = participants[offset:offset + 2]
            noisy_f = [perturb(costs[i], error, flags[i]) for i in pair]
            noisy_g = [perturb(gs[i], constraint_error, flags[i]) for i in pair]
            chosen = tournament_winner(noisy_f, rng, constraints=noisy_g, valid=[flags[i] for i in pair])
            winners.append(pair[chosen])
        participants = winners
    return participants[0]
