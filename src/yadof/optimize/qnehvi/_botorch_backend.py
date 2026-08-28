"""BoTorch-owned numerical core for the experimental discrete backend."""

from __future__ import annotations

from importlib import metadata
import time
from typing import Sequence
import warnings

import numpy as np
import torch
from botorch.acquisition.multi_objective.logei import (
    qLogNoisyExpectedHypervolumeImprovement,
)
from botorch.models.ensemble import EnsembleModel
from botorch.sampling.base import MCSampler

from ...job_template.rawdata_projector import JointObjectiveSamples


_QLOGNEHVI_CLASS = qLogNoisyExpectedHypervolumeImprovement


class _LookupEnsembleModel(EnsembleModel):
    """Map fixed design rows to aligned sample-backed objective draws."""

    def __init__(self, X: torch.Tensor, samples: torch.Tensor) -> None:
        super().__init__()
        self.register_buffer("lookup_x", X)
        self.register_buffer("lookup_samples", samples)
        self._num_outputs = int(samples.shape[-1])

    def forward(self, X: torch.Tensor) -> torch.Tensor:
        flat = X.reshape(-1, X.shape[-1])
        matches = torch.isclose(
            flat[:, None, :],
            self.lookup_x[None, :, :],
            rtol=0.0,
            atol=1e-12,
        ).all(dim=-1)
        if not matches.any(dim=-1).all():
            raise ValueError("qLogNEHVI requested a point outside the fixed lookup pool")
        if torch.any(matches.sum(dim=-1) != 1):
            raise ValueError("qLogNEHVI lookup points must be unique")
        indices = matches.to(dtype=torch.int64).argmax(dim=-1)
        values = self.lookup_samples[:, indices, :]
        batch_shape = X.shape[:-2]
        values = values.reshape(
            self.lookup_samples.shape[0],
            *batch_shape,
            X.shape[-2],
            self._num_outputs,
        )
        return values.movedim(0, len(batch_shape))


class _EnumerateSampler(MCSampler):
    """Enumerate every supplied empirical draw exactly once and in order."""

    def forward(self, posterior):
        return posterior.values.movedim(-3, 0)

    def _update_base_samples(self, posterior, base_sampler) -> None:
        del posterior, base_sampler


