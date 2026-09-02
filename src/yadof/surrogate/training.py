"""Explicit materialized surrogate data, prediction, and fit lifecycle values."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import hashlib
import json
import math
from collections.abc import Iterator, Sequence as MaterializedSequence
from types import MappingProxyType
import threading
import time
from typing import Callable, Mapping, Protocol, Sequence, runtime_checkable

import numpy as np

from ..job_template.rawdata_contract import resolve_main_array_key
from ..job_template.rawdata_template import (
    RawDataSchemaTemplate,
    StructuredRawDataSample,
)


_CONTENT_DOMAIN = b"yadof.surrogate-training-content:v1\0"
_PROVENANCE_DOMAIN = b"yadof.surrogate-training-provenance:v1\0"


@dataclass(frozen=True, slots=True)
class SurrogateTrainingData:
    """Owned, aligned, exactly hashable rawData training rows."""

    parameter_names: tuple[str, ...]
    normalized_variables: tuple[tuple[float, ...], ...]
    raw_data: tuple[StructuredRawDataSample, ...]
    row_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    statuses: tuple[str, ...] = ()
    valid_mask: tuple[bool, ...] = ()
    lineage: tuple[tuple[Mapping[str, object], ...], ...] = ()
    record_metadata: tuple[Mapping[str, object], ...] = ()
    transform_id: str | None = None
    schema_signature: str = field(init=False)
    content_digest: str = field(init=False)
    provenance_digest: str = field(init=False)

    def __post_init__(self) -> None:
        _require_materialized(self.parameter_names, "parameter_names")
        _require_materialized(
            self.normalized_variables,
            "normalized_variables",
            allow_array=True,
        )
        _require_materialized(self.raw_data, "raw_data")
        names = tuple(str(value) for value in self.parameter_names)
        if not names or any(not value for value in names):
            raise ValueError("surrogate training requires named parameters")
        if len(set(names)) != len(names):
            raise ValueError("surrogate training parameter names must be unique")
        variables = tuple(
            tuple(float(value) for value in row)
            for row in self.normalized_variables
        )
        width = len(names)
        for row in variables:
            if len(row) != width:
                raise ValueError(
                    f"surrogate training expected {width} normalized parameters, "
                    f"got {len(row)}"
                )
            if any(not math.isfinite(value) for value in row):
                raise ValueError("surrogate training parameters must be finite")
            if any(value < -1e-9 or value > 1.0 + 1e-9 for value in row):
                raise ValueError("surrogate training parameters must stay in [0, 1]")
        variables = tuple(
            tuple(max(0.0, min(1.0, value)) for value in row)
            for row in variables
        )
        samples = tuple(
            sample
            if isinstance(sample, StructuredRawDataSample)
            else StructuredRawDataSample.from_items(sample)
            for sample in self.raw_data
        )
        count = len(variables)
        if len(samples) != count:
            raise ValueError("parameter and rawData training rows must align")
        row_ids = _aligned_strings(
            self.row_ids,
            count,
            default=lambda index: f"materialized-row-{index:08d}",
            label="training row identities",
        )
        evidence_ids = _aligned_strings(
            self.evidence_ids,
            count,
            default=lambda index: row_ids[index],
            label="training evidence identities",
        )
        statuses = _aligned_strings(
            self.statuses,
            count,
            default=lambda _index: "succeeded",
            label="training row statuses",
        )
        mask = (
            tuple(True for _ in range(count))
            if not self.valid_mask
            else tuple(bool(value) for value in self.valid_mask)
        )
        if len(mask) != count:
            raise ValueError("training row-valid mask must align with data rows")
        lineage = _aligned_lineage(self.lineage, count)
        metadata_rows = _aligned_metadata(self.record_metadata, count)
        transform_id = (
            None
            if self.transform_id is None
            else str(self.transform_id).strip()
        )
        if transform_id == "":
            raise ValueError("transform_id must be non-empty when provided")

        if not samples:
            schema_signature = _hash_json(
                {"contract": "yadof.empty-surrogate-training-schema", "version": 1}
            )
        else:
            template = RawDataSchemaTemplate.from_items(samples[0].items)
            samples = tuple(template.validate_sample(sample) for sample in samples)
            schema_signature = template.signature
            _validate_numeric_targets(samples)

        content_digest = _training_content_digest(
            names,
            variables,
            samples,
            statuses,
            mask,
            schema_signature,
        )
        provenance_digest = _training_provenance_digest(
            row_ids,
            evidence_ids,
            statuses,
            mask,
            lineage,
            metadata_rows,
            transform_id,
        )
        object.__setattr__(self, "parameter_names", names)
        object.__setattr__(self, "normalized_variables", variables)
        object.__setattr__(self, "raw_data", samples)
        object.__setattr__(self, "row_ids", row_ids)
        object.__setattr__(self, "evidence_ids", evidence_ids)
        object.__setattr__(self, "statuses", statuses)
        object.__setattr__(self, "valid_mask", mask)
        object.__setattr__(self, "lineage", lineage)
        object.__setattr__(self, "record_metadata", metadata_rows)
        object.__setattr__(self, "transform_id", transform_id)
        object.__setattr__(self, "schema_signature", schema_signature)
        object.__setattr__(self, "content_digest", content_digest)
        object.__setattr__(self, "provenance_digest", provenance_digest)

    @property
    def sample_count(self) -> int:
        return sum(self.valid_mask)

    @property
    def selected_indices(self) -> tuple[int, ...]:
        return tuple(index for index, valid in enumerate(self.valid_mask) if valid)


def materialize_training_data(
    dataset,
    cost_table,
    *,
    row_ids: Sequence[str] | None = None,
    transform_id: str | None = None,
) -> SurrogateTrainingData:
    """Materialize identity-joined successful evidence into one training value."""

    from ..recorded_data.dataset import EvidenceState, InterpretationStatus

    evidence_lookup = {row.row_id: row for row in dataset.rows}
    cost_lookup = {row.row_id: row for row in cost_table.rows}
    if row_ids is None:
        selected_ids = tuple(
            row.row_id
            for row in dataset.rows
            if row.row_id in cost_lookup
            and row.evidence_state in {EvidenceState.COMMITTED, EvidenceState.DERIVED}
            and row.execution_status in {"completed", "derived"}
            and row.has_rawdata
            and cost_lookup[row.row_id].status == InterpretationStatus.SUCCEEDED
            and cost_lookup[row.row_id].normalized_variables is not None
        )
    else:
        selected_ids = tuple(str(value) for value in row_ids)

    variables: list[tuple[float, ...]] = []
    samples: list[StructuredRawDataSample] = []
    evidence_ids: list[str] = []
    statuses: list[str] = []
    lineage_rows: list[tuple[Mapping[str, object], ...]] = []
    metadata_rows: list[Mapping[str, object]] = []
    for row_id in selected_ids:
        evidence = evidence_lookup.get(row_id)
        cost = cost_lookup.get(row_id)
        if evidence is None or cost is None:
            raise KeyError(f"training row {row_id!r} is missing from evidence/cost views")
        if evidence.evidence_id != cost.evidence_id:
            raise ValueError(f"training row {row_id!r} has mismatched root identity")
        if evidence.evidence_state not in {EvidenceState.COMMITTED, EvidenceState.DERIVED}:
            raise ValueError(f"training row {row_id!r} is not committed or derived evidence")
        if evidence.execution_status not in {"completed", "derived"}:
            raise ValueError(f"training row {row_id!r} did not complete execution")
        if not evidence.has_rawdata:
            raise ValueError(f"training row {row_id!r} has no readable rawData")
        if cost.status != InterpretationStatus.SUCCEEDED or cost.normalized_variables is None:
            raise ValueError(f"training row {row_id!r} has no successful interpretation")
        variables.append(tuple(float(value) for value in cost.normalized_variables))
        samples.append(StructuredRawDataSample.from_items(evidence.load_rawdata()))
        evidence_ids.append(evidence.evidence_id)
        statuses.append(f"{evidence.evidence_state.value}:{cost.status.value}")
        lineage_rows.append(tuple(step.as_dict() for step in evidence.lineage))
        metadata_rows.append(dict(evidence.record))

    return SurrogateTrainingData(
        parameter_names=tuple(dataset.parameter_names),
        normalized_variables=tuple(variables),
        raw_data=tuple(samples),
        row_ids=selected_ids,
        evidence_ids=tuple(evidence_ids),
        statuses=tuple(statuses),
        valid_mask=tuple(True for _ in selected_ids),
        lineage=tuple(lineage_rows),
        record_metadata=tuple(metadata_rows),
        transform_id=transform_id,
    )


class SurrogateContractError(RuntimeError):
    """A prediction implementation/interface failure that must not become fallback."""


@dataclass(frozen=True, slots=True)
class SurrogatePrediction:
    """Transient deterministic rawData and current-cost prediction."""

    state_signature: str
    training_data_digest: str
    normalized_variables: tuple[tuple[float, ...], ...]
    raw_data: tuple[StructuredRawDataSample | None, ...]
    costs: tuple[tuple[float, ...], ...]
    intervals: tuple[tuple[tuple[float, float], ...], ...]
    interpretation_fingerprint: str
    diagnostics: Mapping[str, object] = field(default_factory=dict)
    kind: str = "deterministic_rawdata_current_cost"
    valid_mask: tuple[bool, ...] = ()

    def __post_init__(self) -> None:
        rows = tuple(tuple(float(value) for value in row) for row in self.normalized_variables)
        if rows:
            width = len(rows[0])
            if any(len(row) != width for row in rows):
                raise ValueError("surrogate prediction parameter rows must have one width")
        if any(
            not math.isfinite(value) or value < -1e-9 or value > 1.0 + 1e-9
            for row in rows
            for value in row
        ):
            raise ValueError("surrogate prediction parameters must be finite in [0, 1]")
        rows = tuple(
            tuple(max(0.0, min(1.0, value)) for value in row)
            for row in rows
        )
        valid = tuple(self.valid_mask) if self.valid_mask else (True,) * len(rows)
        if len(valid) != len(rows) or any(type(value) is not bool for value in valid):
            raise ValueError("surrogate prediction valid_mask must align and be boolean")
        samples = tuple(
            sample
            if sample is None or isinstance(sample, StructuredRawDataSample)
            else StructuredRawDataSample.from_items(sample)
            for sample in self.raw_data
        )
        present = tuple(sample for sample in samples if sample is not None)
        if present:
            template = RawDataSchemaTemplate.from_items(present[0].items)
            samples = tuple(
                None if sample is None else template.validate_sample(sample)
                for sample in samples
            )
        costs = tuple(tuple(float(value) for value in row) for row in self.costs)
        intervals = tuple(
            tuple((float(lower), float(upper)) for lower, upper in row)
            for row in self.intervals
        )
        count = len(rows)
        if len(samples) != count or len(costs) != count or len(intervals) != count:
            raise ValueError("surrogate prediction rows must align")
        for sample, cost_row, interval_row, is_valid in zip(samples, costs, intervals, valid):
            if len(cost_row) != len(interval_row):
                raise ValueError("surrogate cost and interval widths must align")
            if not is_valid:
                if sample is not None or not cost_row or any(value != math.inf for value in cost_row):
                    raise ValueError("failed prediction requires no rawData and all +inf costs")
                if any(pair != (math.inf, math.inf) for pair in interval_row):
                    raise ValueError("failed prediction requires +inf point intervals")
                continue
            if sample is None or any(not math.isfinite(value) for value in cost_row):
                raise ValueError("valid surrogate predictions require rawData and finite costs")
            if any(
                not math.isfinite(lower)
                or not math.isfinite(upper)
                or lower != value
                or upper != value
                for value, (lower, upper) in zip(cost_row, interval_row)
            ):
                raise ValueError(
                    "deterministic surrogate prediction intervals must be zero-width"
                )
        object.__setattr__(self, "state_signature", _sha256(self.state_signature, "state_signature"))
        object.__setattr__(
            self,
            "training_data_digest",
            _sha256(self.training_data_digest, "training_data_digest"),
        )
        object.__setattr__(self, "normalized_variables", rows)
        object.__setattr__(self, "raw_data", samples)
        object.__setattr__(self, "valid_mask", valid)
        object.__setattr__(self, "costs", costs)
        object.__setattr__(self, "intervals", intervals)
        object.__setattr__(
            self,
            "interpretation_fingerprint",
            _sha256(self.interpretation_fingerprint, "interpretation_fingerprint"),
        )
        object.__setattr__(self, "diagnostics", _freeze_json_mapping(self.diagnostics))
        if self.kind != "deterministic_rawdata_current_cost":
            raise ValueError("unsupported surrogate prediction kind")

    def as_gpsaf_rows(
        self,
    ) -> tuple[tuple[tuple[float, ...], tuple[tuple[float, float], ...]], ...]:
        return tuple(zip(self.costs, self.intervals))


@runtime_checkable
class DeterministicPredictionProvider(Protocol):
    """Typed deterministic prediction edge consumed by search selection."""

    def predict_for_selection(
        self,
        context,
        population,
        training_data: SurrogateTrainingData | None = None,
    ) -> SurrogatePrediction: ...


@runtime_checkable
class DeterministicSurrogateComponent(DeterministicPredictionProvider, Protocol):
    """Explicit deterministic component contract used by workspace programs.

    Every operation consumes a caller-materialized :class:`SurrogateTrainingData`
    value.  Implementations must not reconstruct training evidence through a
    campaign session or another hidden recorder query.
    """

    def validate(self, config, problem) -> None: ...

    def semantic_identity(self, config, problem) -> Mapping[str, object]: ...

    def training_data(
        self,
        dataset,
        cost_table,
        *,
        row_ids: Sequence[str] | None = None,
        transform_id: str | None = None,
    ) -> SurrogateTrainingData: ...

    def ensure_fresh_enough(self, context, training_data: SurrogateTrainingData): ...

    def latest_trained_generation(
        self,
        context,
        training_data: SurrogateTrainingData,
    ) -> int | None: ...

    def has_trained_state(
        self,
        context,
        training_data: SurrogateTrainingData,
    ) -> bool: ...

    def start_training(self, context, training_data: SurrogateTrainingData): ...

    def finish_training(self, context): ...


@dataclass(frozen=True, slots=True)
class SurrogateSelectionFreshness:
    """Pure generation-local readiness for deterministic selection."""

    ready: bool
    action: str
    latest_completed_generation_index: int | None
    lag: int | None
    max_lag: int
    error: str = ""

    def diagnostics(self) -> Mapping[str, object]:
        return MappingProxyType(
            {
                "surrogate_training_gate": self.action,
                "surrogate_training_pending_generation": None,
                "surrogate_training_latest_generation": (
                    self.latest_completed_generation_index
                ),
                "surrogate_training_lag": self.lag,
                "surrogate_training_max_lag": self.max_lag,
                "surrogate_training_gate_error": self.error,
            }
        )


def assess_surrogate_selection_freshness(
    component: DeterministicSurrogateComponent,
    context,
    training_data: SurrogateTrainingData,
) -> SurrogateSelectionFreshness:
    """Inspect state age without waiting for or starting training."""

    if not isinstance(component, DeterministicSurrogateComponent):
        raise TypeError("freshness requires a DeterministicSurrogateComponent")
    if not isinstance(training_data, SurrogateTrainingData):
        raise TypeError("freshness requires explicit SurrogateTrainingData")
    max_lag = max(0, int(context.config.OPTIMIZE_SURROGATE_MAX_TRAINING_LAG))
    try:
        latest = component.latest_trained_generation(context, training_data)
    except SurrogateContractError:
        raise
    except Exception as exc:  # noqa: BLE001 - derived selection falls back to real.
        return SurrogateSelectionFreshness(
            ready=False,
            action="failed",
            latest_completed_generation_index=None,
            lag=None,
            max_lag=max_lag,
            error=f"{exc.__class__.__name__}: {exc}"[:512],
        )
    if latest is None:
        return SurrogateSelectionFreshness(
            ready=False,
            action="skipped_no_data" if training_data.sample_count < 1 else "unavailable",
            latest_completed_generation_index=None,
            lag=None,
            max_lag=max_lag,
        )
    lag = int(context.generation_index) - int(latest)
    if lag < 0:
        return SurrogateSelectionFreshness(
            ready=False,
            action="failed",
            latest_completed_generation_index=int(latest),
            lag=lag,
            max_lag=max_lag,
            error="surrogate state generation is ahead of current generation",
        )
    return SurrogateSelectionFreshness(
        ready=lag <= max_lag,
        action="fresh" if lag <= max_lag else "stale",
        latest_completed_generation_index=int(latest),
        lag=lag,
        max_lag=max_lag,
    )


class TrainingHandleState(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    CANCELLING = "cancelling"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"
    CLOSED = "closed"


class TrainingCancelledError(RuntimeError):
    """Raised repeatedly when an explicit surrogate fit was cancelled."""


class TrainingHandle:
    """One owner-thread fit lifecycle with cached terminal semantics."""

    def __init__(
        self,
        runner: Callable[[threading.Event], object],
        *,
        session=None,
        snapshot=None,
        owned_cleanup: Callable[[], None] | None = None,
    ) -> None:
        if not callable(runner):
            raise TypeError("training handle runner must be callable")
        self._runner: Callable[[threading.Event], object] | None = runner
        self._session = session
        self._snapshot = snapshot
        self._owned_cleanup = owned_cleanup
        self._cancel_event = threading.Event()
        self._condition = threading.Condition(threading.RLock())
        self._state = TrainingHandleState.CREATED
        self._terminal_state: TrainingHandleState | None = None
        self._result: object | None = None
        self._failure: BaseException | None = None
        self._owner: threading.Thread | None = None
        self._released = False
        if session is not None:
            session._register_generation_handle(  # noqa: SLF001
                snapshot,
                self,
                boundary_policy="wait",
            )

    @property
    def state(self) -> TrainingHandleState:
        with self._condition:
            return self._state

    @property
    def terminal_state(self) -> TrainingHandleState | None:
        with self._condition:
            return self._terminal_state

    @property
    def owner_alive(self) -> bool:
        with self._condition:
            return bool(self._owner is not None and self._owner.is_alive())

    def start(self) -> TrainingHandle:
        with self._condition:
            if self._state in {TrainingHandleState.RUNNING, TrainingHandleState.CANCELLING}:
                return self
            if self._state == TrainingHandleState.CREATED:
                self._state = TrainingHandleState.RUNNING
                owner = threading.Thread(
                    target=self._run,
                    name=f"yadof-surrogate-fit-{id(self):x}",
                    daemon=False,
                )
                self._owner = owner
                owner.start()
                return self
            if self._state == TrainingHandleState.COMPLETED:
                return self
            raise RuntimeError(f"cannot start training handle in state {self._state.value}")

    def wait(self, timeout: float | None = None):
        deadline = None if timeout is None else time.monotonic() + max(0.0, float(timeout))
        with self._condition:
            while self._terminal_state is None:
                if deadline is None:
                    self._condition.wait()
                    continue
                remaining = deadline - time.monotonic()
                if remaining <= 0.0:
                    raise TimeoutError("surrogate fit did not finish before wait timeout")
                self._condition.wait(remaining)
            failure = self._failure
            result = self._result
        if failure is not None:
            raise failure
        return result

    def cancel(self) -> bool:
        with self._condition:
            if self._terminal_state is not None or self._state == TrainingHandleState.CLOSED:
                return False
            if self._state == TrainingHandleState.CREATED:
                failure = TrainingCancelledError("surrogate fit cancelled before start")
                self._failure = failure
                self._terminal_state = TrainingHandleState.CANCELLED
                self._state = TrainingHandleState.CANCELLED
                self._runner = None
                self._condition.notify_all()
                return True
            if self._state == TrainingHandleState.RUNNING:
                self._state = TrainingHandleState.CANCELLING
                self._cancel_event.set()
                return True
            return False

    def finish(self):
        """Wait normally, then release the generation lease without cancelling."""

        try:
            return self.wait()
        finally:
            self._release()

    def close(self) -> None:
        with self._condition:
            state = self._state
        if state == TrainingHandleState.CREATED:
            self.cancel()
        elif state in {TrainingHandleState.RUNNING, TrainingHandleState.CANCELLING}:
            self.cancel()
        try:
            self.wait()
        except TrainingCancelledError:
            pass
        finally:
            self._release()

    def __enter__(self) -> TrainingHandle:
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if exc_type is None:
            self.finish()
        else:
            try:
                self.close()
            except BaseException:
                pass
        return False

    def _run(self) -> None:
        try:
            runner = self._runner
            if runner is None:
                raise TrainingCancelledError("surrogate fit has no runnable input")
            result = runner(self._cancel_event)
        except TrainingCancelledError as exc:
            with self._condition:
                self._failure = exc
                self._terminal_state = TrainingHandleState.CANCELLED
                self._state = TrainingHandleState.CANCELLED
                self._runner = None
                self._condition.notify_all()
        except BaseException as exc:
            with self._condition:
                self._failure = exc
                self._terminal_state = TrainingHandleState.FAILED
                self._state = TrainingHandleState.FAILED
                self._runner = None
                self._condition.notify_all()
        else:
            with self._condition:
                self._result = result
                self._terminal_state = TrainingHandleState.COMPLETED
                self._state = TrainingHandleState.COMPLETED
                self._runner = None
                self._condition.notify_all()

    def _release(self) -> None:
        with self._condition:
            if self._released:
                return
            self._released = True
            session = self._session
            cleanup = self._owned_cleanup
            self._session = None
            self._snapshot = None
            self._owned_cleanup = None
            self._owner = None
            self._runner = None
            self._state = TrainingHandleState.CLOSED
        if session is not None:
            session._unregister_generation_handle(self)  # noqa: SLF001
        if cleanup is not None:
            cleanup()


def _validate_numeric_targets(samples: Sequence[StructuredRawDataSample]) -> None:
    for sample in samples:
        for item in sample.items:
            key = resolve_main_array_key(item.payload)
            value = item.payload[key]
            if np.ma.isMaskedArray(value):
                raise ValueError(f"surrogate target {(item.filename, key)!r} cannot be masked")
            array = np.asarray(value)
            if (
                array.dtype.hasobject
                or array.dtype.fields is not None
                or np.issubdtype(array.dtype, np.complexfloating)
                or not np.issubdtype(array.dtype, np.number)
            ):
                raise ValueError(f"surrogate target {(item.filename, key)!r} must be real numeric")
            if not np.all(np.isfinite(array)):
                raise ValueError(
                    f"surrogate target {(item.filename, key)!r} contains non-finite values"
                )


def _training_content_digest(
    parameter_names: Sequence[str],
    variables: Sequence[Sequence[float]],
    samples: Sequence[StructuredRawDataSample],
    statuses: Sequence[str],
    mask: Sequence[bool],
    schema_signature: str,
) -> str:
    digest = hashlib.sha256(_CONTENT_DOMAIN)
    _update_json(digest, {"parameter_names": list(parameter_names), "schema": schema_signature})
    matrix = np.asarray(variables, dtype="<f8")
    if matrix.size == 0:
        matrix = np.zeros((len(variables), len(parameter_names)), dtype="<f8")
    matrix = np.ascontiguousarray(matrix, dtype="<f8")
    _update_json(digest, {"shape": list(matrix.shape), "statuses": list(statuses), "mask": list(mask)})
    digest.update(matrix.tobytes(order="C"))
    for sample in samples:
        for item in sample.items:
            key = resolve_main_array_key(item.payload)
            array = np.asarray(item.payload[key])
            dtype = array.dtype.newbyteorder("<")
            canonical = np.ascontiguousarray(array.astype(dtype, copy=False))
            _update_json(
                digest,
                {
                    "selector": [item.filename, key],
                    "dtype": dtype.str,
                    "shape": list(canonical.shape),
                },
            )
            digest.update(canonical.tobytes(order="C"))
    return digest.hexdigest()


def _training_provenance_digest(
    row_ids: Sequence[str],
    evidence_ids: Sequence[str],
    statuses: Sequence[str],
    mask: Sequence[bool],
    lineage: Sequence[Sequence[Mapping[str, object]]],
    metadata: Sequence[Mapping[str, object]],
    transform_id: str | None,
) -> str:
    digest = hashlib.sha256(_PROVENANCE_DOMAIN)
    _update_json(
        digest,
        {
            "row_ids": list(row_ids),
            "evidence_ids": list(evidence_ids),
            "statuses": list(statuses),
            "valid_mask": list(mask),
            "lineage": [[_thaw_json(item) for item in row] for row in lineage],
            "record_metadata": [_thaw_json(row) for row in metadata],
            "transform_id": transform_id,
        },
    )
    return digest.hexdigest()


def _aligned_strings(values, count, *, default, label: str) -> tuple[str, ...]:
    selected = (
        tuple(default(index) for index in range(count))
        if not values
        else tuple(str(value).strip() for value in values)
    )
    if len(selected) != count:
        raise ValueError(f"{label} must align with data rows")
    if any(not value for value in selected):
        raise ValueError(f"{label} must be non-empty")
    return selected


def _require_materialized(
    value: object,
    label: str,
    *,
    allow_array: bool = False,
) -> None:
    if callable(value) or isinstance(value, Iterator):
        raise TypeError(f"surrogate training {label} must be materialized")
    if allow_array and isinstance(value, np.ndarray):
        return
    if isinstance(value, (str, bytes)) or not isinstance(value, MaterializedSequence):
        raise TypeError(f"surrogate training {label} must be a materialized sequence")


def _aligned_lineage(values, count) -> tuple[tuple[Mapping[str, object], ...], ...]:
    selected = tuple(() for _ in range(count)) if not values else tuple(values)
    if len(selected) != count:
        raise ValueError("training lineage must align with data rows")
    return tuple(
        tuple(_freeze_json_mapping(item) for item in row)
        for row in selected
    )


def _aligned_metadata(values, count) -> tuple[Mapping[str, object], ...]:
    selected = tuple({} for _ in range(count)) if not values else tuple(values)
    if len(selected) != count:
        raise ValueError("training record metadata must align with data rows")
    return tuple(_freeze_json_mapping(item) for item in selected)


def _freeze_json_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError("surrogate metadata must be a mapping")
    normalized = json.loads(
        json.dumps(
            _thaw_json(value),
            allow_nan=False,
            sort_keys=True,
            ensure_ascii=True,
        )
    )
    return MappingProxyType(
        {str(key): _freeze_json_value(item) for key, item in normalized.items()}
    )


def _freeze_json_value(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze_json_value(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(_freeze_json_value(item) for item in value)
    return value


def _thaw_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _hash_json(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _update_json(digest, value: object) -> None:
    digest.update(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
            ensure_ascii=True,
        ).encode("utf-8")
    )
    digest.update(b"\0")


def _sha256(value: object, label: str) -> str:
    selected = str(value).lower()
    if len(selected) != 64 or any(character not in "0123456789abcdef" for character in selected):
        raise ValueError(f"{label} must be a SHA-256 hex digest")
    return selected


__all__ = [
    "assess_surrogate_selection_freshness",
    "DeterministicPredictionProvider",
    "DeterministicSurrogateComponent",
    "SurrogatePrediction",
    "SurrogateContractError",
    "SurrogateSelectionFreshness",
    "SurrogateTrainingData",
    "TrainingCancelledError",
    "TrainingHandle",
    "TrainingHandleState",
    "materialize_training_data",
]
