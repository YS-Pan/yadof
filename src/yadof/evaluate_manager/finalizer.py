"""Backend-neutral result validation, current cost, and reliable recording."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
import time
from typing import Callable
import uuid

from ..job_template import api as job_template_api
from ..recorded_data.rawdata import own_rawdata_source
from ..recorded_data.records import build_owned_envelope
from ..recorded_data.session import (
    CampaignSession,
    PublicationReceipt,
    RecordingError,
)
from ..task_snapshot import GenerationTaskSnapshot
from .types import JobResult


FinalizedConsumer = Callable[[int, JobResult], object]


@dataclass(slots=True)
class _PreparedResult:
    index: int
    result: JobResult
    receipt: PublicationReceipt
    completed_at: float


class ResultFinalizationCoordinator:
    """Publish bounded evidence groups before ordered cost interpretation."""

    def __init__(
        self,
        session: CampaignSession,
        snapshot: GenerationTaskSnapshot,
        *,
        expected_count: int | None = None,
        on_finalized: FinalizedConsumer | None = None,
    ) -> None:
        if expected_count is not None and int(expected_count) < 0:
            raise ValueError("expected_count must be non-negative")
        self._session = session
        self._snapshot = snapshot
        self._expected_count = (
            int(expected_count) if expected_count is not None else None
        )
        self._on_finalized = on_finalized
        self._pending: dict[int, _PreparedResult] = {}
        self._results: dict[int, JobResult] = {}
        self._next_index = 0
        self._group_sequence = 0
        self._coordinator_id = uuid.uuid4().hex[:12]
        self._group_count = 0
        self._group_bytes = 0
        self._closed = False
        self._failed = False
        self._interpreter_context = None
        self._interpreter = None
        config = snapshot.config
        self._group_count_limit = int(config.HISTORY_SEGMENT_MAX_CANDIDATES)
        self._group_bytes_limit = int(config.HISTORY_SEGMENT_TARGET_BYTES)

    def accept(
        self,
        index: int,
        result: JobResult,
        *,
        completed_at: float | None = None,
    ) -> None:
        """Own and admit one completion, flushing on existing count/byte targets."""

        self._ensure_active()
        position = int(index)
        if position < 0:
            raise ValueError("result index must be non-negative")
        if self._expected_count is not None and position >= self._expected_count:
            raise IndexError(
                f"result index {position} is outside expected population "
                f"of {self._expected_count}"
            )
        if position in self._pending or position in self._results:
            raise RecordingError(f"duplicate finalized population index: {position}")
        group_id = self._current_group_id()
        prepared = _prepare_result(
            self._session,
            self._snapshot,
            position,
            result,
            group_id=group_id,
            completed_at=(
                time.monotonic() if completed_at is None else float(completed_at)
            ),
        )
        self._pending[position] = prepared
        self._group_count += 1
        self._group_bytes += prepared.receipt.reservation_bytes
        should_flush = (
            self._group_count >= self._group_count_limit
            or self._group_bytes >= self._group_bytes_limit
        )
        try:
            if should_flush:
                self._session.flush_boundary()
                self._advance_group()
            self._drain_ready(wait=False)
        except BaseException:
            self._failed = True
            self.close()
            raise

    def finish(self) -> tuple[JobResult, ...]:
        """Commit the tail, finish ordered interpretations, and return all rows."""

        self._ensure_active()
        try:
            self._session.flush_boundary()
            self._advance_group()
            self._drain_ready(wait=True)
            expected = (
                self._expected_count
                if self._expected_count is not None
                else len(self._pending) + len(self._results)
            )
            missing = tuple(
                index for index in range(expected) if index not in self._results
            )
            if missing:
                raise RuntimeError(
                    "finalization coordinator is missing population indices: "
                    + ", ".join(str(index) for index in missing[:16])
                )
            if self._pending:
                raise RuntimeError("finalization coordinator retained unordered rows")
            return tuple(self._results[index] for index in range(expected))
        except BaseException:
            self._failed = True
            raise
        finally:
            self.close()

    def close(self) -> None:
        """Release the frozen interpreter without changing durable evidence."""

        if self._closed:
            return
        self._closed = True
        context = self._interpreter_context
        self._interpreter_context = None
        self._interpreter = None
        if context is not None:
            context.__exit__(None, None, None)

    def _ensure_active(self) -> None:
        if self._closed:
            raise RuntimeError("finalization coordinator is closed")
        if self._failed:
            raise RuntimeError("finalization coordinator has failed")

    def _current_group_id(self) -> str:
        return (
            f"{self._session.campaign_id}:"
            f"{self._snapshot.task_snapshot_id[:12]}:"
            f"{self._coordinator_id}:"
            f"{self._group_sequence:06d}"
        )

    def _advance_group(self) -> None:
        if self._group_count or self._group_bytes:
            self._group_sequence += 1
        self._group_count = 0
        self._group_bytes = 0

    def _drain_ready(self, *, wait: bool) -> None:
        while True:
            prepared = self._pending.get(self._next_index)
            if prepared is None:
                return
            if not wait and prepared.receipt.state == "pending":
                return
            prepared.receipt.wait_committed()
            finalized = self._interpret(prepared)
            del self._pending[self._next_index]
            self._results[self._next_index] = finalized
            if self._on_finalized is not None:
                self._on_finalized(self._next_index, finalized)
            self._next_index += 1

    def _cost_interpreter(self):
        if self._interpreter is None:
            context = job_template_api.task_cost_interpreter(
                self._snapshot.config.workspace
            )
            self._interpreter_context = context
            self._interpreter = context.__enter__()
        return self._interpreter

    def _interpret(self, prepared: _PreparedResult) -> JobResult:
        receipt = prepared.receipt
        result = prepared.result
        committed_at = receipt.committed_at_monotonic
        if committed_at is None:
            raise RecordingError(
                f"receipt reported committed without a timestamp: {receipt.job_name}"
            )
        metadata = dict(result.metadata)
        metadata.update(
            {
                "evidence_state": "committed",
                "publication_receipt_state": "committed",
                "publication_group_id": receipt.group_id,
                "evaluation_completion_to_commit_sec": max(
                    0.0, committed_at - prepared.completed_at
                ),
            }
        )
        if result.status != "done":
            interpreted_at = time.monotonic()
            latency = max(0.0, interpreted_at - committed_at)
            diagnostics = {
                "state": "not_applicable",
                "evidence_commit_to_interpretation_sec": latency,
            }
            self._session.record_interpretation(
                receipt,
                state="not_applicable",
                normalized=None,
                costs=None,
                interpretation_fingerprint=self._snapshot.interpretation_fingerprint,
                diagnostics=diagnostics,
            )
            metadata.update(
                {
                    "interpretation_state": "not_applicable",
                    "evidence_commit_to_interpretation_sec": latency,
                }
            )
            return replace(result, metadata=metadata, costs=None)

        interpretation_started = time.monotonic()
        try:
            evidence = self._session.committed_evidence(receipt)
            raw_variables = tuple(
                float(value) for value in result.unnormalized_variables
            )
            costs = self._cost_interpreter().calculate_costs(
                (tuple(item.payload for item in evidence),),
                (raw_variables,),
            )[0]
        except Exception as exc:  # One replayable interpretation becomes inf later.
            interpreted_at = time.monotonic()
            latency = max(0.0, interpreted_at - committed_at)
            duration = max(0.0, interpreted_at - interpretation_started)
            diagnostics = {
                "state": "failed",
                "failure_stage": "cost_interpretation",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "cost_interpretation_sec": duration,
                "evidence_commit_to_interpretation_sec": latency,
            }
            self._session.record_interpretation(
                receipt,
                state="failed",
                normalized=result.normalized_variables,
                costs=None,
                interpretation_fingerprint=self._snapshot.interpretation_fingerprint,
                diagnostics=diagnostics,
            )
            metadata.update(
                {
                    "status": "error",
                    "interpretation_state": "failed",
                    "failure_stage": "cost_interpretation",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "failed_at": _now_text(),
                    "cost_interpretation_sec": duration,
                    "evidence_commit_to_interpretation_sec": latency,
                }
            )
            return replace(result, status="error", metadata=metadata, costs=None)

        interpreted_at = time.monotonic()
        latency = max(0.0, interpreted_at - committed_at)
        duration = max(0.0, interpreted_at - interpretation_started)
        finalized_costs = tuple(float(value) for value in costs)
        diagnostics = {
            "state": "succeeded",
            "cost_interpretation_sec": duration,
            "evidence_commit_to_interpretation_sec": latency,
        }
        self._session.record_interpretation(
            receipt,
            state="succeeded",
            normalized=result.normalized_variables,
            costs=finalized_costs,
            interpretation_fingerprint=self._snapshot.interpretation_fingerprint,
            diagnostics=diagnostics,
        )
        metadata.update(
            {
                "interpretation_state": "succeeded",
                "cost_interpretation_sec": duration,
                "evidence_commit_to_interpretation_sec": latency,
            }
        )
        return replace(result, metadata=metadata, costs=finalized_costs)


def finalize_result(
    session: CampaignSession,
    snapshot: GenerationTaskSnapshot,
    result: JobResult,
) -> JobResult:
    """Synchronous one-row facade over the common two-phase coordinator."""

    coordinator = ResultFinalizationCoordinator(
        session,
        snapshot,
        expected_count=1,
    )
    coordinator.accept(0, result)
    return coordinator.finish()[0]


def _prepare_result(
    session: CampaignSession,
    snapshot: GenerationTaskSnapshot,
    index: int,
    result: JobResult,
    *,
    group_id: str,
    completed_at: float,
) -> _PreparedResult:
    started = time.monotonic()
    metadata = dict(result.metadata)
    metadata.setdefault("campaign_id", session.campaign_id)
    metadata.update(
        {
            "interpretation_fingerprint": snapshot.interpretation_fingerprint,
            "evaluation_fingerprint": snapshot.evaluation_fingerprint,
            "task_snapshot_id": snapshot.task_snapshot_id,
            "publication_group_id": group_id,
        }
    )
    if result.status != "done":
        prepared = replace(
            result,
            raw_data_paths=(),
            raw_data_items=(),
            metadata=metadata,
            costs=None,
        )
        owned = ()
        durable_status = result.status
    else:
        try:
            source = (
                result.raw_data_items
                if result.raw_data_items
                else tuple(Path(path) for path in result.raw_data_paths)
            )
            owned = own_rawdata_source(source)
        except Exception as exc:  # Invalid rawData is not completed evidence.
            metadata.update(
                {
                    "status": "error",
                    "failure_stage": "rawdata_validation",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "failed_at": _now_text(),
                    "rawdata_validation_ownership_sec": max(
                        0.0, time.monotonic() - started
                    ),
                }
            )
            prepared = replace(
                result,
                status="error",
                raw_data_paths=(),
                raw_data_items=(),
                metadata=metadata,
                costs=None,
            )
            owned = ()
            durable_status = "error"
        else:
            metadata["rawdata_validation_ownership_sec"] = max(
                0.0, time.monotonic() - started
            )
            prepared = replace(
                result,
                raw_data_paths=(),
                raw_data_items=(),
                metadata=metadata,
                costs=None,
            )
            durable_status = "completed"
    try:
        envelope = build_owned_envelope(
            snapshot.config.workspace,
            prepared.job_name,
            prepared.unnormalized_variables,
            owned,
            prepared.metadata,
            status=durable_status,
        )
    except Exception as exc:
        raise RecordingError(
            f"failed to construct durable evidence for {prepared.job_name}"
        ) from exc
    admission_started = time.monotonic()
    receipt = session.submit_evidence(envelope, group_id=group_id)
    prepared_metadata = dict(prepared.metadata)
    prepared_metadata.update(
        {
            "candidate_id": receipt.candidate_id,
            "evidence_id": receipt.candidate_id,
            "evidence_state": "pending",
            "publication_receipt_state": "pending",
            "recorder_admission_sec": max(
                0.0, time.monotonic() - admission_started
            ),
        }
    )
    return _PreparedResult(
        index=index,
        result=replace(prepared, metadata=prepared_metadata),
        receipt=receipt,
        completed_at=completed_at,
    )


def _now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


__all__ = ["ResultFinalizationCoordinator", "finalize_result"]
