"""Finite empirical posterior adapter over conditional-INR ensemble members."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np

from ...job_template.rawdata_contract import (
    NamedRawDataItem,
    resolve_main_array_key,
)
from ...job_template.rawdata_template import (
    RawDataFieldSelector,
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
from .modeling import member_list
from .types import RawDataSchema, SurrogateState


_MAX_RETAINED_FAILURES = 32


@dataclass(frozen=True, slots=True)
class _FailedPrediction:
    error_type: str
    message: str


class ConditionalINRRawDataSampler:
    """Persistent seeded member draws evaluated on the stored full grid."""

    def __init__(
        self,
        state: SurrogateState,
        schema_template: RawDataSchemaTemplate,
        selectors_by_item: tuple[RawDataFieldSelector, ...],
        member_indices: tuple[int, ...],
        *,
        draw_count: int,
        seed: int,
        strategy_signature: str,
    ) -> None:
        self._state = state
        self._schema_template = schema_template
        self._selectors_by_item = selectors_by_item
        self._member_indices = member_indices
        draw_ids = tuple(
            f"conditional-inr-seed-{int(seed)}-draw-{index:06d}"
            for index in range(int(draw_count))
        )
        self._diagnostics = RawDataPosteriorDiagnostics(
            posterior_kind="empirical_ensemble",
            requested_draw_count=int(draw_count),
            support_kind=SUPPORT_FINITE,
            unique_support=len(member_list(state.model)),
            seed=int(seed),
            draw_ids=draw_ids,
            draw_sources=tuple(
                f"conditional-inr-member-{member_index:04d}"
                for member_index in member_indices
            ),
            schema_signature=schema_template.signature,
            state_signature=str(state.state_signature),
            strategy_signature=str(strategy_signature),
            approximate=True,
            limitations=(
                "finite empirical ensemble support; repeated draws add no support",
                "conditional-INR member spread is not a calibrated posterior",
                "full stored-grid rawData reconstruction only",
                "observation noise is not included",
            ),
            field_selectors=schema_template.field_selectors,
            observation_noise_included=False,
        )

    @property
    def schema(self) -> RawDataSchemaTemplate:
        return self._schema_template

    @property
    def diagnostics(self) -> RawDataPosteriorDiagnostics:
        return self._diagnostics

    def predict(
        self,
        population: Sequence[Sequence[float]],
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
                cache_key = (member_index, row)
                result = cache.get(cache_key)
                if result is None:
                    result = self._predict_one(member_index, row)
                    cache[cache_key] = result
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
        self,
        member_index: int,
        row: tuple[float, ...],
    ) -> StructuredRawDataSample | _FailedPrediction:
        try:
            if len(row) != len(self._state.parameter_names):
                raise ValueError(
                    "normalized candidate width does not match the trained state"
                )
            if not np.all(np.isfinite(np.asarray(row, dtype=np.float64))):
                raise ValueError("normalized candidate values must be finite")
            x = runtime._x_matrix((row,), len(self._state.parameter_names))
            predicted = runtime._predict_selected_member_flat(
                self._state,
                x,
                member_index,
            )
            if predicted.shape != (1, int(self._state.schema.flat_dim)):
                raise ValueError(
                    "conditional-INR member prediction returned an unexpected shape"
                )
            return _reconstruct_member_sample(
                self._schema_template,
                self._selectors_by_item,
                self._state.schema,
                predicted[0],
            )
        except Exception as exc:
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
) -> ConditionalINRRawDataSampler:
    """Create a fixed-draw sampler from the context's trained state."""

    requested = int(draw_count)
    if requested <= 0:
        raise ValueError("draw_count must be positive")
    state = runtime._require_state(context.config, component.settings)
    strategy_signature = str(context.strategy_signature)
    if state.strategy_signature != strategy_signature:
        raise RuntimeError(
            "conditional-INR posterior state belongs to a different strategy namespace"
        )
    if state.schema is None or state.model is None:
        raise RuntimeError("conditional-INR posterior requires a trained rawData model")
    members = member_list(state.model)
    if not members:
        raise RuntimeError("conditional-INR posterior has no ensemble members")
    schema_template, selectors_by_item = _schema_template_from_context(
        context,
        state.schema,
    )
    selected = _seeded_member_indices(len(members), requested, int(seed))
    return ConditionalINRRawDataSampler(
        state,
        schema_template,
        selectors_by_item,
        selected,
        draw_count=requested,
        seed=int(seed),
        strategy_signature=strategy_signature,
    )


def _schema_template_from_context(
    context,
    schema: RawDataSchema,
) -> tuple[RawDataSchemaTemplate, tuple[RawDataFieldSelector, ...]]:
    try:
        evidence = context.session.named_rawdata_samples(status="completed")
    except AttributeError as exc:
        raise RuntimeError(
            "campaign session does not expose named rawData evidence"
        ) from exc
    failures: list[str] = []
    for job_name, items in evidence:
        if len(items) != len(schema.templates):
            failures.append(f"{job_name}: item count mismatch")
            continue
        try:
            state_items = []
            selectors = []
            for item_index, (evidence_item, payload) in enumerate(
                zip(items, schema.templates)
            ):
                evidence_key = resolve_main_array_key(evidence_item.payload)
                state_key = resolve_main_array_key(payload)
                if evidence_key != state_key:
                    raise ValueError(
                        f"item {item_index} main key changed from "
                        f"{state_key!r} to {evidence_key!r}"
                    )
                state_items.append(NamedRawDataItem(evidence_item.filename, payload))
                selectors.append((evidence_item.filename, state_key))
            for slot in schema.modeled_slots:
                if slot.key != selectors[slot.item_index][1]:
                    raise ValueError(
                        "posterior reconstruction requires all modeled slots to be "
                        "resolved rawData main arrays; axes and metadata stay frozen"
                    )
            return RawDataSchemaTemplate.from_items(state_items), tuple(selectors)
        except Exception as exc:
            failures.append(f"{job_name}: {exc}")
    detail = "; ".join(failures[:3]) or "no completed evidence"
    raise RuntimeError(
        "no completed named rawData sample is compatible with the trained "
        f"conditional-INR schema ({detail})"
    )


def _reconstruct_member_sample(
    template: RawDataSchemaTemplate,
    selectors_by_item: tuple[RawDataFieldSelector, ...],
    schema: RawDataSchema,
    flat: np.ndarray,
) -> StructuredRawDataSample:
    arrays = {
        field.selector: np.asarray(field.payload[field.main_key]).copy()
        for field in template.fields
    }
    vector = np.asarray(flat, dtype=np.float64).reshape(-1)
    if vector.size != int(schema.flat_dim):
        raise ValueError("conditional-INR member prediction width changed")
    for slot in schema.modeled_slots:
        selector = selectors_by_item[slot.item_index]
        expected = np.asarray(schema.templates[slot.item_index][slot.key])
        values = vector[slot.start : slot.end].reshape(slot.shape)
        if np.issubdtype(expected.dtype, np.integer):
            values = np.rint(values)
        arrays[selector] = values.astype(expected.dtype, copy=False)
    return template.reconstruct(arrays)


def _seeded_member_indices(
    member_count: int,
    draw_count: int,
    seed: int,
) -> tuple[int, ...]:
    rng = np.random.default_rng(int(seed) % (2**64))
    selected: list[int] = []
    while len(selected) < int(draw_count):
        selected.extend(int(value) for value in rng.permutation(int(member_count)))
    return tuple(selected[: int(draw_count)])


__all__ = ["ConditionalINRRawDataSampler", "make_rawdata_sampler"]
