"""Finite joint rawData function draws from hierarchical CAE predictors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np

from ...job_template.rawdata_template import (
    RawDataSchemaTemplate,
    StructuredRawDataSample,
)
from ..posterior import (
    MaterializedRawDataPosterior,
    RawDataFunctionDraw,
    RawDataPosteriorDiagnostics,
    SUPPORT_FINITE,
)
from . import runtime
from .schema import reconstruct_samples
from .types import HierarchicalState


_MAX_RETAINED_FAILURES = 32


@dataclass(frozen=True, slots=True)
class _FailedPrediction:
    error_type: str
    message: str


class HierarchicalCAERawDataSampler:
    """Persistent member identity shared across all candidates and fields."""

    def __init__(
        self,
        state: HierarchicalState,
        member_indices: tuple[int, ...],
        *,
        draw_count: int,
        seed: int,
        strategy_signature: str,
    ) -> None:
        if state.schema is None or state.model is None:
            raise RuntimeError("hierarchical CAE sampler requires a trained state")
        self._state = state
        self._member_indices = member_indices
        draw_ids = tuple(
            f"hierarchical-cae-seed-{int(seed)}-draw-{index:06d}"
            for index in range(int(draw_count))
        )
        self._diagnostics = RawDataPosteriorDiagnostics(
            posterior_kind="empirical_predictor_ensemble",
            requested_draw_count=int(draw_count),
            support_kind=SUPPORT_FINITE,
            unique_support=len(state.model.predictors),
            seed=int(seed),
            draw_ids=draw_ids,
            draw_sources=tuple(
                f"hierarchical-cae-predictor-{member_index:04d}"
                for member_index in member_indices
            ),
            schema_signature=state.schema.template.signature,
            state_signature=str(state.state_signature),
            strategy_signature=str(strategy_signature),
            approximate=True,
            limitations=(
                "finite uncalibrated predictor-ensemble support",
                "one member identity is preserved across candidates and fields",
                "regime uncertainty is structural, not observation noise",
                "full stored-grid rawData reconstruction only",
                "observation noise is not included",
            ),
            field_selectors=state.schema.template.field_selectors,
            observation_noise_included=False,
        )

    @property
    def schema(self) -> RawDataSchemaTemplate:
        assert self._state.schema is not None
        return self._state.schema.template

    @property
    def diagnostics(self) -> RawDataPosteriorDiagnostics:
        return self._diagnostics

    def predict(
        self, population: Sequence[Sequence[float]]
    ) -> MaterializedRawDataPosterior:
        rows = tuple(tuple(float(value) for value in row) for row in population)
        cache: dict[
            tuple[int, tuple[float, ...]],
            StructuredRawDataSample | _FailedPrediction,
        ] = {}
        draws = []
        retained_failures: list[Mapping[str, object]] = []
        failure_count = 0
        complete_sources: set[str] = set()
        for draw_index, (draw_id, member_index, source) in enumerate(
            zip(
                self._diagnostics.draw_ids,
                self._member_indices,
                self._diagnostics.draw_sources,
            )
        ):
            samples = []
            draw_complete = bool(rows)
            for candidate_index, row in enumerate(rows):
                key = (member_index, row)
                result = cache.get(key)
                if result is None:
                    result = self._predict_one(member_index, row)
                    cache[key] = result
                if isinstance(result, _FailedPrediction):
                    draw_complete = False
                    failure_count += 1
                    samples.append(())
                    if len(retained_failures) < _MAX_RETAINED_FAILURES:
                        retained_failures.append(
                            {
                                "error_type": result.error_type,
                                "draw_id": draw_id,
                                "draw_index": draw_index,
                                "draw_source": source,
                                "member_index": member_index,
                                "candidate_index": candidate_index,
                                "message": result.message,
                            }
                        )
                else:
                    samples.append(result)
            if draw_complete:
                complete_sources.add(source)
            draws.append(RawDataFunctionDraw(draw_id, tuple(samples)))
        diagnostics = self._diagnostics.for_prediction(
            len(rows),
            prediction_failure_count=failure_count,
            retained_prediction_failures=retained_failures,
            effective_unique_support=len(complete_sources),
        )
        return MaterializedRawDataPosterior(rows, tuple(draws), diagnostics)

    def _predict_one(
        self, member_index: int, row: tuple[float, ...]
    ) -> StructuredRawDataSample | _FailedPrediction:
        try:
            if len(row) != len(self._state.parameter_names):
                raise ValueError(
                    "normalized candidate width does not match the trained state"
                )
            x = runtime._x_matrix((row,), len(self._state.parameter_names))
            fields, _applicability, _residual = runtime._predict_members(
                self._state, x
            )
            assert self._state.schema is not None
            return reconstruct_samples(
                self._state.schema,
                tuple(values[int(member_index)] for values in fields),
            )[0]
        except Exception as exc:  # noqa: BLE001 - retain bounded diagnostics.
            return _FailedPrediction(
                type(exc).__name__,
                str(exc).replace("\r", " ").replace("\n", " ")[:512],
            )


def make_rawdata_sampler(
    context,
    *,
    component,
    draw_count: int,
    seed: int,
) -> HierarchicalCAERawDataSampler:
    requested = int(draw_count)
    if requested <= 0:
        raise ValueError("draw_count must be positive")
    state = runtime._require_state(context.config, component=component)
    strategy_signature = str(context.strategy_signature)
    if state.strategy_signature != strategy_signature:
        raise RuntimeError(
            "hierarchical CAE posterior state belongs to another strategy namespace"
        )
    if state.model is None:
        raise RuntimeError("hierarchical CAE posterior has no predictor members")
    member_count = len(state.model.predictors)
    if member_count <= 0:
        raise RuntimeError("hierarchical CAE posterior has no predictor members")
    selected = _seeded_member_indices(member_count, requested, int(seed))
    return HierarchicalCAERawDataSampler(
        state,
        selected,
        draw_count=requested,
        seed=int(seed),
        strategy_signature=strategy_signature,
    )


def _seeded_member_indices(
    member_count: int, draw_count: int, seed: int
) -> tuple[int, ...]:
    rng = np.random.default_rng(int(seed) % (2**64))
    selected: list[int] = []
    while len(selected) < int(draw_count):
        selected.extend(
            int(value) for value in rng.permutation(int(member_count))
        )
    return tuple(selected[: int(draw_count)])


__all__ = ["HierarchicalCAERawDataSampler", "make_rawdata_sampler"]
