"""Identity-preserving evidence datasets and task-scoped cost tables."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import hashlib
import json
import math
from types import MappingProxyType
from typing import Callable, Mapping, Sequence

import numpy as np

from ..config import load_config
from ..job_template import api as job_template_api
from ..job_template.rawdata_contract import NamedRawDataItem
from ..task_snapshot import GenerationTaskSnapshot, create_generation_snapshot
from ..workspace import WorkspaceContext, resolve_workspace
from .paths import WorkspaceLike, recorded_data_paths
from .rawdata import RawDataSource, own_rawdata_source, reservation_bytes
from .segment_store import (
    SegmentReference,
    discover_catalog,
    load_reference_rawdata,
)
from .utils import json_ready


Progress = Callable[[int, int, str], None]
MAX_DIAGNOSTIC_CHARS = 4096


class EvidenceState(StrEnum):
    """Publication/materialization state of one evidence row."""

    PENDING = "pending"
    COMMITTED = "committed"
    FAILED = "failed"
    DERIVED = "derived"


class InterpretationStatus(StrEnum):
    """Task-scoped current-cost status for one evidence row."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"
    MISSING = "missing"


@dataclass(frozen=True, slots=True)
class EvidenceLineage:
    """One deterministic, JSON-safe derivation step from a parent row."""

    parent_row_id: str
    operation: str
    ordinal: int
    parameters: Mapping[str, object]
    content_digest: str

    def __post_init__(self) -> None:
        parent = str(self.parent_row_id).strip()
        operation = str(self.operation).strip()
        ordinal = int(self.ordinal)
        digest = str(self.content_digest).lower()
        if not parent:
            raise ValueError("lineage parent_row_id must be non-empty")
        if not operation:
            raise ValueError("lineage operation must be non-empty")
        if ordinal < 0:
            raise ValueError("lineage ordinal must be non-negative")
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError("lineage content_digest must be a SHA-256 hex digest")
        clean_parameters = _json_mapping(self.parameters, label="lineage parameters")
        object.__setattr__(self, "parent_row_id", parent)
        object.__setattr__(self, "operation", operation)
        object.__setattr__(self, "ordinal", ordinal)
        object.__setattr__(self, "parameters", _freeze_mapping(clean_parameters))
        object.__setattr__(self, "content_digest", digest)

    def as_dict(self) -> dict[str, object]:
        return {
            "parent_row_id": self.parent_row_id,
            "operation": self.operation,
            "ordinal": self.ordinal,
            "parameters": _thaw_json(self.parameters),
            "content_digest": self.content_digest,
        }


