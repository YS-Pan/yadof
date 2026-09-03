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
    selected: list[int] = []
    heap: list[tuple[float, int, int]] = []
    for index, is_valid in enumerate(valid):
        if is_valid:
            gain = max(0.0, float(indicator(np.vstack((front, candidate_costs[index])))) - value)
            heapq.heappush(heap, (-gain, index, 0))

    gains: list[float] = []
    while heap and len(selected) < count:
        negative_gain, index, iteration = heapq.heappop(heap)
        # Coverage is submodular: an earlier marginal gain is an upper bound.
        if iteration != len(selected):
            gain = max(0.0, float(indicator(np.vstack((front, candidate_costs[index])))) - value)
            heapq.heappush(heap, (-gain, index, len(selected)))
            continue
        if -negative_gain <= 1e-12:
            break
        selected.append(index)
        gains.append(-negative_gain)
        front = np.vstack((front, candidate_costs[index]))
        front = front[sorting.do(front, only_non_dominated_front=True)]
        value = float(indicator(front))

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
