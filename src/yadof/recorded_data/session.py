"""Campaign-owned hot history and backpressured segment recorder."""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, replace
import threading
import time
from types import MappingProxyType
from typing import Mapping, Sequence
import uuid

from ..config import LoadedConfig
from ..job_template import api as job_template_api
from ..job_template.rawdata_contract import NamedRawDataItem
from ..task_snapshot import (
    RECORDER_CONFIG_NAMES,
    GenerationTaskSnapshot,
    create_generation_snapshot,
)
from ..workspace import WorkspaceContext
from .campaign_lock import CampaignLock
from .dataset import (
    CostTable,
    EvidenceDataset,
    InterpretationStatus,
    _LiveEvidenceInput,
    _evidence_dataset_from_live,
    calculate_cost_table,
)
from .paths import RecordedDataPaths, recorded_data_paths
from .records import catalog_snapshot
from .segment_store import (
    RecordEnvelope,
    SegmentReference,
    load_reference_rawdata,
    next_sequence_by_directory,
    publish_segment,
    segment_counter_key,
)


class RecordingError(RuntimeError):
    """Raised when durable campaign evidence cannot be published."""


class PublicationReceipt:
    """Thread-safe acknowledgement for one immutable evidence publication."""

    __slots__ = (
        "candidate_id",
        "job_name",
        "group_id",
        "reservation_bytes",
        "_event",
        "_lock",
        "_state",
        "_reference",
        "_failure",
        "_committed_at",
    )

    def __init__(
        self,
        *,
        candidate_id: str,
        job_name: str,
        group_id: str,
        reservation_bytes: int,
    ) -> None:
        self.candidate_id = str(candidate_id)
        self.job_name = str(job_name)
        self.group_id = str(group_id)
        self.reservation_bytes = int(reservation_bytes)
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._state = "pending"
        self._reference: SegmentReference | None = None
        self._failure: BaseException | None = None
        self._committed_at: float | None = None

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @property
    def committed_at_monotonic(self) -> float | None:
        with self._lock:
            return self._committed_at

    def wait_committed(self, timeout: float | None = None) -> SegmentReference:
        """Wait for durable publication and return its recovery-visible reference."""

        if not self._event.wait(timeout):
            raise TimeoutError(
                f"timed out waiting for evidence receipt {self.candidate_id}"
            )
        with self._lock:
            if self._state == "committed" and self._reference is not None:
                return self._reference
            failure = self._failure
        raise RecordingError(
            f"evidence publication failed for {self.job_name}"
        ) from failure

    def _mark_committed(self, reference: SegmentReference) -> bool:
        with self._lock:
            if self._state != "pending":
                return False
            self._reference = reference
            self._committed_at = time.monotonic()
            self._state = "committed"
            self._event.set()
            return True

    def _mark_failed(self, failure: BaseException) -> bool:
        with self._lock:
            if self._state != "pending":
                return False
            self._failure = failure
            self._state = "failed"
            self._event.set()
            return True


@dataclass(slots=True)
class RecorderCounters:
    offered: int = 0
    admitted: int = 0
    published_candidates: int = 0
    published_segments: int = 0
    write_failed: int = 0
    write_failed_segments: int = 0
    fatal_errors: int = 0
    backpressure_waits: int = 0
    backpressure_wait_sec: float = 0.0
    flush_waits: int = 0
    flush_wait_sec: float = 0.0
    peak_unpublished_candidates: int = 0
    peak_unpublished_bytes: int = 0


@dataclass(slots=True)
class InterpretationCounters:
    receipts_submitted: int = 0
    receipts_committed: int = 0
    receipts_failed: int = 0
    committed_uninterpreted_candidates: int = 0
    committed_uninterpreted_bytes: int = 0
    peak_committed_uninterpreted_candidates: int = 0
    peak_committed_uninterpreted_bytes: int = 0
    committed_owned_candidates: int = 0
    committed_owned_bytes: int = 0
    peak_committed_owned_candidates: int = 0
    peak_committed_owned_bytes: int = 0
    committed_owned_spills: int = 0
    interpretation_succeeded: int = 0
    interpretation_failed: int = 0
    interpretation_not_applicable: int = 0


