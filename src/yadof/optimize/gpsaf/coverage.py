"""Deterministic predicted hypervolume coverage over an existing GPSAF pool."""

from __future__ import annotations

import heapq
from collections.abc import Sequence


def select_hypervolume_indices(
    costs: Sequence[Sequence[float]],
    valid: Sequence[bool],
    history_costs: Sequence[Sequence[float]],
    count: int,
    fallback: Sequence[int],
) -> tuple[tuple[int, ...], dict[str, object]]:
    """Greedily cover the fixed unit reference box, then preserve valid infill.

    Inputs are already bound and validated by the search primitives. Only means
    and the supplied real history are used; this is not an uncertainty-aware
    acquisition function. Pymoo owns hypervolume and nondominated sorting.
    """
    import numpy as np
    from pymoo.indicators.hv import HV
    from pymoo.util.nds.non_dominated_sorting import NonDominatedSorting

    candidate_costs = np.asarray(costs, dtype=float)
    front = np.asarray(history_costs, dtype=float).reshape(-1, candidate_costs.shape[1])
    front = front[np.isfinite(front).all(axis=1)]
    sorting = NonDominatedSorting()
    if len(front):
        front = front[sorting.do(front, only_non_dominated_front=True)]
    reference = np.ones(candidate_costs.shape[1])
    indicator = HV(ref_point=reference)
    value = float(indicator(front))
    zero_gain = np.any(candidate_costs >= reference, axis=1)
    for survivor in front:
        zero_gain |= np.all(survivor <= candidate_costs, axis=1)
    selected: list[int] = []
    heap: list[tuple[float, int, int]] = []
    def marginal_gain(index: int) -> float:
        candidate = candidate_costs[index]
        # A dominated rectangle or one outside the reference contributes exactly
        # zero. Avoid calling the HV backend for these common late-run cases.
        if zero_gain[index]:
            return 0.0
        return max(0.0, float(indicator(np.vstack((front, candidate)))) - value)

    for index, is_valid in enumerate(valid):
        if is_valid:
            gain = marginal_gain(index)
            heapq.heappush(heap, (-gain, index, 0))

    gains: list[float] = []
    while heap and len(selected) < count:
        negative_gain, index, iteration = heapq.heappop(heap)
        # Coverage is submodular: an earlier marginal gain is an upper bound.
        if iteration != len(selected):
            gain = marginal_gain(index)
            heapq.heappush(heap, (-gain, index, len(selected)))
            continue
        if -negative_gain <= 1e-12:
            break
        selected.append(index)
        gains.append(-negative_gain)
        front = np.vstack((front, candidate_costs[index]))
        front = front[sorting.do(front, only_non_dominated_front=True)]
        value = float(indicator(front))
        # The covered region only grows, so prior zero-gain flags stay valid.
        zero_gain |= np.all(candidate_costs[index] <= candidate_costs, axis=1)

    ordered = list(fallback) + list(range(len(candidate_costs)))
    for is_valid in (True, False):
        for index in ordered:
            if valid[index] == is_valid and index not in selected and len(selected) < count:
                selected.append(index)
    if len(selected) != count:
        raise ValueError("hypervolume infill cannot fill the requested candidate count")
    return tuple(selected), {
        "coverage_positive_count": len(gains),
        "coverage_gain": sum(gains),
        "coverage_reference_point": tuple(float(item) for item in reference),
    }
