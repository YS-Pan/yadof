"""Load and normalize historical optimization rows for the cost viewer."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence as SequenceABC
from typing import Mapping, Sequence

from ...job_template import api as job_template_api
from ...recorded_data import api as recorded_data_api
from .types import ProgressCallback, ViewCostError, WorkspaceLike


def _as_float_tuple(
    values: Sequence[object], *, field_name: str, job_name: str
) -> tuple[float, ...]:
    try:
        out = tuple(float(value) for value in values)
    except (TypeError, ValueError) as exc:
        raise ViewCostError(
            f"{field_name} for job {job_name!r} is not numeric"
        ) from exc
    if not all(math.isfinite(value) for value in out):
        raise ViewCostError(
            f"{field_name} for job {job_name!r} contains non-finite values"
        )
    return out


def _record_issue(issues: list[str] | None, message: str) -> None:
    if issues is not None:
        issues.append(message)


def _metadata_from_record(record: Mapping[str, object]) -> dict[str, object]:
    """Extract display provenance from the record already read with rawData."""

    metadata = record.get("job_metadata")
    row = dict(metadata) if isinstance(metadata, Mapping) else {}
    for key in (
        "run_id",
        "optimization_index",
        "generation_index",
        "population_index",
    ):
        if key in record:
            row[key] = record[key]
    return row


def _opt_metadata_by_job(
    workspace: WorkspaceLike,
    recorded_api=recorded_data_api,
    *,
    issues: list[str] | None = None,
) -> dict[str, dict[str, object]]:
    list_optimization_metadata = getattr(
        recorded_api, "list_optimization_metadata", None
    )
    if list_optimization_metadata is None:
        return {}

    out: dict[str, dict[str, object]] = {}
    run_order: dict[str, int] = {}
    try:
        for row_number, raw_row in enumerate(
            list_optimization_metadata(workspace), start=1
        ):
            if not isinstance(raw_row, Mapping):
                continue
            row = dict(raw_row)
            run_id = str(
                row.get("run_id")
                or row.get("optimization_index")
                or f"run_{row_number}"
            )
            if run_id not in run_order:
                run_order[run_id] = len(run_order) + 1
            created_job_names = row.get("created_job_names", ())
            if isinstance(created_job_names, (str, bytes)) or not isinstance(
                created_job_names, SequenceABC
            ):
                created_job_names = (created_job_names,)
            for job_name_raw in created_job_names:
                if job_name_raw in (None, ""):
                    continue
                out[str(job_name_raw)] = {
                    "optimization_index": run_order[run_id],
                    "optimization_run_id": run_id,
                    "generation_index": _metadata_int(
                        row, "generation_index"
                    ),
                    "started_at": row.get("started_at"),
                    "ended_at": row.get("ended_at"),
                    "source": row.get("source"),
                    "surrogate_used": row.get("surrogate_used"),
                }
    except Exception as exc:  # noqa: BLE001 - annotations must not block costs.
        _record_issue(
            issues,
            f"optimization metadata annotations were ignored: {exc}",
        )
    return out


def _metadata_int(metadata: Mapping[str, object], key: str) -> int | None:
    value = metadata.get(key)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _metadata_str(metadata: Mapping[str, object], key: str) -> str | None:
    value = metadata.get(key)
    if value in (None, ""):
        return None
    return str(value)


def _raw_variables(
    record: Mapping[str, object], names: Sequence[str]
) -> tuple[float, ...]:
    values = record.get("raw_variables")
    if not isinstance(values, Mapping):
        raise TypeError("raw_variables must be a mapping")
    return tuple(float(values[name]) for name in names)


def build_rows(
    workspace: WorkspaceLike,
    *,
    status: str | None = "completed",
    recorded_api=recorded_data_api,
    issues: list[str] | None = None,
    progress: ProgressCallback | None = None,
    objective_names_out: list[str] | None = None,
) -> list[dict[str, object]]:
    """Build display rows in one frozen task/history interpretation pass."""

    open_snapshot = getattr(
        recorded_api, "open_historical_rawdata_snapshot", None
    )
    if not callable(open_snapshot):
        raise ViewCostError(
            "recorded_data.api does not provide "
            "open_historical_rawdata_snapshot()"
        )
    try:
        snapshot = open_snapshot(workspace, status=status)
    except Exception as exc:  # noqa: BLE001 - hide raw internals from CLI.
        raise ViewCostError(
            f"Could not read recorded_data history: {exc}"
        ) from exc

    for diagnostic in snapshot.diagnostics:
        _record_issue(
            issues,
            "recorded row/segment was ignored: "
            f"{diagnostic.get('error_type', 'unknown')}: "
            f"{diagnostic.get('error_message', '')}",
        )

    candidates: list[dict[str, object]] = []
    metadata_by_job: dict[str, dict[str, object]] = {}
    history_row_count = 0
    if progress is not None:
        progress(0, None, "reinterpreting candidates")

    try:
        with job_template_api.task_cost_interpreter(workspace) as interpreter:
            if objective_names_out is not None:
                objective_names_out[:] = list(interpreter.objective_names)
            for batch in snapshot.iter_batches():
                for diagnostic in batch.diagnostics:
                    _record_issue(
                        issues,
                        "recorded row/segment was ignored: "
                        f"{diagnostic.get('error_type', 'unknown')}: "
                        f"{diagnostic.get('error_message', '')}",
                    )

                pending: list[
                    tuple[
                        int,
                        str,
                        tuple[float, ...],
                        tuple[float, ...],
                        tuple[object, ...],
                    ]
                ] = []
                for reference, rawdata_items in batch.records:
                    history_row_count += 1
                    row_number = history_row_count
                    job_name = str(reference.record.get("job_name", ""))
                    try:
                        raw_variables = _raw_variables(
                            reference.record, interpreter.parameter_names
                        )
                        normalized = _as_float_tuple(
                            interpreter.normalize_variables(raw_variables),
                            field_name="variables",
                            job_name=job_name,
                        )
                    except (
                        OSError,
                        ValueError,
                        TypeError,
                        KeyError,
                        ViewCostError,
                    ) as exc:
                        _record_issue(
                            issues,
                            f"recorded row for job {job_name!r} was skipped: {exc}",
                        )
                        continue
                    metadata_by_job[job_name] = _metadata_from_record(
                        reference.record
                    )
                    pending.append(
                        (
                            row_number,
                            job_name,
                            raw_variables,
                            normalized,
                            tuple(item.payload for item in rawdata_items),
                        )
                    )

                def add_costed_row(
                    pending_row: tuple[
                        int,
                        str,
                        tuple[float, ...],
                        tuple[float, ...],
                        tuple[object, ...],
                    ],
                    costs_raw: Sequence[object],
                ) -> None:
                    row_number, job_name, _raw_variables, variables, _sample = (
                        pending_row
                    )
                    try:
                        costs = _as_float_tuple(
                            costs_raw, field_name="costs", job_name=job_name
                        )
                    except ViewCostError as exc:
                        _record_issue(
                            issues, f"history row {row_number} was skipped: {exc}"
                        )
                        return
                    if not costs:
                        _record_issue(
                            issues,
                            f"history row {row_number} for job {job_name!r} "
                            "was skipped: costs are empty",
                        )
                        return
                    try:
                        average_cost = math.fsum(costs) / len(costs)
                    except OverflowError:
                        average_cost = math.inf
                    if not math.isfinite(average_cost):
                        _record_issue(
                            issues,
                            f"history row {row_number} for job {job_name!r} "
                            "was skipped: average cost is non-finite",
                        )
                        return
                    candidates.append(
                        {
                            "row_number": row_number,
                            "job_name": job_name,
                            "variables": variables,
                            "costs": costs,
                            "average_cost": average_cost,
                        }
                    )

                if pending:
                    samples = tuple(row[4] for row in pending)
                    variables = tuple(row[2] for row in pending)
                    try:
                        cost_rows = interpreter.calculate_costs(samples, variables)
                    except (OSError, ValueError, TypeError, KeyError):
                        cost_rows = ()
                        for pending_row, sample, raw_variables in zip(
                            pending, samples, variables
                        ):
                            try:
                                individual = interpreter.calculate_costs(
                                    (sample,), (raw_variables,)
                                )[0]
                            except (OSError, ValueError, TypeError, KeyError) as exc:
                                _record_issue(
                                    issues,
                                    "recorded row for job "
                                    f"{pending_row[1]!r} was skipped: {exc}",
                                )
                            else:
                                add_costed_row(pending_row, individual)
                    if cost_rows:
                        for pending_row, costs in zip(pending, cost_rows):
                            add_costed_row(pending_row, costs)
                if progress is not None:
                    progress(
                        history_row_count, None, "reinterpreting candidates"
                    )
        if progress is not None:
            progress(
                history_row_count,
                history_row_count,
                "reinterpreting candidates",
            )
    except ViewCostError:
        raise
    except Exception as exc:  # noqa: BLE001 - task loading remains one clear error.
        raise ViewCostError(
            f"Could not reinterpret recorded_data history: {exc}"
        ) from exc

    status_text = (
        "all statuses" if status is None else f"status={status!r}"
    )
    if not candidates:
        if history_row_count:
            detail = f" First issue: {issues[0]}" if issues else ""
            raise ViewCostError(
                "No plottable historical results found in recorded_data "
                f"({status_text}).{detail}"
            )
        raise ViewCostError(
            "No completed historical results found in recorded_data "
            f"({status_text})."
        )

    width_counts = Counter(
        len(row["costs"]) for row in candidates  # type: ignore[arg-type]
    )
    objective_count = width_counts.most_common(1)[0][0]
    opt_metadata = _opt_metadata_by_job(
        workspace, recorded_api, issues=issues
    )
    rows: list[dict[str, object]] = []
    for row in candidates:
        costs = row["costs"]
        if len(costs) != objective_count:  # type: ignore[arg-type]
            _record_issue(
                issues,
                f"history row {row['row_number']} for job "
                f"{row['job_name']!r} was skipped: expected "
                f"{objective_count} objectives, got {len(costs)}",  # type: ignore[arg-type]
            )
            continue

        job_name = str(row["job_name"])
        job_metadata = metadata_by_job.get(job_name, {})
        job_opt_metadata = opt_metadata.get(job_name, {})
        optimization_index = _metadata_int(
            job_metadata, "optimization_index"
        )
        if optimization_index is None:
            optimization_index = job_opt_metadata.get("optimization_index")
        generation_index = _metadata_int(job_metadata, "generation_index")
        if generation_index is None:
            generation_index = job_opt_metadata.get("generation_index")
        optimization_run_id = _metadata_str(
            job_metadata, "run_id"
        ) or job_opt_metadata.get("optimization_run_id")
        row.update(
            {
                "optimization_index": optimization_index,
                "optimization_run_id": optimization_run_id,
                "generation_index": generation_index,
                "job_static_hash": _metadata_str(
                    job_metadata, "job_static_hash"
                ),
            }
        )
        rows.append(row)
    return rows


def objective_names(
    workspace: WorkspaceLike,
    rows: Sequence[dict[str, object]],
    objective_api=job_template_api,
) -> list[str]:
    first_costs = rows[0]["costs"]
    objective_count = len(first_costs)  # type: ignore[arg-type]
    get_names = getattr(objective_api, "get_objective_names", None)
    if callable(get_names):
        try:
            names = [str(name) for name in get_names(workspace)]
            if len(names) == objective_count:
                return names
        except Exception:  # noqa: BLE001 - generic labels keep output usable.
            pass
    return [f"objective_{idx + 1}" for idx in range(objective_count)]


__all__ = ["build_rows", "objective_names"]