@dataclass(slots=True)
class _SessionRow:
    record: dict[str, object]
    reference: SegmentReference | None = None
    envelope: RecordEnvelope | None = None
    receipt: PublicationReceipt | None = None
    evidence_state: str = "committed"
    interpretation_state: str = "uninterpreted"
    interpretation_diagnostics: dict[str, object] | None = None
    normalized: tuple[float, ...] | None = None
    costs: tuple[float, ...] | None = None
    interpretation_fingerprint: str | None = None


class _BoundedSegmentWriter:
    def __init__(
        self,
        storage: RecordedDataPaths,
        config: LoadedConfig,
        *,
        on_published,
        on_failed,
        on_exit,
    ) -> None:
        self.storage = storage
        self.max_segment_count = int(config.HISTORY_SEGMENT_MAX_CANDIDATES)
        self.segment_target_bytes = int(config.HISTORY_SEGMENT_TARGET_BYTES)
        self.max_candidate_bytes = int(config.HISTORY_MAX_CANDIDATE_BYTES)
        self.max_unpublished_count = int(
            config.HISTORY_UNPUBLISHED_MAX_CANDIDATES
        )
        self.max_unpublished_bytes = int(config.HISTORY_UNPUBLISHED_MAX_BYTES)
        self.max_failures = int(config.HISTORY_WRITER_MAX_CONSECUTIVE_FAILURES)
        if self.max_segment_count > self.max_unpublished_count:
            raise ValueError(
                "HISTORY_SEGMENT_MAX_CANDIDATES must not exceed "
                "HISTORY_UNPUBLISHED_MAX_CANDIDATES"
            )
        if self.max_candidate_bytes > self.max_unpublished_bytes:
            raise ValueError(
                "HISTORY_MAX_CANDIDATE_BYTES must not exceed "
                "HISTORY_UNPUBLISHED_MAX_BYTES"
            )
        self._on_published = on_published
        self._on_failed = on_failed
        self._on_exit = on_exit
        self._condition = threading.Condition()
        self._queue: deque[RecordEnvelope] = deque()
        self._flush_requested = False
        self._shutdown = False
        self._active_batch: tuple[RecordEnvelope, ...] = ()
        self._unpublished_count = 0
        self._unpublished_bytes = 0
        self._consecutive_failures = 0
        self._fatal_error: BaseException | None = None
        self._counters = RecorderCounters()
        self._sequences = next_sequence_by_directory(storage)
        self._thread = threading.Thread(
            target=self._run_guarded,
            name="yadof-history-writer",
            daemon=False,
        )
        self._thread.start()

    def offer(self, envelope: RecordEnvelope) -> bool:
        wait_started: float | None = None
        with self._condition:
            self._counters.offered += 1
            self._raise_if_unavailable_unlocked()
            if envelope.reservation_bytes > self.max_candidate_bytes:
                raise RecordingError(
                    "record envelope reservation exceeds "
                    "HISTORY_MAX_CANDIDATE_BYTES: "
                    f"{envelope.reservation_bytes} > {self.max_candidate_bytes}"
                )
            try:
                while not self._has_capacity_unlocked(envelope):
                    self._raise_if_unavailable_unlocked()
                    if wait_started is None:
                        wait_started = time.monotonic()
                        self._counters.backpressure_waits += 1
                    self._flush_requested = True
                    self._condition.notify_all()
                    self._condition.wait()
                self._raise_if_unavailable_unlocked()
            finally:
                if wait_started is not None:
                    self._counters.backpressure_wait_sec += max(
                        0.0, time.monotonic() - wait_started
                    )
            self._queue.append(envelope)
            self._unpublished_count += 1
            self._unpublished_bytes += envelope.reservation_bytes
            self._counters.admitted += 1
            self._counters.peak_unpublished_candidates = max(
                self._counters.peak_unpublished_candidates,
                self._unpublished_count,
            )
            self._counters.peak_unpublished_bytes = max(
                self._counters.peak_unpublished_bytes,
                self._unpublished_bytes,
            )
            self._condition.notify_all()
            return True

    def flush_boundary(self) -> None:
        wait_started: float | None = None
        with self._condition:
            self._raise_if_unavailable_unlocked()
            self._flush_requested = True
            self._condition.notify_all()
            try:
                while self._unpublished_count:
                    self._raise_if_unavailable_unlocked()
                    if wait_started is None:
                        wait_started = time.monotonic()
                        self._counters.flush_waits += 1
                    self._condition.wait()
                self._raise_if_unavailable_unlocked()
            finally:
                if wait_started is not None:
                    self._counters.flush_wait_sec += max(
                        0.0, time.monotonic() - wait_started
                    )

    def _has_capacity_unlocked(self, envelope: RecordEnvelope) -> bool:
        return (
            self._unpublished_count + 1 <= self.max_unpublished_count
            and self._unpublished_bytes + envelope.reservation_bytes
            <= self.max_unpublished_bytes
        )

    def _raise_if_unavailable_unlocked(self) -> None:
        if self._fatal_error is not None:
            raise RecordingError(
                "campaign evidence writer failed; no later evaluation may proceed"
            ) from self._fatal_error
        if self._shutdown:
            raise RecordingError("campaign evidence writer is shutting down")
        if not self._thread.is_alive():
            raise RecordingError("campaign evidence writer stopped unexpectedly")

    def _set_fatal_unlocked(self, exc: BaseException) -> None:
        if self._fatal_error is None:
            self._fatal_error = exc
            self._counters.fatal_errors += 1
        self._condition.notify_all()

    def _fail_pending_unlocked(self) -> tuple[RecordEnvelope, ...]:
        failed = self._active_batch + tuple(self._queue)
        self._active_batch = ()
        self._queue.clear()
        self._release_budget_unlocked(failed)
        self._condition.notify_all()
        return failed

    def counters(self) -> dict[str, object]:
        with self._condition:
            return asdict(self._counters)

    def shutdown(self) -> bool:
        with self._condition:
            self._shutdown = True
            self._flush_requested = True
            self._condition.notify_all()
        self._thread.join()
        with self._condition:
            if self._fatal_error is not None:
                raise RecordingError(
                    "campaign closed before all evidence could be published"
                ) from self._fatal_error
        return True

    def _run_guarded(self) -> None:
        try:
            self._run()
        except BaseException as exc:  # noqa: BLE001 - wake blocked producers.
            with self._condition:
                self._set_fatal_unlocked(exc)
                failed = self._fail_pending_unlocked()
            if failed:
                self._on_failed(failed, "writer_death")
        finally:
            # An unexpectedly dead recorder must not release the campaign's
            # exclusivity while optimization continues. CampaignSession.close()
            # releases it after joining the already-dead thread. A normal shutdown
            # releases the retained lock here after every publication completes.
            with self._condition:
                release_on_exit = self._shutdown
            if release_on_exit:
                self._on_exit()

    def _run(self) -> None:
        while True:
            with self._condition:
                self._condition.wait_for(self._ready_unlocked)
                if self._shutdown and not self._queue:
                    return
                batch = self._take_batch_unlocked()
                if not batch:
                    continue
                self._active_batch = batch
            first = batch[0]
            key = segment_counter_key(first.run_id, first.generation_index)
            sequence = self._sequences.get(key, 0)
            while True:
                try:
                    _path, references = publish_segment(
                        self.storage, batch, sequence=sequence
                    )
                except Exception as exc:  # noqa: BLE001 - retry the same evidence.
                    with self._condition:
                        self._counters.write_failed += len(batch)
                        self._counters.write_failed_segments += 1
                        self._consecutive_failures += 1
                        exhausted = self._consecutive_failures >= self.max_failures
                        if exhausted:
                            self._set_fatal_unlocked(exc)
                            failed = self._fail_pending_unlocked()
                        else:
                            failed = ()
                    if exhausted:
                        if failed:
                            self._on_failed(failed, "write_failed")
                        return
                    continue
                break
            self._on_published(batch, references)
            with self._condition:
                self._active_batch = ()
                self._release_budget_unlocked(batch)
                self._consecutive_failures = 0
                self._sequences[key] = sequence + 1
                self._counters.published_candidates += len(batch)
                self._counters.published_segments += 1
                self._condition.notify_all()

    def _ready_unlocked(self) -> bool:
        if self._shutdown:
            return True
        if not self._queue:
            return False
        if self._flush_requested:
            return True
        if len(self._queue) >= self.max_segment_count:
            return True
        total = 0
        first = self._queue[0]
        for envelope in self._queue:
            if (
                envelope.run_id != first.run_id
                or envelope.generation_index != first.generation_index
            ):
                return True
            total += envelope.reservation_bytes
            if total >= self.segment_target_bytes:
                return True
        return False

    def _take_batch_unlocked(self) -> tuple[RecordEnvelope, ...]:
        if not self._queue:
            self._flush_requested = False
            return ()
        first = self._queue[0]
        batch: list[RecordEnvelope] = []
        total = 0
        while self._queue and len(batch) < self.max_segment_count:
            candidate = self._queue[0]
            if (
                candidate.run_id != first.run_id
                or candidate.generation_index != first.generation_index
            ):
                break
            if batch and total + candidate.reservation_bytes > self.segment_target_bytes:
                break
            batch.append(self._queue.popleft())
            total += candidate.reservation_bytes
            if total >= self.segment_target_bytes:
                break
        if not self._queue:
            self._flush_requested = False
        return tuple(batch)

    def _release_budget_unlocked(self, envelopes: Sequence[RecordEnvelope]) -> None:
        self._unpublished_count = max(0, self._unpublished_count - len(envelopes))
        self._unpublished_bytes = max(
            0,
            self._unpublished_bytes
            - sum(envelope.reservation_bytes for envelope in envelopes),
        )


