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
from .campaign_lock import CampaignLock
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
class _SessionRow:
    record: dict[str, object]
    reference: SegmentReference | None = None
    envelope: RecordEnvelope | None = None
    evidence_state: str = "published"
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

    def add_finalized(
        self,
        envelope: RecordEnvelope,
        *,
        normalized: Sequence[float] | None,
        costs: Sequence[float] | None,
        interpretation_fingerprint: str,
    ) -> bool:
        row = _SessionRow(
            record=dict(envelope.record),
            envelope=envelope,
            evidence_state="pending",
            normalized=(
                tuple(float(value) for value in normalized)
                if normalized is not None
                else None
            ),
            costs=(
                tuple(float(value) for value in costs) if costs is not None else None
            ),
            interpretation_fingerprint=interpretation_fingerprint,
        )
        with self._state_lock:
            if envelope.candidate_id in self._rows:
                raise RecordingError(
                    "duplicate campaign candidate identity cannot be recorded: "
                    f"{envelope.candidate_id}"
                )
            self._rows[envelope.candidate_id] = row
        try:
            return self._writer.offer(envelope)
        except Exception as exc:
            with self._state_lock:
                row.envelope = None
                row.reference = None
                row.evidence_state = "recording_failed"
                metadata = dict(row.record.get("job_metadata") or {})
                metadata["recording_error"] = str(exc)
                row.record["job_metadata"] = metadata
            raise

    def flush_boundary(self) -> None:
        self._writer.flush_boundary()

    def records(self) -> tuple[dict[str, object], ...]:
        with self._state_lock:
            return tuple(dict(row.record) for row in self._rows.values())

    def historical_results(
        self, snapshot: GenerationTaskSnapshot | None = None
    ) -> tuple[tuple[str, tuple[float, ...], tuple[float, ...]], ...]:
        selected = snapshot or self.current_snapshot
        if selected is None:
            raise RuntimeError("campaign generation snapshot has not been selected")
        started = time.monotonic()
        output: list[tuple[str, tuple[float, ...], tuple[float, ...]]] = []
        with self._state_lock:
            rows = tuple(self._rows.values())
        for row in rows:
            if str(row.record.get("status")) != "completed":
                continue
            if (
                row.interpretation_fingerprint
                != selected.interpretation_fingerprint
                or row.normalized is None
                or row.costs is None
            ):
                try:
                    items = self._evidence(row)
                    raw_variables = _raw_variables_tuple(
                        selected, row.record.get("raw_variables")
                    )
                    normalized = job_template_api.normalize_variables(
                        selected.config.workspace, raw_variables
                    )
                    calculated = job_template_api.calculate_cost(
                        selected.config.workspace,
                        (tuple(item.payload for item in items),),
                        (raw_variables,),
                    )[0]
                    if len(calculated) != len(selected.objective_names):
                        raise ValueError("historical objective width mismatch")
                except Exception:
                    continue
                with self._state_lock:
                    row.normalized = tuple(float(value) for value in normalized)
                    row.costs = tuple(float(value) for value in calculated)
                    row.interpretation_fingerprint = (
                        selected.interpretation_fingerprint
                    )
            output.append(
                (
                    str(row.record.get("job_name", "")),
                    tuple(row.normalized or ()),
                    tuple(row.costs or ()),
                )
            )
        self.last_reinterpretation_sec = max(0.0, time.monotonic() - started)
        return tuple(output)

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

    def counters(self) -> dict[str, object]:
        return self._writer.counters()

    def close(self) -> dict[str, object]:
        if self._closed:
            return self.counters()
        self._closed = True
        error: BaseException | None = None
        try:
            self._writer.shutdown()
        except BaseException as exc:  # Preserve cleanup before propagating failure.
            error = exc
        finally:
            self._release_campaign_lock()
            for snapshot in self._snapshots:
                snapshot.close()
        if error is not None:
            raise error
        return self.counters()

    def _evidence(self, row: _SessionRow):
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
                row.reference = reference
                row.envelope = None
                row.evidence_state = "published"

    def _on_failed(
        self, envelopes: Sequence[RecordEnvelope], reason: str
    ) -> None:
        with self._state_lock:
            for envelope in envelopes:
                row = self._rows.get(envelope.candidate_id)
                if row is None:
                    continue
                row.envelope = None
                row.reference = None
                row.evidence_state = "recording_failed"
                metadata = dict(row.record.get("job_metadata") or {})
                metadata["recording_error"] = str(reason)
                row.record["job_metadata"] = metadata

    def _release_campaign_lock(self) -> None:
        with self._lock_release_guard:
            self._lock.release()

    def __enter__(self) -> "CampaignSession":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()


def _raw_variables_tuple(
    snapshot: GenerationTaskSnapshot, value: object
) -> tuple[float, ...]:
    if not isinstance(value, Mapping):
        raise TypeError("raw_variables must be a name/value mapping")
    return tuple(float(value[name]) for name in snapshot.parameter_names)


__all__ = ["CampaignSession", "RecorderCounters", "RecordingError"]
