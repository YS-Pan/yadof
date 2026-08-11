"""Pure analysis and plot-layout calculations for cost history."""

from __future__ import annotations

import math
from typing import Sequence

from .history import _metadata_int
from .style import MAX_VISIBLE_PARETO, MIN_SCATTER_ALPHA, SCATTER_ALPHA
from .types import ViewCostError


def is_pareto_efficient(costs) -> object:
    import numpy as np

    efficient = np.ones(costs.shape[0], dtype=bool)
    for i, cost in enumerate(costs):
        if efficient[i]:
            efficient[efficient] = np.any(
                costs[efficient] < cost, axis=1
            )
            efficient[i] = True
    return efficient


def gaussian_kernel_smoother(x_data, y_data, fine_x, sigma):
    import numpy as np

    smoothed = np.zeros_like(fine_x, dtype=float)
    for index, fine_value in enumerate(fine_x):
        weights = np.exp(
            -((x_data - fine_value) ** 2) / (2 * sigma**2)
        )
        weight_sum = float(np.sum(weights))
        if weight_sum > 0.0:
            smoothed[index] = np.sum(weights * y_data) / weight_sum
    return smoothed


def _visible_pareto_mask(pareto_mask, display_values):
    import numpy as np

    if int(np.sum(pareto_mask)) <= MAX_VISIBLE_PARETO:
        return pareto_mask
    out = np.zeros_like(pareto_mask)
    keep = np.where(pareto_mask)[0][
        np.argsort(display_values[pareto_mask])[:MAX_VISIBLE_PARETO]
    ]
    out[keep] = True
    return out


def _optimization_start_rows(
    rows: Sequence[dict[str, object]],
) -> list[tuple[int, float]]:
    starts: list[tuple[int, float]] = []
    seen: set[int] = set()
    for row in rows:
        opt_idx = row.get("optimization_index")
        if opt_idx is None or opt_idx in seen:
            continue
        seen.add(int(opt_idx))
        starts.append((int(opt_idx), float(row["row_number"])))
    return starts


def _row_cell_edges(
    rows: Sequence[dict[str, object]],
) -> list[float]:
    x = [float(row["row_number"]) for row in rows]
    if len(x) == 1:
        return [x[0] - 0.5, x[0] + 0.5]
    midpoints = [
        (left + right) / 2.0 for left, right in zip(x, x[1:])
    ]
    return [
        x[0] - (midpoints[0] - x[0]),
        *midpoints,
        x[-1] + (x[-1] - midpoints[-1]),
    ]


def _generation_groups(
    rows: Sequence[dict[str, object]],
) -> list[dict[str, object]]:
    groups: list[dict[str, object]] = []
    active_key: tuple[object, int] | None = None
    for index, row in enumerate(rows):
        generation = _metadata_int(row, "generation_index")
        run_identity = row.get("optimization_run_id")
        if run_identity is None:
            run_identity = row.get("optimization_index")
        key = None if generation is None else (run_identity, generation)
        if key == active_key:
            if key is not None:
                groups[-1]["last_position"] = index
                groups[-1]["last_x"] = float(row["row_number"])
                groups[-1]["rows"].append(row)  # type: ignore[union-attr]
            continue
        active_key = key
        if key is None:
            continue
        groups.append(
            {
                "generation_index": generation,
                "first_position": index,
                "last_position": index,
                "first_x": float(row["row_number"]),
                "last_x": float(row["row_number"]),
                "rows": [row],
            }
        )
    return groups


def _generation_regions(
    rows: Sequence[dict[str, object]],
) -> list[tuple[int, float, float]]:
    edges = _row_cell_edges(rows)
    regions: list[tuple[int, float, float]] = []
    for group in _generation_groups(rows):
        first_position = int(group["first_position"])
        last_position = int(group["last_position"])
        regions.append(
            (
                int(group["generation_index"]),
                edges[first_position],
                edges[last_position + 1],
            )
        )
    return regions


def _hash_change_rows(
    rows: Sequence[dict[str, object]],
) -> list[float]:
    starts: list[float] = []
    previous_hash = None
    seen_hash = False
    for row in rows:
        current_hash = row.get("job_static_hash")
        if current_hash is None:
            continue
        if seen_hash and current_hash != previous_hash:
            starts.append(float(row["row_number"]))
        previous_hash, seen_hash = current_hash, True
    return starts


def _scatter_alpha(row_count: int, *, threshold: int = 1000) -> float:
    row_count = max(1, int(row_count))
    if row_count <= threshold:
        return SCATTER_ALPHA
    return max(
        MIN_SCATTER_ALPHA,
        SCATTER_ALPHA * math.sqrt(float(threshold) / float(row_count)),
    )


def hypervolume_series(
    rows: Sequence[dict[str, object]],
    *,
    reference_point: Sequence[float] | None = None,
):
    """Return all-individual and current-generation HV at generation ends."""

    try:
        import numpy as np
        from pymoo.indicators.hv import HV
    except ImportError as exc:
        raise ViewCostError(
            "numpy and pymoo are required to calculate hypervolume"
        ) from exc
    if not rows:
        raise ViewCostError("Cannot calculate hypervolume from empty rows")

    groups = _generation_groups(rows)
    if not groups:
        groups = [
            {
                "last_x": float(rows[-1]["row_number"]),
                "rows": list(rows),
            }
        ]
    all_costs = np.asarray([row["costs"] for row in rows], dtype=float)
    objective_count = int(all_costs.shape[1])
    if reference_point is None:
        reference = (1.0,) * objective_count
    else:
        reference = tuple(float(value) for value in reference_point)
        if len(reference) != objective_count:
            raise ViewCostError(
                f"hypervolume reference point has {len(reference)} values; "
                f"expected {objective_count}"
            )
        if not all(math.isfinite(value) for value in reference):
            raise ViewCostError(
                "hypervolume reference point contains non-finite values"
            )

    indicator = HV(ref_point=np.asarray(reference, dtype=float))
    cumulative_rows: list[dict[str, object]] = []
    x_values: list[float] = []
    all_values: list[float] = []
    generation_values: list[float] = []

    def calculate(group_rows: Sequence[dict[str, object]]) -> float:
        matrix = np.asarray(
            [row["costs"] for row in group_rows], dtype=float
        )
        valid = matrix[
            np.all((matrix >= 0.0) & (matrix <= 1.0), axis=1)
        ]
        return float(indicator.do(valid)) if len(valid) else 0.0

    for group in groups:
        generation_rows = group["rows"]
        cumulative_rows.extend(generation_rows)  # type: ignore[arg-type]
        x_values.append(float(group["last_x"]))
        generation_values.append(
            calculate(generation_rows)  # type: ignore[arg-type]
        )
        all_values.append(calculate(cumulative_rows))

    return (
        np.asarray(x_values, dtype=float),
        np.asarray(all_values, dtype=float),
        np.asarray(generation_values, dtype=float),
        reference,
    )


def _hypervolume_axis_ylim(*series) -> tuple[float, float]:
    import numpy as np

    values = np.concatenate(
        [np.asarray(item, dtype=float) for item in series]
    )
    finite = values[np.isfinite(values)]
    if len(finite) == 0 or float(np.max(finite)) <= 0.0:
        return 0.0, 1.0
    return 0.0, float(np.max(finite)) * 1.05


__all__ = [
    "gaussian_kernel_smoother",
    "hypervolume_series",
    "is_pareto_efficient",
]