class CampaignSession:
    """Private per-campaign recorder, catalog, and derived history view."""

    def __init__(self, config: LoadedConfig) -> None:
        self.initial_config = config
        self.campaign_id = uuid.uuid4().hex
        self.storage = recorded_data_paths(config.workspace)
        self._lock = CampaignLock(self.storage.campaign_lock_path)
        self._lock.acquire()
        self._state_lock = threading.RLock()
        self._close_lock = threading.Lock()
        catalog = catalog_snapshot(self.storage)
        self._rows: dict[str, _SessionRow] = {
            reference.candidate_id: _SessionRow(
                record=dict(reference.record), reference=reference
            )
            for reference in catalog.references
        }
        self.catalog_diagnostics = list(catalog.diagnostics)
        self._snapshots: list[GenerationTaskSnapshot] = []
        self.current_snapshot: GenerationTaskSnapshot | None = None
        self._stable_parameter_names: tuple[str, ...] | None = None
        self._stable_objective_count: int | None = None
        self.last_reinterpretation_sec = 0.0
        self._closed = False
        self._closing = False
        self._generation_handles: set[object] = set()
        self._generation_handle_snapshots: dict[object, GenerationTaskSnapshot] = {}
        self._generation_handle_policies: dict[object, str] = {}
        self._interpretation_counters = InterpretationCounters()
        self._committed_owned_count_limit = int(
            config.HISTORY_UNPUBLISHED_MAX_CANDIDATES
        )
        self._committed_owned_bytes_limit = int(
            config.HISTORY_UNPUBLISHED_MAX_BYTES
        )
        self._lock_release_guard = threading.Lock()
        try:
            self._writer = _BoundedSegmentWriter(
                self.storage,
                config,
                on_published=self._on_published,
                on_failed=self._on_failed,
                on_exit=self._release_campaign_lock,
            )
        except Exception:
            self._lock.release()
            raise

    def begin_generation(self, config: LoadedConfig) -> GenerationTaskSnapshot:
        with self._state_lock:
            if self._closed or self._closing:
                raise RuntimeError("campaign session is closing or closed")
            if self._generation_handles:
                raise RuntimeError(
                    "cannot begin a new generation while generation handles remain open; "
                    "wait and close every handle first"
                )
        snapshot = create_generation_snapshot(self._freeze_recorder_config(config))
        try:
            if self._stable_parameter_names is None:
                self._stable_parameter_names = snapshot.parameter_names
                self._stable_objective_count = len(snapshot.objective_names)
            else:
                if snapshot.parameter_names != self._stable_parameter_names:
                    raise ValueError(
                        "in-campaign parameter names/order/count changed; use a new workspace"
                    )
                if len(snapshot.objective_names) != self._stable_objective_count:
                    raise ValueError(
                        "in-campaign objective count changed; use a new workspace"
                    )
        except Exception:
            snapshot.close()
            raise
        self._snapshots.append(snapshot)
        self.current_snapshot = snapshot
        return snapshot

    def _register_generation_handle(
        self,
        snapshot: GenerationTaskSnapshot | None,
        handle: object,
        *,
        boundary_policy: str,
    ) -> None:
        """Retain one exact current-generation lease until its handle closes."""

        policy = str(boundary_policy).strip().lower()
        if policy not in {"cancel", "wait"}:
            raise ValueError("generation handle boundary_policy must be 'cancel' or 'wait'")
        with self._state_lock:
            if self._closed or self._closing:
                raise RuntimeError("cannot register work on a closing campaign")
            if snapshot is None or snapshot is not self.current_snapshot:
                raise ValueError(
                    "generation handle must use the campaign's current task snapshot"
                )
            if handle in self._generation_handles:
                if self._generation_handle_policies[handle] != policy:
                    raise ValueError("generation handle boundary policy cannot change")
                return
            self._generation_handles.add(handle)
            self._generation_handle_snapshots[handle] = snapshot
            self._generation_handle_policies[handle] = policy

    def _unregister_generation_handle(self, handle: object) -> None:
        with self._state_lock:
            self._generation_handles.discard(handle)
            self._generation_handle_snapshots.pop(handle, None)
            self._generation_handle_policies.pop(handle, None)

    def finish_generation(self) -> None:
        """Resolve and close every exact-current-snapshot handle normally."""

        with self._state_lock:
            handles = tuple(
                (handle, self._generation_handle_policies[handle])
                for handle in self._generation_handles
            )
        errors: list[BaseException] = []
        for handle, policy in handles:
            try:
                if policy == "wait":
                    finish = getattr(handle, "finish", None)
                    if callable(finish):
                        finish()
                    else:
                        getattr(handle, "wait")()
                        getattr(handle, "close")()
                else:
                    getattr(handle, "close")()
            except BaseException as exc:
                errors.append(exc)
        if errors:
            raise errors[-1]

    def _freeze_recorder_config(self, config: LoadedConfig) -> LoadedConfig:
        values = dict(config.values)
        sources = dict(config.sources)
        for name in RECORDER_CONFIG_NAMES:
            values[name] = self.initial_config.values[name]
            sources[name] = self.initial_config.sources[name]
        workspace = replace(
            config.workspace,
            recorded_data_dir=self.initial_config.workspace.recorded_data_dir,
        )
        return replace(
            config,
            workspace=workspace,
            values=MappingProxyType(values),
            sources=MappingProxyType(sources),
        )

    def submit_evidence(
        self,
        envelope: RecordEnvelope,
        *,
        group_id: str,
    ) -> PublicationReceipt:
        """Admit owned evidence and return its durable-publication receipt."""

        receipt = PublicationReceipt(
            candidate_id=envelope.candidate_id,
            job_name=str(envelope.record.get("job_name") or ""),
            group_id=group_id,
            reservation_bytes=envelope.reservation_bytes,
        )
        row = _SessionRow(
            record=dict(envelope.record),
            envelope=envelope,
            receipt=receipt,
            evidence_state="pending",
            interpretation_state="pending",
        )
        with self._state_lock:
            if envelope.candidate_id in self._rows:
                raise RecordingError(
                    "duplicate campaign candidate identity cannot be recorded: "
                    f"{envelope.candidate_id}"
                )
            self._rows[envelope.candidate_id] = row
            self._interpretation_counters.receipts_submitted += 1
        try:
            self._writer.offer(envelope)
        except Exception as exc:
            with self._state_lock:
                row.envelope = None
                row.reference = None
                row.evidence_state = "recording_failed"
                row.interpretation_state = "blocked"
                metadata = dict(row.record.get("job_metadata") or {})
                metadata["recording_error"] = str(exc)
                row.record["job_metadata"] = metadata
                if receipt._mark_failed(exc):
                    self._interpretation_counters.receipts_failed += 1
            raise
        return receipt

    def committed_evidence(
        self, receipt: PublicationReceipt
    ) -> tuple[NamedRawDataItem, ...]:
        """Return owned or recovery-loaded evidence after acknowledgement."""

        reference = receipt.wait_committed()
        with self._state_lock:
            row = self._rows.get(receipt.candidate_id)
            if row is None or row.evidence_state != "committed":
                raise RecordingError(
                    f"committed evidence row is unavailable: {receipt.candidate_id}"
                )
            if row.envelope is not None:
                return row.envelope.rawdata_items
        return load_reference_rawdata(reference)

    def record_interpretation(
        self,
        receipt: PublicationReceipt,
        *,
        state: str,
        normalized: Sequence[float] | None,
        costs: Sequence[float] | None,
        interpretation_fingerprint: str,
        diagnostics: Mapping[str, object] | None = None,
    ) -> None:
        """Attach a transient derived interpretation and release owned payload."""

        selected_state = str(state)
        if selected_state not in {"succeeded", "failed", "not_applicable"}:
            raise ValueError(f"unsupported interpretation state: {selected_state!r}")
        receipt.wait_committed()
        with self._state_lock:
            row = self._rows.get(receipt.candidate_id)
            if row is None or row.evidence_state != "committed":
                raise RecordingError(
                    f"cannot interpret unavailable evidence: {receipt.candidate_id}"
                )
            was_pending = row.interpretation_state == "pending"
            retained_owned = row.envelope is not None
            row.normalized = (
                tuple(float(value) for value in normalized)
                if normalized is not None
                else None
            )
            row.costs = (
                tuple(float(value) for value in costs) if costs is not None else None
            )
            row.interpretation_fingerprint = str(interpretation_fingerprint)
            row.interpretation_state = selected_state
            row.interpretation_diagnostics = (
                dict(diagnostics) if diagnostics is not None else None
            )
            row.envelope = None
            counters = self._interpretation_counters
            if was_pending:
                counters.committed_uninterpreted_candidates = max(
                    0, counters.committed_uninterpreted_candidates - 1
                )
                counters.committed_uninterpreted_bytes = max(
                    0,
                    counters.committed_uninterpreted_bytes
                    - receipt.reservation_bytes,
                )
                if retained_owned:
                    counters.committed_owned_candidates = max(
                        0, counters.committed_owned_candidates - 1
                    )
                    counters.committed_owned_bytes = max(
                        0, counters.committed_owned_bytes - receipt.reservation_bytes
                    )
            if selected_state == "succeeded":
                counters.interpretation_succeeded += 1
            elif selected_state == "failed":
                counters.interpretation_failed += 1
            else:
                counters.interpretation_not_applicable += 1

    def flush_boundary(self) -> None:
        self._writer.flush_boundary()

    def records(self) -> tuple[dict[str, object], ...]:
        with self._state_lock:
            output = []
            for row in self._rows.values():
                record = dict(row.record)
                record["evidence_state"] = row.evidence_state
                record["interpretation_state"] = row.interpretation_state
                if row.interpretation_diagnostics is not None:
                    record["interpretation_diagnostics"] = dict(
                        row.interpretation_diagnostics
                    )
                if row.receipt is not None:
                    record["publication_receipt"] = {
                        "candidate_id": row.receipt.candidate_id,
                        "group_id": row.receipt.group_id,
                        "state": row.receipt.state,
                    }
                output.append(record)
            return tuple(output)

    def evidence_dataset(self) -> EvidenceDataset:
        """Freeze the current live catalog without retaining envelope payloads."""

        with self._state_lock:
            selected = self.current_snapshot
        workspace = (
            self.initial_config.workspace
            if selected is None
            else selected.config.workspace
        )
        return self._evidence_dataset_for_workspace(workspace)

    def _evidence_dataset_for_workspace(
        self, workspace: WorkspaceContext
    ) -> EvidenceDataset:
        with self._state_lock:
            inputs = tuple(
                _LiveEvidenceInput(
                    candidate_id=candidate_id,
                    record=dict(row.record),
                    evidence_state=row.evidence_state,
                    reference=row.reference,
                    interpretation_state=row.interpretation_state,
                    normalized_variables=row.normalized,
                    costs=row.costs,
                    interpretation_fingerprint=row.interpretation_fingerprint,
                    interpretation_diagnostics=(
                        None
                        if row.interpretation_diagnostics is None
                        else dict(row.interpretation_diagnostics)
                    ),
                )
                for candidate_id, row in self._rows.items()
            )
            diagnostics = tuple(dict(item) for item in self.catalog_diagnostics)
        return _evidence_dataset_from_live(workspace, inputs, diagnostics)

    def cost_table(
        self, snapshot: GenerationTaskSnapshot | None = None
    ) -> CostTable:
        """Build and cache one task-scoped interpretation table for live evidence."""

        selected = snapshot or self.current_snapshot
        if selected is None:
            raise RuntimeError("campaign generation snapshot has not been selected")
        started = time.monotonic()
        dataset = self._evidence_dataset_for_workspace(selected.config.workspace)
        table = calculate_cost_table(dataset, selected)
        with self._state_lock:
            for cost_row in table.rows:
                if cost_row.status == InterpretationStatus.MISSING:
                    continue
                row = self._rows.get(cost_row.evidence_id)
                if row is None or cost_row.row_id != cost_row.evidence_id:
                    continue
                row.normalized = cost_row.normalized_variables
                row.costs = cost_row.costs
                row.interpretation_fingerprint = table.interpretation_fingerprint
                row.interpretation_state = cost_row.status.value
                row.interpretation_diagnostics = dict(cost_row.diagnostics)
        self.last_reinterpretation_sec = max(0.0, time.monotonic() - started)
        return table

    def historical_results(
        self, snapshot: GenerationTaskSnapshot | None = None
    ) -> tuple[tuple[str, tuple[float, ...], tuple[float, ...]], ...]:
        table = self.cost_table(snapshot)
        return tuple(
            (
                row.job_name,
                tuple(row.normalized_variables or ()),
                tuple(row.costs or ()),
            )
            for row in table.rows
            if row.status == InterpretationStatus.SUCCEEDED
        )

    def rawdata_samples(
        self,
        *,
        job_names: Sequence[str] | None = None,
        status: str | None = None,
    ) -> tuple[tuple[str, tuple[dict[str, object], ...]], ...]:
        requested = set(job_names) if job_names is not None else None
        output = []
        with self._state_lock:
            rows = tuple(self._rows.values())
        for row in rows:
            name = str(row.record.get("job_name", ""))
            if requested is not None and name not in requested:
                continue
            if status is not None and str(row.record.get("status")) != status:
                continue
            try:
                items = self._evidence(row)
            except Exception:
                continue
            output.append((name, tuple(dict(item.payload) for item in items)))
        return tuple(output)

    def named_rawdata_samples(
        self,
        *,
        job_names: Sequence[str] | None = None,
        status: str | None = None,
    ) -> tuple[tuple[str, tuple[NamedRawDataItem, ...]], ...]:
        """Return transient evidence with its stable direct ``.npz`` basenames.

        This is the named counterpart of :meth:`rawdata_samples`. It does not
        change the recorded-data format or retain another evidence copy; callers
        that need long-lived ownership must freeze or copy the returned payloads.
        """

        requested = set(job_names) if job_names is not None else None
        output = []
        with self._state_lock:
            rows = tuple(self._rows.values())
        for row in rows:
            name = str(row.record.get("job_name", ""))
            if requested is not None and name not in requested:
                continue
            if status is not None and str(row.record.get("status")) != status:
                continue
            try:
                items = self._evidence(row)
            except Exception:
                continue
            output.append(
                (
                    name,
                    tuple(
                        NamedRawDataItem(item.filename, dict(item.payload))
                        for item in items
                    ),
                )
            )
        return tuple(output)

    def record_metadata(
        self,
        *,
        job_names: Sequence[str] | None = None,
        status: str | None = None,
    ) -> tuple[tuple[str, dict[str, object]], ...]:
        """Return task/runtime metadata aligned by stable job name."""

        requested = set(job_names) if job_names is not None else None
        output = []
        with self._state_lock:
            rows = tuple(self._rows.values())
        for row in rows:
            name = str(row.record.get("job_name", ""))
            if requested is not None and name not in requested:
                continue
            if status is not None and str(row.record.get("status")) != status:
                continue
            metadata = row.record.get("job_metadata")
            output.append(
                (name, dict(metadata) if isinstance(metadata, Mapping) else {})
            )
        return tuple(output)

    def counters(self) -> dict[str, object]:
        output = self._writer.counters()
        with self._state_lock:
            output.update(asdict(self._interpretation_counters))
        return output

    def close(self) -> dict[str, object]:
        with self._close_lock:
            if self._closed:
                return self.counters()
            with self._state_lock:
                self._closing = True
                handles = tuple(self._generation_handles)
            errors: list[BaseException] = []
            for handle in handles:
                try:
                    close = getattr(handle, "close")
                    close()
                except BaseException as exc:  # Finish every owned cleanup obligation.
                    errors.append(exc)
            try:
                self._writer.shutdown()
            except BaseException as exc:  # Preserve cleanup before propagating failure.
                errors.append(exc)
            finally:
                self._release_campaign_lock()
                for snapshot in self._snapshots:
                    snapshot.close()
                with self._state_lock:
                    self._closed = True
                    self._closing = False
                    self._generation_handles.clear()
                    self._generation_handle_snapshots.clear()
                    self._generation_handle_policies.clear()
            if errors:
                raise errors[-1]
            return self.counters()

    def _evidence(self, row: _SessionRow):
        if row.evidence_state != "committed":
            raise FileNotFoundError("recorded evidence is not durably committed")
        if row.envelope is not None:
            return row.envelope.rawdata_items
        if row.reference is not None:
            return load_reference_rawdata(row.reference)
        raise FileNotFoundError("recorded evidence is unavailable after publication failure")

    def _on_published(
        self,
        envelopes: Sequence[RecordEnvelope],
        references: Sequence[SegmentReference],
    ) -> None:
        with self._state_lock:
            for envelope, reference in zip(envelopes, references):
                row = self._rows.get(envelope.candidate_id)
                if row is None:
                    continue
                counters = self._interpretation_counters
                retain_owned = bool(envelope.rawdata_items) and (
                    counters.committed_owned_candidates + 1
                    <= self._committed_owned_count_limit
                    and counters.committed_owned_bytes + envelope.reservation_bytes
                    <= self._committed_owned_bytes_limit
                )
                row.reference = reference
                row.envelope = envelope if retain_owned else None
                row.evidence_state = "committed"
                counters.committed_uninterpreted_candidates += 1
                counters.committed_uninterpreted_bytes += envelope.reservation_bytes
                counters.peak_committed_uninterpreted_candidates = max(
                    counters.peak_committed_uninterpreted_candidates,
                    counters.committed_uninterpreted_candidates,
                )
                counters.peak_committed_uninterpreted_bytes = max(
                    counters.peak_committed_uninterpreted_bytes,
                    counters.committed_uninterpreted_bytes,
                )
                if retain_owned:
                    counters.committed_owned_candidates += 1
                    counters.committed_owned_bytes += envelope.reservation_bytes
                    counters.peak_committed_owned_candidates = max(
                        counters.peak_committed_owned_candidates,
                        counters.committed_owned_candidates,
                    )
                    counters.peak_committed_owned_bytes = max(
                        counters.peak_committed_owned_bytes,
                        counters.committed_owned_bytes,
                    )
                elif envelope.rawdata_items:
                    counters.committed_owned_spills += 1
                if row.receipt is not None and row.receipt._mark_committed(reference):
                    counters.receipts_committed += 1

    def _on_failed(
        self, envelopes: Sequence[RecordEnvelope], reason: str
    ) -> None:
        failure = RecordingError(f"evidence publication failed: {reason}")
        with self._state_lock:
            for envelope in envelopes:
                row = self._rows.get(envelope.candidate_id)
                if row is None:
                    continue
                row.envelope = None
                row.reference = None
                row.evidence_state = "recording_failed"
                row.interpretation_state = "blocked"
                metadata = dict(row.record.get("job_metadata") or {})
                metadata["recording_error"] = str(reason)
                row.record["job_metadata"] = metadata
                if row.receipt is not None and row.receipt._mark_failed(failure):
                    self._interpretation_counters.receipts_failed += 1

    def _release_campaign_lock(self) -> None:
        with self._lock_release_guard:
            self._lock.release()

    def __enter__(self) -> "CampaignSession":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()


__all__ = [
    "CampaignSession",
    "PublicationReceipt",
    "RecorderCounters",
    "RecordingError",
]