def score_discrete_qlognehvi(
    *,
    baseline_population: Sequence[Sequence[float]],
    baseline_costs: Sequence[Sequence[float]],
    candidate_samples: JointObjectiveSamples,
    candidate_batches: Sequence[Sequence[int]],
    reference_point: Sequence[float] | None,
    seed: int,
    device: str,
    minimum_unique_support: int | None,
    low_support_policy: str,
) -> dict[str, object]:
    started = time.perf_counter()
    costs = np.asarray(candidate_samples.cost_samples, dtype=np.float64)
    valid = np.asarray(candidate_samples.valid_mask, dtype=bool)
    draw_count, candidate_count, objective_count = costs.shape
    if objective_count < 2:
        raise ValueError("qLogNEHVI requires at least two objectives")
    if candidate_count == 0:
        raise ValueError("qLogNEHVI candidate pool must not be empty")
    candidate_x = _matrix(
        candidate_samples.normalized_population,
        "candidate population",
    )
    if candidate_x.shape[0] != candidate_count:
        raise ValueError("candidate population does not align with objective samples")
    _require_normalized(candidate_x, "candidate population")
    _require_unique_rows(candidate_x, "candidate population")

    baseline_x = _matrix(baseline_population, "baseline population")
    baseline_y = _matrix(baseline_costs, "baseline costs")
    if baseline_x.shape[0] != baseline_y.shape[0]:
        raise ValueError("baseline population and costs must have the same row count")
    if baseline_x.shape[1] != candidate_x.shape[1]:
        raise ValueError("baseline and candidate parameter widths must match")
    if baseline_y.shape[1] != objective_count:
        raise ValueError("baseline objective width does not match candidate samples")
    _require_normalized(baseline_x, "baseline population")
    baseline_valid = (
        np.all(np.isfinite(baseline_y), axis=1)
        & np.all((baseline_y >= 0.0) & (baseline_y <= 1.0), axis=1)
    )
    excluded_baseline = int(baseline_valid.size - np.count_nonzero(baseline_valid))
    baseline_x = baseline_x[baseline_valid]
    baseline_y = baseline_y[baseline_valid]
    if baseline_x.shape[0] == 0:
        raise ValueError("qLogNEHVI needs at least one finite in-contract baseline row")
    _require_unique_rows(baseline_x, "valid baseline population")
    if _rows_overlap(baseline_x, candidate_x):
        raise ValueError("candidate pool must exclude completed baseline rows")

    reference = (
        np.ones((objective_count,), dtype=np.float64)
        if reference_point is None
        else np.asarray(tuple(reference_point), dtype=np.float64)
    )
    if reference.shape != (objective_count,) or not np.all(np.isfinite(reference)):
        raise ValueError("reference_point must be one finite value per objective")
    if np.any(reference < 0.0) or np.any(reference > 1.0):
        raise ValueError("reference_point must follow the [0, 1] minimization-cost contract")

    batches = tuple(tuple(int(index) for index in batch) for batch in candidate_batches)
    if not batches:
        raise ValueError("candidate_batches must not be empty")
    for batch in batches:
        if not batch:
            raise ValueError("qLogNEHVI candidate batches must not be empty")
        if len(batch) != len(set(batch)):
            raise ValueError("one qLogNEHVI batch cannot repeat a candidate index")
        if min(batch) < 0 or max(batch) >= candidate_count:
            raise IndexError("qLogNEHVI candidate batch index is outside the pool")

    in_contract = np.all(np.isfinite(costs), axis=2) & np.all(
        (costs >= 0.0) & (costs <= 1.0), axis=2
    )
    usable_draws = np.all(valid & in_contract, axis=1)
    usable_indices = np.flatnonzero(usable_draws)
    if usable_indices.size == 0:
        raise RuntimeError("qLogNEHVI has no complete valid objective draw")

    support = _support_diagnostics(
        candidate_samples,
        usable_indices,
        minimum_unique_support=minimum_unique_support,
        low_support_policy=low_support_policy,
    )
    selected_costs = np.ascontiguousarray(costs[usable_indices], dtype=np.float64)
    torch_device = torch.device(str(device))
    if torch_device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("requested qLogNEHVI CUDA device is unavailable")
    if torch_device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(torch_device)

    baseline_x_t = torch.as_tensor(
        baseline_x,
        dtype=torch.float64,
        device=torch_device,
    )
    candidate_x_t = torch.as_tensor(
        candidate_x,
        dtype=torch.float64,
        device=torch_device,
    )
    baseline_samples = -torch.as_tensor(
        baseline_y,
        dtype=torch.float64,
        device=torch_device,
    ).unsqueeze(0).expand(int(usable_indices.size), -1, -1)
    candidate_costs_t = torch.as_tensor(
        selected_costs,
        dtype=torch.float64,
        device=torch_device,
    )
    lookup_x = torch.cat((baseline_x_t, candidate_x_t), dim=0)
    lookup_samples = torch.cat((baseline_samples, -candidate_costs_t), dim=1)
    model = _LookupEnsembleModel(lookup_x, lookup_samples)
    sampler = _EnumerateSampler(
        sample_shape=torch.Size((int(usable_indices.size),)),
        seed=int(seed),
    )
    acquisition = _QLOGNEHVI_CLASS(
        model=model,
        ref_point=(-reference).tolist(),
        X_baseline=baseline_x_t,
        sampler=sampler,
        prune_baseline=False,
        cache_pending=False,
        cache_root=False,
        incremental_nehvi=True,
    )

    values = np.empty((len(batches),), dtype=np.float64)
    grouped: dict[int, list[tuple[int, tuple[int, ...]]]] = {}
    for position, batch in enumerate(batches):
        grouped.setdefault(len(batch), []).append((position, batch))
    with torch.no_grad():
        for entries in grouped.values():
            X = torch.stack(
                [candidate_x_t[list(batch)] for _position, batch in entries],
                dim=0,
            )
            evaluated = acquisition(X).detach().to(device="cpu", dtype=torch.float64)
            for (position, _batch), value in zip(entries, evaluated.reshape(-1)):
                values[position] = float(value.item())
    if not np.all(np.isfinite(values)):
        raise RuntimeError("BoTorch qLogNEHVI returned a non-finite acquisition value")

    tensor_bytes = sum(
        tensor.numel() * tensor.element_size()
        for tensor in (
            baseline_x_t,
            candidate_x_t,
            baseline_samples,
            candidate_costs_t,
            lookup_x,
            lookup_samples,
        )
    )
    cuda_peak = (
        int(torch.cuda.max_memory_allocated(torch_device))
        if torch_device.type == "cuda"
        else 0
    )
    diagnostics = {
        "backend_distribution": "botorch",
        "backend_version": metadata.version("botorch"),
        "backend_class": "qLogNoisyExpectedHypervolumeImprovement",
        "direction": "minimization_cost_negated_once_for_backend_maximization",
        "reference_point_cost": reference.tolist(),
        "fixed_baseline": True,
        "observation_noise_included": False,
        "pending_supported_by_spike": False,
        "outcome_constraints_supported_by_spike": False,
        "gradient_candidate_optimization": False,
        "draw_policy": "enumerate_supplied_joint_draws_once",
        "seed": int(seed),
        "device": str(torch_device),
        "candidate_count": int(candidate_count),
        "objective_count": int(objective_count),
        "batch_count": len(batches),
        "baseline_input_count": int(baseline_valid.size),
        "baseline_valid_count": int(baseline_x.shape[0]),
        "baseline_excluded_count": excluded_baseline,
        "input_draw_count": int(draw_count),
        "usable_draw_count": int(usable_indices.size),
        "rejected_whole_draw_count": int(draw_count - usable_indices.size),
        "finite_one_is_valid": True,
        "resident_tensor_bytes": int(tensor_bytes),
        "cuda_peak_allocated_bytes": cuda_peak,
        "elapsed_sec": float(time.perf_counter() - started),
        **support,
    }
    return {
        "batch_indices": batches,
        "log_acquisition_values": tuple(float(value) for value in values),
        "diagnostics": diagnostics,
    }


