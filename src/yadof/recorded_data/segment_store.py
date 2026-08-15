"""Immutable standard-ZIP segment publication and tolerant discovery."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Iterator, Mapping, Sequence
import zipfile

from ..job_template.rawdata_contract import NamedRawDataItem
from .paths import RecordedDataPaths
from .rawdata import decode_npz, encode_npz
from .utils import json_ready, now_utc_text


SEGMENT_FORMAT = "yadof.recorded-data-segment"
MANIFEST_MEMBER = "manifest.json"


@dataclass(frozen=True, slots=True)
class RecordEnvelope:
    candidate_id: str
    record: Mapping[str, object]
    rawdata_items: tuple[NamedRawDataItem, ...]
    reservation_bytes: int

    @property
    def run_id(self) -> str:
        return str(self.record.get("run_id") or "unscoped")

    @property
    def generation_index(self) -> int | None:
        try:
            return int(self.record["generation_index"])
        except (KeyError, TypeError, ValueError):
            return None


@dataclass(frozen=True, slots=True)
class SegmentReference:
    candidate_id: str
    segment_path: Path
    record: Mapping[str, object]
    rawdata_members: tuple[tuple[str, str, int], ...]


@dataclass(frozen=True, slots=True)
class CatalogSnapshot:
    references: tuple[SegmentReference, ...]
    diagnostics: tuple[dict[str, object], ...]
    segment_paths: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class RawDataBatch:
    """Validated candidate evidence read from one already-open segment."""

    records: tuple[
        tuple[SegmentReference, tuple[NamedRawDataItem, ...]], ...
    ]
    diagnostics: tuple[dict[str, object], ...]


@dataclass(frozen=True, slots=True)
class HistoricalRawDataSnapshot:
    """One stable list of finalized segments for a history interpretation."""

    segment_paths: tuple[Path, ...]
    diagnostics: tuple[dict[str, object], ...]
    status: str | None

    def iter_batches(self) -> Iterator[RawDataBatch]:
        """Open each frozen segment once and yield its valid decoded evidence."""

        return _iter_snapshot_batches(self.segment_paths, self.status)


def candidate_identity(record: Mapping[str, object]) -> str:
    payload = {
        "campaign_id": record.get("campaign_id"),
        "run_id": record.get("run_id"),
        "optimization_index": record.get("optimization_index"),
        "generation_index": record.get("generation_index"),
        "population_index": record.get("population_index"),
        "job_name": record.get("job_name"),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode(
            "utf-8"
        )
    ).hexdigest()


def publish_segment(
    storage: RecordedDataPaths,
    envelopes: Sequence[RecordEnvelope],
    *,
    sequence: int,
) -> tuple[Path, tuple[SegmentReference, ...]]:
    """Publish only new bytes through one temporary ZIP and atomic rename."""

    if not envelopes:
        raise ValueError("cannot publish an empty recorded-data segment")
    first = envelopes[0]
    if any(
        envelope.run_id != first.run_id
        or envelope.generation_index != first.generation_index
        for envelope in envelopes
    ):
        raise ValueError("one segment cannot cross a run or generation boundary")
    if len({envelope.candidate_id for envelope in envelopes}) != len(envelopes):
        raise ValueError("one segment cannot contain duplicate candidate identities")
    directory = _segment_directory(storage, first.run_id, first.generation_index)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"segment_{int(sequence):06d}.zip"
    if destination.exists():
        raise FileExistsError(destination)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f"{destination.name}.", suffix=".tmp", dir=str(directory)
    )
    os.close(fd)
    temporary = Path(temporary_name)
    candidates: list[dict[str, object]] = []
    references: list[SegmentReference] = []
    try:
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_STORED, allowZip64=True
        ) as archive:
            for index, envelope in enumerate(envelopes):
                prefix = f"candidates/{index:06d}_{envelope.candidate_id[:16]}"
                metadata_member = f"{prefix}/metadata.json"
                record = {
                    **dict(envelope.record),
                    "candidate_id": envelope.candidate_id,
                }
                metadata_payload = _json_bytes(record)
                archive.writestr(
                    metadata_member,
                    metadata_payload,
                    compress_type=zipfile.ZIP_DEFLATED,
                    compresslevel=1,
                )
                raw_members: list[dict[str, object]] = []
                reference_members: list[tuple[str, str, int]] = []
                for item in envelope.rawdata_items:
                    member = f"{prefix}/rawdata/{item.filename}"
                    payload = encode_npz(item)
                    archive.writestr(member, payload, compress_type=zipfile.ZIP_STORED)
                    raw_members.append(
                        {
                            "filename": item.filename,
                            "member": member,
                            "size_bytes": len(payload),
                        }
                    )
                    reference_members.append((item.filename, member, len(payload)))
                candidates.append(
                    {
                        "candidate_id": envelope.candidate_id,
                        "metadata_member": metadata_member,
                        "metadata_size_bytes": len(metadata_payload),
                        "rawdata": raw_members,
                    }
                )
                references.append(
                    SegmentReference(
                        envelope.candidate_id,
                        destination,
                        record,
                        tuple(reference_members),
                    )
                )
            manifest = {
                "format": SEGMENT_FORMAT,
                "published_at": now_utc_text(),
                "run_id": first.run_id,
                "generation_index": first.generation_index,
                "candidate_count": len(candidates),
                "candidates": candidates,
            }
            archive.writestr(
                MANIFEST_MEMBER,
                _json_bytes(manifest),
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=1,
            )
        os.replace(temporary, destination)
        return destination, tuple(references)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def discover_catalog(storage: RecordedDataPaths) -> CatalogSnapshot:
    """Take one stable finalized-name snapshot and tolerate every bad segment."""

    paths, snapshot_diagnostics = _finalized_segment_paths(storage)
    if snapshot_diagnostics:
        return CatalogSnapshot((), snapshot_diagnostics, paths)
    references: list[SegmentReference] = []
    diagnostics: list[dict[str, object]] = []
    seen: dict[str, Path] = {}
    for path in paths:
        try:
            segment_refs, segment_diagnostics = scan_segment(path)
        except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
            diagnostics.append(_diagnostic("segment_unreadable", exc, path=path))
            continue
        diagnostics.extend(segment_diagnostics)
        for reference in segment_refs:
            previous = seen.get(reference.candidate_id)
            if previous is not None:
                diagnostics.append(
                    {
                        "error_type": "duplicate_candidate",
                        "candidate_id": reference.candidate_id,
                        "kept_segment": str(previous),
                        "ignored_segment": str(path),
                    }
                )
                continue
            seen[reference.candidate_id] = path
            references.append(reference)
    return CatalogSnapshot(tuple(references), tuple(diagnostics), paths)


def open_historical_rawdata_snapshot(
    storage: RecordedDataPaths,
    *,
    status: str | None = "completed",
) -> HistoricalRawDataSnapshot:
    """Freeze final segment names before one streamed history interpretation."""

    paths, diagnostics = _finalized_segment_paths(storage)
    return HistoricalRawDataSnapshot(paths, diagnostics, status)


def scan_segment(
    path: Path,
) -> tuple[tuple[SegmentReference, ...], tuple[dict[str, object], ...]]:
    """Inspect one segment without decoding its rawData members."""

    with zipfile.ZipFile(path, "r") as archive:
        return _scan_open_segment(path, archive)


def _scan_open_segment(
    path: Path, archive: zipfile.ZipFile
) -> tuple[tuple[SegmentReference, ...], tuple[dict[str, object], ...]]:
    references: list[SegmentReference] = []
    diagnostics: list[dict[str, object]] = []
    manifest = _json_object(archive.read(MANIFEST_MEMBER), "segment manifest")
    if manifest.get("format") != SEGMENT_FORMAT:
        raise ValueError("unsupported recorded-data segment manifest")
    candidates = manifest.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("segment candidates must be a list")
    if int(manifest.get("candidate_count", -1)) != len(candidates):
        raise ValueError("segment candidate count mismatch")
    names = set(archive.namelist())
    for candidate in candidates:
        try:
            if not isinstance(candidate, Mapping):
                raise ValueError("candidate manifest entry must be an object")
            candidate_id = str(candidate["candidate_id"])
            metadata_member = str(candidate["metadata_member"])
            if not metadata_member.startswith(
                "candidates/"
            ) or not metadata_member.endswith("/metadata.json"):
                raise ValueError("invalid candidate metadata member mapping")
            candidate_prefix = metadata_member.removesuffix("/metadata.json")
            if metadata_member not in names:
                raise KeyError(metadata_member)
            metadata_payload = archive.read(metadata_member)
            if len(metadata_payload) != int(
                candidate.get("metadata_size_bytes", -1)
            ):
                raise ValueError("candidate metadata size mismatch")
            record = _json_object(metadata_payload, "candidate metadata")
            if str(record.get("candidate_id")) != candidate_id:
                raise ValueError("candidate identity mismatch")
            raw_entries = candidate.get("rawdata", ())
            if not isinstance(raw_entries, list):
                raise ValueError("candidate rawdata map must be a list")
            raw_members: list[tuple[str, str, int]] = []
            seen_filenames: set[str] = set()
            seen_members: set[str] = set()
            for entry in raw_entries:
                if not isinstance(entry, Mapping):
                    raise ValueError("rawData manifest entry must be an object")
                filename = str(entry["filename"])
                member = str(entry["member"])
                size = int(entry["size_bytes"])
                if Path(filename).name != filename or not filename.lower().endswith(
                    ".npz"
                ):
                    raise ValueError("invalid rawData filename")
                if member != f"{candidate_prefix}/rawdata/{filename}":
                    raise ValueError("invalid candidate rawData member mapping")
                if filename.casefold() in seen_filenames or member in seen_members:
                    raise ValueError("duplicate candidate rawData member mapping")
                seen_filenames.add(filename.casefold())
                seen_members.add(member)
                if member not in names:
                    raise KeyError(member)
                info = archive.getinfo(member)
                if int(info.file_size) != size:
                    raise ValueError("rawData member size mismatch")
                raw_members.append((filename, member, size))
            if list(record.get("rawdata_files", ())) != [
                filename for filename, _member, _size in raw_members
            ]:
                raise ValueError("candidate rawData metadata mismatch")
            references.append(
                SegmentReference(candidate_id, path, record, tuple(raw_members))
            )
        except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
            diagnostics.append(
                _diagnostic(
                    "candidate_unreadable",
                    exc,
                    path=path,
                    candidate_id=(
                        str(candidate.get("candidate_id", ""))
                        if isinstance(candidate, Mapping)
                        else ""
                    ),
                )
            )
    return tuple(references), tuple(diagnostics)


def load_reference_rawdata(
    reference: SegmentReference,
) -> tuple[NamedRawDataItem, ...]:
    with zipfile.ZipFile(reference.segment_path, "r") as archive:
        return _load_reference_rawdata_from_archive(reference, archive)


def _load_reference_rawdata_from_archive(
    reference: SegmentReference, archive: zipfile.ZipFile
) -> tuple[NamedRawDataItem, ...]:
    output: list[NamedRawDataItem] = []
    for filename, member, expected_size in reference.rawdata_members:
        payload = archive.read(member)
        if len(payload) != expected_size:
            raise ValueError(f"rawData member size changed: {member}")
        output.append(NamedRawDataItem(filename, decode_npz(payload)))
    return tuple(output)


def _iter_snapshot_batches(
    paths: Sequence[Path], status: str | None
) -> Iterator[RawDataBatch]:
    seen: dict[str, Path] = {}
    for path in paths:
        records: list[tuple[SegmentReference, tuple[NamedRawDataItem, ...]]] = []
        diagnostics: list[dict[str, object]] = []
        try:
            with zipfile.ZipFile(path, "r") as archive:
                references, scan_diagnostics = _scan_open_segment(path, archive)
                diagnostics.extend(scan_diagnostics)
                for reference in references:
                    previous = seen.get(reference.candidate_id)
                    if previous is not None:
                        diagnostics.append(
                            {
                                "error_type": "duplicate_candidate",
                                "candidate_id": reference.candidate_id,
                                "kept_segment": str(previous),
                                "ignored_segment": str(path),
                            }
                        )
                        continue
                    seen[reference.candidate_id] = path
                    if status is not None and str(
                        reference.record.get("status")
                    ) != status:
                        continue
                    try:
                        items = _load_reference_rawdata_from_archive(reference, archive)
                    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
                        diagnostics.append(
                            _diagnostic(
                                "unreadable_rawdata",
                                exc,
                                path=path,
                                candidate_id=reference.candidate_id,
                            )
                        )
                        continue
                    records.append((reference, items))
        except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
            diagnostics.append(_diagnostic("segment_unreadable", exc, path=path))
        yield RawDataBatch(tuple(records), tuple(diagnostics))


def next_sequence_by_directory(
    storage: RecordedDataPaths,
) -> dict[tuple[str, int | None], int]:
    counters: dict[tuple[str, int | None], int] = {}
    try:
        paths = tuple(storage.segments_directory.rglob("segment_*.zip"))
    except OSError:
        return counters
    for path in paths:
        match = re.fullmatch(r"segment_(\d+)\.zip", path.name)
        if match is None:
            continue
        generation = _generation_from_directory(path.parent.name)
        key = (path.parent.parent.name, generation)
        counters[key] = max(counters.get(key, 0), int(match.group(1)) + 1)
    return counters


def segment_counter_key(
    run_id: str, generation_index: int | None
) -> tuple[str, int | None]:
    return (_safe_component(run_id), generation_index)


def _finalized_segment_paths(
    storage: RecordedDataPaths,
) -> tuple[tuple[Path, ...], tuple[dict[str, object], ...]]:
    try:
        paths = tuple(
            sorted(
                storage.segments_directory.rglob("segment_*.zip"),
                key=lambda item: item.as_posix().casefold(),
            )
        )
    except OSError as exc:
        return (), (_diagnostic("catalog_unreadable", exc),)
    return paths, ()


def _segment_directory(
    storage: RecordedDataPaths, run_id: str, generation_index: int | None
) -> Path:
    generation = (
        "generation_unscoped"
        if generation_index is None
        else f"generation_{int(generation_index):06d}"
    )
    return storage.segments_directory / _safe_component(run_id) / generation


def _safe_component(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("._")
    if not clean:
        clean = "unscoped"
    digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:8]
    return f"{clean[:48]}_{digest}"


def _generation_from_directory(value: str) -> int | None:
    match = re.fullmatch(r"generation_(\d+)", value)
    return int(match.group(1)) if match is not None else None


def _json_bytes(value: object) -> bytes:
    return json.dumps(
        json_ready(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _json_object(payload: bytes, label: str) -> dict[str, object]:
    loaded = json.loads(payload.decode("utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{label} must be an object")
    return loaded


def _diagnostic(
    error_type: str,
    exc: BaseException,
    *,
    path: Path | None = None,
    candidate_id: str | None = None,
) -> dict[str, object]:
    output: dict[str, object] = {
        "error_type": error_type,
        "error_message": f"{type(exc).__name__}: {exc}",
    }
    if path is not None:
        output["path"] = str(path)
    if candidate_id:
        output["candidate_id"] = candidate_id
    return output


__all__ = [
    "CatalogSnapshot",
    "HistoricalRawDataSnapshot",
    "RecordEnvelope",
    "RawDataBatch",
    "SegmentReference",
    "candidate_identity",
    "discover_catalog",
    "load_reference_rawdata",
    "next_sequence_by_directory",
    "open_historical_rawdata_snapshot",
    "publish_segment",
    "scan_segment",
    "segment_counter_key",
]