@dataclass(frozen=True, slots=True)
class RawDataHandle:
    """Lazy rawData loader; each call returns newly owned candidate arrays."""

    filenames: tuple[str, ...]
    estimated_bytes: int
    source: str
    _loader: Callable[[], tuple[NamedRawDataItem, ...]] = field(
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        names = tuple(str(name) for name in self.filenames)
        if len(set(name.casefold() for name in names)) != len(names):
            raise ValueError("rawData handle filenames must be unique")
        if int(self.estimated_bytes) < 0:
            raise ValueError("rawData handle estimated_bytes must be non-negative")
        if not callable(self._loader):
            raise TypeError("rawData handle loader must be callable")
        object.__setattr__(self, "filenames", names)
        object.__setattr__(self, "estimated_bytes", int(self.estimated_bytes))
        object.__setattr__(self, "source", str(self.source))

    def load(self) -> tuple[NamedRawDataItem, ...]:
        items = tuple(self._loader())
        loaded_names = tuple(item.filename for item in items)
        if loaded_names != self.filenames:
            raise ValueError(
                "rawData handle loader changed filenames/order: "
                f"expected {self.filenames!r}, got {loaded_names!r}"
            )
        return items


@dataclass(frozen=True, slots=True)
class _InterpretationHint:
    status: str
    interpretation_fingerprint: str
    normalized_variables: tuple[float, ...] | None
    costs: tuple[float, ...] | None
    diagnostics: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class EvidenceRow:
    """One original or explicitly derived evidence row with stable identity."""

    row_id: str
    evidence_id: str
    job_name: str
    execution_status: str
    evidence_state: EvidenceState
    design_key: str | None
    raw_variables: tuple[float, ...] | None
    record: Mapping[str, object]
    parent_row_id: str | None = None
    lineage: tuple[EvidenceLineage, ...] = ()
    diagnostics: Mapping[str, object] = field(default_factory=dict)
    _rawdata_handle: RawDataHandle | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    _interpretation_hint: _InterpretationHint | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        row_id = str(self.row_id).strip()
        evidence_id = str(self.evidence_id).strip()
        if not row_id or not evidence_id:
            raise ValueError("row_id and evidence_id must be non-empty")
        state = EvidenceState(self.evidence_state)
        lineage = tuple(self.lineage)
        parent = None if self.parent_row_id is None else str(self.parent_row_id).strip()
        if state == EvidenceState.DERIVED:
            if not lineage or not parent:
                raise ValueError("derived evidence requires parent identity and lineage")
            if lineage[-1].parent_row_id != parent:
                raise ValueError("derived parent identity must match the final lineage step")
        elif row_id != evidence_id or lineage or parent is not None:
            raise ValueError(
                "original evidence row_id must equal its durable evidence_id"
            )
        raw_variables = (
            None
            if self.raw_variables is None
            else tuple(float(value) for value in self.raw_variables)
        )
        object.__setattr__(self, "row_id", row_id)
        object.__setattr__(self, "evidence_id", evidence_id)
        object.__setattr__(self, "job_name", str(self.job_name))
        object.__setattr__(self, "execution_status", str(self.execution_status))
        object.__setattr__(self, "evidence_state", state)
        object.__setattr__(
            self,
            "design_key",
            None if self.design_key is None else str(self.design_key),
        )
        object.__setattr__(self, "raw_variables", raw_variables)
        object.__setattr__(self, "record", _freeze_mapping(_json_mapping(self.record, label="evidence record")))
        object.__setattr__(self, "parent_row_id", parent)
        object.__setattr__(self, "lineage", lineage)
        object.__setattr__(
            self,
            "diagnostics",
            _freeze_mapping(_json_mapping(self.diagnostics, label="evidence diagnostics")),
        )

    @property
    def candidate_id(self) -> str:
        """Return the root durable candidate identity."""

        return self.evidence_id

    @property
    def is_original(self) -> bool:
        return self.row_id == self.evidence_id and not self.lineage

    @property
    def is_durable(self) -> bool:
        return self.is_original and self.evidence_state == EvidenceState.COMMITTED

    @property
    def has_rawdata(self) -> bool:
        return self._rawdata_handle is not None

    @property
    def rawdata_filenames(self) -> tuple[str, ...]:
        handle = self._rawdata_handle
        return () if handle is None else handle.filenames

    @property
    def rawdata_estimated_bytes(self) -> int:
        handle = self._rawdata_handle
        return 0 if handle is None else handle.estimated_bytes

    def load_rawdata(self) -> tuple[NamedRawDataItem, ...]:
        handle = self._rawdata_handle
        if handle is None:
            raise RuntimeError(
                f"rawData is unavailable for evidence row {self.row_id} "
                f"in state {self.evidence_state.value}"
            )
        return handle.load()


@dataclass(frozen=True, slots=True)
class EvidenceDataset:
    """Immutable identity-indexed view over evidence metadata and lazy payloads."""

    parameter_names: tuple[str, ...]
    rows: tuple[EvidenceRow, ...]
    diagnostics: tuple[Mapping[str, object], ...] = ()
    source: str = "durable"

    def __post_init__(self) -> None:
        names = tuple(str(name) for name in self.parameter_names)
        rows = tuple(self.rows)
        row_ids = tuple(row.row_id for row in rows)
        if len(set(row_ids)) != len(row_ids):
            raise ValueError("evidence dataset contains duplicate row identities")
        diagnostics = tuple(
            _freeze_mapping(_json_mapping(item, label="dataset diagnostic"))
            for item in self.diagnostics
        )
        source = str(self.source).strip()
        if not source:
            raise ValueError("evidence dataset source must be non-empty")
        object.__setattr__(self, "parameter_names", names)
        object.__setattr__(self, "rows", rows)
        object.__setattr__(self, "diagnostics", diagnostics)
        object.__setattr__(self, "source", source)

    def __len__(self) -> int:
        return len(self.rows)

    def __iter__(self):
        return iter(self.rows)

    def by_id(self, row_id: str) -> EvidenceRow:
        selected = str(row_id)
        for row in self.rows:
            if row.row_id == selected:
                return row
        raise KeyError(selected)

    def select(self, row_ids: Sequence[str]) -> EvidenceDataset:
        selected_ids = tuple(str(value) for value in row_ids)
        if len(set(selected_ids)) != len(selected_ids):
            raise ValueError("evidence selection cannot repeat row identities")
        lookup = {row.row_id: row for row in self.rows}
        missing = tuple(row_id for row_id in selected_ids if row_id not in lookup)
        if missing:
            raise KeyError(", ".join(missing))
        return EvidenceDataset(
            self.parameter_names,
            tuple(lookup[row_id] for row_id in selected_ids),
            self.diagnostics,
            self.source,
        )

    def where(self, predicate: Callable[[EvidenceRow], bool]) -> EvidenceDataset:
        if not callable(predicate):
            raise TypeError("evidence predicate must be callable")
        return EvidenceDataset(
            self.parameter_names,
            tuple(row for row in self.rows if bool(predicate(row))),
            self.diagnostics,
            self.source,
        )

    def copy(self) -> EvidenceDataset:
        return EvidenceDataset(
            self.parameter_names,
            tuple(self.rows),
            tuple(self.diagnostics),
            self.source,
        )

    def join_costs(self, table: CostTable) -> tuple[EvidenceCostRow, ...]:
        lookup = {row.row_id: row for row in table.rows}
        missing = tuple(row.row_id for row in self.rows if row.row_id not in lookup)
        if missing:
            raise KeyError("cost table is missing row(s): " + ", ".join(missing))
        return tuple(EvidenceCostRow(row, lookup[row.row_id]) for row in self.rows)


@dataclass(frozen=True, slots=True)
class CostRow:
    """One task/schema-bound interpretation of an evidence row."""

    interpretation_id: str
    row_id: str
    evidence_id: str
    job_name: str
    status: InterpretationStatus
    interpretation_fingerprint: str
    objective_schema_id: str
    objective_width: int
    normalized_variables: tuple[float, ...] | None
    costs: tuple[float, ...] | None
    diagnostics: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        status = InterpretationStatus(self.status)
        width = int(self.objective_width)
        if width < 1:
            raise ValueError("objective_width must be positive")
        normalized = (
            None
            if self.normalized_variables is None
            else tuple(float(value) for value in self.normalized_variables)
        )
        costs = None if self.costs is None else tuple(float(value) for value in self.costs)
        if status == InterpretationStatus.SUCCEEDED:
            if normalized is None:
                raise ValueError("successful cost row requires normalized variables")
            if costs is None or len(costs) != width:
                raise ValueError("successful cost row has the wrong objective width")
            if any(not math.isfinite(value) for value in (*normalized, *costs)):
                raise ValueError("successful cost row must contain finite values")
        elif costs is not None:
            raise ValueError("only successful cost rows may contain costs")
        object.__setattr__(self, "interpretation_id", str(self.interpretation_id))
        object.__setattr__(self, "row_id", str(self.row_id))
        object.__setattr__(self, "evidence_id", str(self.evidence_id))
        object.__setattr__(self, "job_name", str(self.job_name))
        object.__setattr__(self, "status", status)
        object.__setattr__(
            self,
            "interpretation_fingerprint",
            str(self.interpretation_fingerprint),
        )
        object.__setattr__(self, "objective_schema_id", str(self.objective_schema_id))
        object.__setattr__(self, "objective_width", width)
        object.__setattr__(self, "normalized_variables", normalized)
        object.__setattr__(self, "costs", costs)
        object.__setattr__(
            self,
            "diagnostics",
            _freeze_mapping(_json_mapping(self.diagnostics, label="cost diagnostics")),
        )

    @property
    def valid(self) -> bool:
        return self.status == InterpretationStatus.SUCCEEDED


@dataclass(frozen=True, slots=True)
class CostTable:
    """Immutable task/schema-bound cost interpretations keyed by row identity."""

    objective_names: tuple[str, ...]
    objective_schema_id: str
    interpretation_fingerprint: str
    rows: tuple[CostRow, ...]
    diagnostics: tuple[Mapping[str, object], ...] = ()

    def __post_init__(self) -> None:
        names = tuple(str(name) for name in self.objective_names)
        if not names:
            raise ValueError("cost table requires at least one objective")
        rows = tuple(self.rows)
        if len({row.row_id for row in rows}) != len(rows):
            raise ValueError("cost table contains duplicate row identities")
        schema = str(self.objective_schema_id)
        fingerprint = str(self.interpretation_fingerprint)
        for row in rows:
            if row.objective_schema_id != schema or row.objective_width != len(names):
                raise ValueError("cost row objective schema does not match its table")
            if row.interpretation_fingerprint != fingerprint:
                raise ValueError("cost row task fingerprint does not match its table")
        object.__setattr__(self, "objective_names", names)
        object.__setattr__(self, "objective_schema_id", schema)
        object.__setattr__(self, "interpretation_fingerprint", fingerprint)
        object.__setattr__(self, "rows", rows)
        object.__setattr__(
            self,
            "diagnostics",
            tuple(
                _freeze_mapping(_json_mapping(item, label="cost table diagnostic"))
                for item in self.diagnostics
            ),
        )

    @property
    def objective_width(self) -> int:
        return len(self.objective_names)

    @property
    def statuses(self) -> tuple[InterpretationStatus, ...]:
        return tuple(row.status for row in self.rows)

    @property
    def valid_mask(self) -> tuple[bool, ...]:
        return tuple(row.valid for row in self.rows)

    def by_id(self, row_id: str) -> CostRow:
        selected = str(row_id)
        for row in self.rows:
            if row.row_id == selected:
                return row
        raise KeyError(selected)

    def select(self, row_ids: Sequence[str]) -> CostTable:
        selected_ids = tuple(str(value) for value in row_ids)
        if len(set(selected_ids)) != len(selected_ids):
            raise ValueError("cost selection cannot repeat row identities")
        lookup = {row.row_id: row for row in self.rows}
        missing = tuple(row_id for row_id in selected_ids if row_id not in lookup)
        if missing:
            raise KeyError(", ".join(missing))
        return CostTable(
            self.objective_names,
            self.objective_schema_id,
            self.interpretation_fingerprint,
            tuple(lookup[row_id] for row_id in selected_ids),
            self.diagnostics,
        )

    def successful(self) -> CostTable:
        return CostTable(
            self.objective_names,
            self.objective_schema_id,
            self.interpretation_fingerprint,
            tuple(row for row in self.rows if row.valid),
            self.diagnostics,
        )

    def to_optimizer_costs(
        self,
        row_ids: Sequence[str] | None = None,
    ) -> tuple[tuple[float, ...], ...]:
        selected = self if row_ids is None else self.select(row_ids)
        invalid = tuple(float("inf") for _ in self.objective_names)
        return tuple(row.costs if row.costs is not None else invalid for row in selected.rows)


@dataclass(frozen=True, slots=True)
class EvidenceCostRow:
    """Identity-checked join of one evidence row and one cost row."""

    evidence: EvidenceRow
    cost: CostRow

    def __post_init__(self) -> None:
        if self.evidence.row_id != self.cost.row_id:
            raise ValueError("evidence/cost row identity mismatch")
        if self.evidence.evidence_id != self.cost.evidence_id:
            raise ValueError("evidence/cost root identity mismatch")


@dataclass(frozen=True, slots=True)
class _LiveEvidenceInput:
    candidate_id: str
    record: Mapping[str, object]
    evidence_state: str
    reference: SegmentReference | None
    interpretation_state: str
    normalized_variables: tuple[float, ...] | None
    costs: tuple[float, ...] | None
    interpretation_fingerprint: str | None
    interpretation_diagnostics: Mapping[str, object] | None


def get_evidence_dataset(workspace: WorkspaceLike) -> EvidenceDataset:
    """Freeze one durable catalog view without decoding candidate rawData."""

    context = resolve_workspace(workspace)
    storage = recorded_data_paths(context)
    catalog = discover_catalog(storage)
    parameter_names = tuple(job_template_api.get_parameter_names(context))
    rows = tuple(
        _row_from_record(
            parameter_names,
            candidate_id=reference.candidate_id,
            record=reference.record,
            evidence_state=EvidenceState.COMMITTED,
            reference=reference,
        )
        for reference in catalog.references
    )
    return EvidenceDataset(
        parameter_names,
        rows,
        tuple(catalog.diagnostics),
        "durable",
    )


def get_cost_table(
    workspace: WorkspaceLike,
    *,
    dataset: EvidenceDataset | None = None,
    progress: Progress | None = None,
) -> CostTable:
    """Interpret a durable dataset under one temporary coherent task snapshot."""

    context = resolve_workspace(workspace)
    selected = get_evidence_dataset(context) if dataset is None else dataset
    snapshot = create_generation_snapshot(load_config(context))
    try:
        return calculate_cost_table(selected, snapshot, progress=progress)
    finally:
        snapshot.close()


def calculate_cost_table(
    dataset: EvidenceDataset,
    snapshot: GenerationTaskSnapshot,
    *,
    progress: Progress | None = None,
) -> CostTable:
    """Interpret rows in stable order, loading at most one rawData row at a time."""

    if tuple(dataset.parameter_names) != tuple(snapshot.parameter_names):
        raise ValueError(
            "evidence dataset parameter schema does not match the task snapshot"
        )
    objective_names = tuple(snapshot.objective_names)
    schema_id = _objective_schema_id(objective_names)
    total = len(dataset.rows)
    if progress is not None:
        progress(0, total, "calculating cost table")
    rows: list[CostRow] = []
    interpreter_context = None
    interpreter = None
    try:
        for index, evidence in enumerate(dataset.rows, start=1):
            cached = _hint_cost_row(evidence, snapshot, schema_id, objective_names)
            if cached is not None:
                rows.append(cached)
            elif evidence.execution_status not in {"completed", "derived"}:
                rows.append(
                    _cost_row(
                        evidence,
                        snapshot,
                        schema_id,
                        objective_names,
                        InterpretationStatus.NOT_APPLICABLE,
                        diagnostics={
                            "stage": "execution",
                            "execution_status": evidence.execution_status,
                        },
                    )
                )
            elif evidence.evidence_state not in {
                EvidenceState.COMMITTED,
                EvidenceState.DERIVED,
            }:
                rows.append(
                    _cost_row(
                        evidence,
                        snapshot,
                        schema_id,
                        objective_names,
                        InterpretationStatus.MISSING,
                        diagnostics={
                            "stage": "evidence",
                            "evidence_state": evidence.evidence_state.value,
                        },
                    )
                )
            elif evidence.raw_variables is None:
                rows.append(
                    _cost_row(
                        evidence,
                        snapshot,
                        schema_id,
                        objective_names,
                        InterpretationStatus.FAILED,
                        diagnostics={
                            "stage": "raw_variables",
                            "error_type": "MissingRawVariables",
                            "error_message": "complete ordered raw variables are unavailable",
                        },
                    )
                )
            elif not evidence.has_rawdata:
                rows.append(
                    _cost_row(
                        evidence,
                        snapshot,
                        schema_id,
                        objective_names,
                        InterpretationStatus.MISSING,
                        diagnostics={
                            "stage": "rawdata",
                            "error_type": "MissingRawData",
                            "error_message": "rawData evidence is unavailable",
                        },
                    )
                )
            else:
                try:
                    normalized = tuple(
                        float(value)
                        for value in job_template_api.normalize_variables(
                            snapshot.config.workspace,
                            evidence.raw_variables,
                        )
                    )
                    if any(not math.isfinite(value) for value in normalized):
                        raise ValueError("normalized variables must be finite")
                except Exception as exc:  # noqa: BLE001 - typed row isolation.
                    rows.append(
                        _failed_cost_row(
                            evidence,
                            snapshot,
                            schema_id,
                            objective_names,
                            "normalization",
                            exc,
                        )
                    )
                else:
                    try:
                        items = evidence.load_rawdata()
                    except Exception as exc:  # noqa: BLE001 - corrupt row isolation.
                        rows.append(
                            _failed_cost_row(
                                evidence,
                                snapshot,
                                schema_id,
                                objective_names,
                                "rawdata_load",
                                exc,
                                normalized=normalized,
                            )
                        )
                    else:
                        try:
                            if interpreter is None:
                                candidate_context = (
                                    job_template_api.task_cost_interpreter(
                                        snapshot.config.workspace
                                    )
                                )
                                candidate_interpreter = candidate_context.__enter__()
                                interpreter_context = candidate_context
                                interpreter = candidate_interpreter
                            calculated = interpreter.calculate_costs(
                                (tuple(item.payload for item in items),),
                                (evidence.raw_variables,),
                            )[0]
                            successful = _cost_row(
                                evidence,
                                snapshot,
                                schema_id,
                                objective_names,
                                InterpretationStatus.SUCCEEDED,
                                normalized=normalized,
                                costs=tuple(float(value) for value in calculated),
                                diagnostics={"stage": "cost_interpretation"},
                            )
                        except Exception as exc:  # noqa: BLE001 - typed failure row.
                            rows.append(
                                _failed_cost_row(
                                    evidence,
                                    snapshot,
                                    schema_id,
                                    objective_names,
                                    "cost_interpretation",
                                    exc,
                                    normalized=normalized,
                                )
                            )
                        else:
                            rows.append(successful)
                        finally:
                            del items
            if progress is not None:
                progress(index, total, "calculating cost table")
    finally:
        if interpreter_context is not None:
            interpreter_context.__exit__(None, None, None)
    return CostTable(
        objective_names,
        schema_id,
        snapshot.interpretation_fingerprint,
        tuple(rows),
        tuple(dataset.diagnostics),
    )


def derive_evidence_row(
    parent: EvidenceRow,
    *,
    operation: str,
    ordinal: int,
    rawdata_source: RawDataSource,
    parameters: Mapping[str, object] | None = None,
    job_name: str | None = None,
) -> EvidenceRow:
    """Materialize one transient rawData transform with deterministic lineage."""

    clean_operation = str(operation).strip()
    if not clean_operation:
        raise ValueError("derived operation must be non-empty")
    selected_ordinal = int(ordinal)
    if selected_ordinal < 0:
        raise ValueError("derived ordinal must be non-negative")
    clean_parameters = _json_mapping(parameters or {}, label="derived parameters")
    owned = own_rawdata_source(rawdata_source)
    if not owned:
        raise ValueError("derived evidence requires rawData")
    digest = _rawdata_semantic_digest(owned)
    lineage_step = EvidenceLineage(
        parent.row_id,
        clean_operation,
        selected_ordinal,
        clean_parameters,
        digest,
    )
    row_id = _hash_json(
        {
            "parent_row_id": parent.row_id,
            "operation": clean_operation,
            "ordinal": selected_ordinal,
            "parameters": clean_parameters,
            "content_digest": digest,
        }
    )
    handle = RawDataHandle(
        tuple(item.filename for item in owned),
        reservation_bytes(owned),
        f"derived:{row_id}",
        lambda items=owned: own_rawdata_source(items),
    )
    record = _thaw_json(parent.record)
    record.update(
        {
            "derived_row_id": row_id,
            "derived_from": parent.row_id,
            "derived_operation": clean_operation,
            "derived_ordinal": selected_ordinal,
            "derived_content_digest": digest,
        }
    )
    selected_name = (
        f"{parent.job_name}#{clean_operation}:{selected_ordinal}"
        if job_name is None
        else str(job_name)
    )
    return EvidenceRow(
        row_id=row_id,
        evidence_id=parent.evidence_id,
        job_name=selected_name,
        execution_status="derived",
        evidence_state=EvidenceState.DERIVED,
        design_key=parent.design_key,
        raw_variables=parent.raw_variables,
        record=record,
        parent_row_id=parent.row_id,
        lineage=(*parent.lineage, lineage_step),
        _rawdata_handle=handle,
    )


def _evidence_dataset_from_live(
    workspace: WorkspaceContext,
    inputs: Sequence[_LiveEvidenceInput],
    diagnostics: Sequence[Mapping[str, object]],
) -> EvidenceDataset:
    parameter_names = tuple(job_template_api.get_parameter_names(workspace))
    rows = tuple(
        _row_from_record(
            parameter_names,
            candidate_id=item.candidate_id,
            record=item.record,
            evidence_state=_evidence_state(item.evidence_state),
            reference=item.reference,
            interpretation_state=item.interpretation_state,
            normalized_variables=item.normalized_variables,
            costs=item.costs,
            interpretation_fingerprint=item.interpretation_fingerprint,
            interpretation_diagnostics=item.interpretation_diagnostics,
        )
        for item in inputs
    )
    return EvidenceDataset(parameter_names, rows, tuple(diagnostics), "campaign")


def _row_from_record(
    parameter_names: Sequence[str],
    *,
    candidate_id: str,
    record: Mapping[str, object],
    evidence_state: EvidenceState,
    reference: SegmentReference | None,
    interpretation_state: str = "uninterpreted",
    normalized_variables: Sequence[float] | None = None,
    costs: Sequence[float] | None = None,
    interpretation_fingerprint: str | None = None,
    interpretation_diagnostics: Mapping[str, object] | None = None,
) -> EvidenceRow:
    ready_record = json_ready(record)
    if not isinstance(ready_record, Mapping):
        raise TypeError("evidence record must remain a mapping after normalization")
    clean_record = _json_mapping(ready_record, label="evidence record")
    clean_record["candidate_id"] = str(candidate_id)
    raw_variables = _raw_variables(clean_record, parameter_names)
    design_key = _design_key(parameter_names, raw_variables)
    handle = None
    if evidence_state == EvidenceState.COMMITTED and reference is not None and reference.rawdata_members:
        handle = RawDataHandle(
            tuple(filename for filename, _member, _size in reference.rawdata_members),
            sum(size for _filename, _member, size in reference.rawdata_members),
            str(reference.segment_path),
            lambda selected=reference: load_reference_rawdata(selected),
        )
    hint = None
    selected_interpretation_state = str(interpretation_state)
    if (
        interpretation_fingerprint
        and selected_interpretation_state
        in {
            InterpretationStatus.SUCCEEDED.value,
            InterpretationStatus.FAILED.value,
            InterpretationStatus.NOT_APPLICABLE.value,
        }
    ):
        hint = _InterpretationHint(
            selected_interpretation_state,
            str(interpretation_fingerprint),
            (
                None
                if normalized_variables is None
                else tuple(float(value) for value in normalized_variables)
            ),
            None if costs is None else tuple(float(value) for value in costs),
            _freeze_mapping(
                _json_mapping(
                    interpretation_diagnostics or {},
                    label="interpretation diagnostics",
                )
            ),
        )
    return EvidenceRow(
        row_id=str(candidate_id),
        evidence_id=str(candidate_id),
        job_name=str(clean_record.get("job_name", "")),
        execution_status=str(clean_record.get("status", "")),
        evidence_state=evidence_state,
        design_key=design_key,
        raw_variables=raw_variables,
        record=clean_record,
        diagnostics=interpretation_diagnostics or {},
        _rawdata_handle=handle,
        _interpretation_hint=hint,
    )


def _hint_cost_row(
    evidence: EvidenceRow,
    snapshot: GenerationTaskSnapshot,
    schema_id: str,
    objective_names: Sequence[str],
) -> CostRow | None:
    hint = evidence._interpretation_hint
    if hint is None or hint.interpretation_fingerprint != snapshot.interpretation_fingerprint:
        return None
    status = InterpretationStatus(hint.status)
    costs = hint.costs
    normalized = hint.normalized_variables
    if status == InterpretationStatus.SUCCEEDED:
        if (
            costs is None
            or normalized is None
            or len(costs) != len(objective_names)
            or any(not math.isfinite(value) for value in (*normalized, *costs))
        ):
            return None
    return _cost_row(
        evidence,
        snapshot,
        schema_id,
        objective_names,
        status,
        normalized=normalized,
        costs=costs if status == InterpretationStatus.SUCCEEDED else None,
        diagnostics=hint.diagnostics,
    )


def _failed_cost_row(
    evidence: EvidenceRow,
    snapshot: GenerationTaskSnapshot,
    schema_id: str,
    objective_names: Sequence[str],
    stage: str,
    exc: BaseException,
    *,
    normalized: tuple[float, ...] | None = None,
) -> CostRow:
    return _cost_row(
        evidence,
        snapshot,
        schema_id,
        objective_names,
        InterpretationStatus.FAILED,
        normalized=normalized,
        diagnostics={
            "stage": str(stage),
            "error_type": type(exc).__name__,
            "error_message": str(exc)[:MAX_DIAGNOSTIC_CHARS],
        },
    )


def _cost_row(
    evidence: EvidenceRow,
    snapshot: GenerationTaskSnapshot,
    schema_id: str,
    objective_names: Sequence[str],
    status: InterpretationStatus,
    *,
    normalized: Sequence[float] | None = None,
    costs: Sequence[float] | None = None,
    diagnostics: Mapping[str, object] | None = None,
) -> CostRow:
    interpretation_id = _hash_json(
        {
            "row_id": evidence.row_id,
            "evidence_id": evidence.evidence_id,
            "interpretation_fingerprint": snapshot.interpretation_fingerprint,
            "objective_schema_id": schema_id,
        }
    )
    return CostRow(
        interpretation_id=interpretation_id,
        row_id=evidence.row_id,
        evidence_id=evidence.evidence_id,
        job_name=evidence.job_name,
        status=status,
        interpretation_fingerprint=snapshot.interpretation_fingerprint,
        objective_schema_id=schema_id,
        objective_width=len(objective_names),
        normalized_variables=(
            None if normalized is None else tuple(float(value) for value in normalized)
        ),
        costs=None if costs is None else tuple(float(value) for value in costs),
        diagnostics=diagnostics or {},
    )


def _raw_variables(
    record: Mapping[str, object], parameter_names: Sequence[str]
) -> tuple[float, ...] | None:
    values = record.get("raw_variables")
    if not isinstance(values, Mapping):
        return None
    try:
        return tuple(float(values[name]) for name in parameter_names)
    except (KeyError, TypeError, ValueError):
        return None


def _design_key(
    parameter_names: Sequence[str], raw_variables: Sequence[float] | None
) -> str | None:
    if raw_variables is None or any(not math.isfinite(float(value)) for value in raw_variables):
        return None
    return _hash_json(
        {
            "parameter_names": [str(name) for name in parameter_names],
            "physical_values": [float(value).hex() for value in raw_variables],
        }
    )


def _objective_schema_id(objective_names: Sequence[str]) -> str:
    names = tuple(str(name) for name in objective_names)
    if not names:
        raise ValueError("task snapshot must define at least one objective")
    return _hash_json({"objective_names": list(names), "objective_width": len(names)})


def _evidence_state(value: str | EvidenceState) -> EvidenceState:
    selected = str(value)
    if selected in {"recording_failed", "failed"}:
        return EvidenceState.FAILED
    return EvidenceState(selected)


def _rawdata_semantic_digest(items: Sequence[NamedRawDataItem]) -> str:
    digest = hashlib.sha256()
    _digest_part(digest, b"yadof-derived-rawdata-v1")
    for item in items:
        _digest_part(digest, item.filename.encode("utf-8"))
        for key in sorted(item.payload):
            _digest_part(digest, str(key).encode("utf-8"))
            value = item.payload[key]
            if isinstance(value, np.ndarray):
                array = np.ascontiguousarray(value)
                _digest_part(digest, array.dtype.str.encode("ascii"))
                _digest_part(
                    digest,
                    json.dumps(list(array.shape), separators=(",", ":")).encode("ascii"),
                )
                _digest_part(digest, memoryview(array).cast("B"))
            else:
                encoded = json.dumps(
                    _clean_json(value, label=f"rawData {item.filename} {key}"),
                    ensure_ascii=True,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                _digest_part(digest, encoded)
    return digest.hexdigest()


def _digest_part(digest, payload) -> None:
    size = len(payload)
    digest.update(int(size).to_bytes(8, "big", signed=False))
    digest.update(payload)


def _hash_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _json_mapping(value: Mapping[str, object], *, label: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    clean = {
        str(key): _clean_json(item, label=f"{label}.{key}")
        for key, item in value.items()
    }
    json.dumps(clean, allow_nan=False, sort_keys=True)
    return clean


def _clean_json(value: object, *, label: str) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): _clean_json(item, label=f"{label}.{key}")
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [_clean_json(item, label=label) for item in value]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{label} must not contain non-finite JSON values")
        return value
    raise TypeError(f"{label} contains unsupported JSON value {type(value).__name__}")


def _freeze_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(
        {str(key): _freeze_json(item) for key, item in value.items()}
    )


def _freeze_json(value: object) -> object:
    if isinstance(value, Mapping):
        return _freeze_mapping(value)
    if isinstance(value, (tuple, list)):
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_thaw_json(item) for item in value]
    return value


__all__ = [
    "CostRow",
    "CostTable",
    "EvidenceCostRow",
    "EvidenceDataset",
    "EvidenceLineage",
    "EvidenceRow",
    "EvidenceState",
    "InterpretationStatus",
    "RawDataHandle",
    "calculate_cost_table",
    "derive_evidence_row",
    "get_cost_table",
    "get_evidence_dataset",
]