def _support_diagnostics(
    samples: JointObjectiveSamples,
    usable_indices: np.ndarray,
    *,
    minimum_unique_support: int | None,
    low_support_policy: str,
) -> dict[str, object]:
    policy = str(low_support_policy).strip().lower()
    if policy not in {"reject", "warn"}:
        raise ValueError("low_support_policy must be 'reject' or 'warn'")
    minimum = None if minimum_unique_support is None else int(minimum_unique_support)
    if minimum is not None and minimum <= 0:
        raise ValueError("minimum_unique_support must be positive")
    source = dict(samples.source_diagnostics)
    support_kind = source.get("support_kind")
    nominal = source.get("unique_support")
    draw_sources = tuple(source.get("draw_sources") or samples.draw_ids)
    if len(draw_sources) != len(samples.draw_ids):
        raise ValueError("source draw_sources must align with objective sample draws")
    effective: int | None = None
    low = False
    if support_kind == "finite":
        if nominal is None:
            raise ValueError("finite objective samples must report unique_support")
        effective = len({draw_sources[int(index)] for index in usable_indices})
        reported = source.get("effective_unique_support")
        if reported is not None:
            effective = min(effective, int(reported))
        if minimum is not None and effective < minimum:
            low = True
            message = (
                f"finite posterior effective support {effective} is below required "
                f"minimum {minimum}"
            )
            if policy == "reject":
                raise RuntimeError(message)
            warnings.warn(message, RuntimeWarning, stacklevel=3)
    elif minimum is not None:
        raise ValueError(
            "minimum_unique_support requires source_diagnostics support_kind='finite'"
        )
    return {
        "support_kind": support_kind,
        "nominal_unique_support": (
            None if nominal is None else int(nominal)
        ),
        "effective_unique_support": effective,
        "minimum_unique_support": minimum,
        "low_support_policy": policy,
        "low_support": low,
    }


def _matrix(values: Sequence[Sequence[float]], label: str) -> np.ndarray:
    rows = tuple(tuple(float(value) for value in row) for row in values)
    if not rows:
        return np.zeros((0, 0), dtype=np.float64)
    matrix = np.asarray(rows, dtype=np.float64)
    if matrix.ndim != 2:
        raise ValueError(f"{label} must be a two-dimensional sequence")
    return np.ascontiguousarray(matrix, dtype=np.float64)


def _require_normalized(values: np.ndarray, label: str) -> None:
    if not np.all(np.isfinite(values)) or np.any(values < 0.0) or np.any(values > 1.0):
        raise ValueError(f"{label} must contain finite normalized values in [0, 1]")


def _require_unique_rows(values: np.ndarray, label: str) -> None:
    if len({tuple(float(value) for value in row) for row in values}) != values.shape[0]:
        raise ValueError(f"{label} must not contain duplicate rows")


def _rows_overlap(left: np.ndarray, right: np.ndarray) -> bool:
    left_rows = {tuple(float(value) for value in row) for row in left}
    return any(tuple(float(value) for value in row) in left_rows for row in right)


__all__ = ["score_discrete_qlognehvi"]
