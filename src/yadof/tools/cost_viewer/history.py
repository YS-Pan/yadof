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


def _metadata_by_job(
    workspace: WorkspaceLike,
    recorded_api=recorded_data_api,
    *,
    issues: list[str] | None = None,
) -> dict[str, dict[str, object]]:
    list_records = getattr(recorded_api, "list_records", None)
    if list_records is None:
        return {}
    out: dict[str, dict[str, object]] = {}
    try:
        for record in list_records(workspace):
            if not isinstance(record, dict) or "job_name" not in record:
                continue
            metadata = record.get("job_metadata")
            row = dict(metadata) if isinstance(metadata, dict) else {}
            for key in (
                "run_id",
                "optimization_index",
                "generation_index",
                "population_index",
            ):
                if key in record:
                    row[key] = record[key]
            out[str(record["job_name"])] = row
    except Exception as exc:  # noqa: BLE001 - annotations must not block costs.
        _record_issue(
            issues,
            f"individual metadata annotations were ignored: {exc}",
        )
    return out


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


def build_rows(
    workspace: WorkspaceLike,
    *,
    status: str | None = "completed",
    recorded_api=recorded_data_api,
    issues: list[str] | None = None,
    progress: ProgressCallback | None = None,
) -> list[dict[str, object]]:
    """Build display rows from recorded_data using dynamic cost calculation."""

    get_diagnostics = getattr(recorded_api, "get_rawdata_diagnostics", None)
    if callable(get_diagnostics):
        try:
            for diagnostic in get_diagnostics(
                workspace,
                status=status,
                include_valid=False,
            ):
                _record_issue(
                    issues,
                    "recorded row/segment was ignored: "
                    f"{diagnostic.get('error_type', 'unknown')}: "
                    f"{diagnostic.get('error_message', '')}",
                )
        except Exception as exc:  # noqa: BLE001 - diagnostics are optional.
            _record_issue(issues, f"recorded-data diagnostics were unavailable: {exc}")

    get_history = getattr(recorded_api, "get_historical_results", None)
    if get_history is None:
        raise ViewCostError(
            "recorded_data.api does not provide get_historical_results()"
        )
    try:
        history = get_history(
            workspace,
            status=status,
            **({"progress": progress} if progress is not None else {}),
        )
    except ViewCostError:
        raise
    except Exception as exc:  # noqa: BLE001 - hide raw internals from CLI.
        raise ViewCostError(
            f"Could not read recorded_data history: {exc}"
        ) from exc

    candidates: list[dict[str, object]] = []
    history_row_count = 0
    for row_number, item in enumerate(history, start=1):
        history_row_count += 1
        try:
            job_name_raw, variables_raw, costs_raw = item
        except (TypeError, ValueError):
            _record_issue(
                issues,
                f"history row {row_number} was skipped: unexpected row shape",
            )
            continue
        job_name = str(job_name_raw)
        try:
            variables = _as_float_tuple(
                variables_raw, field_name="variables", job_name=job_name
            )
            costs = _as_float_tuple(
                costs_raw, field_name="costs", job_name=job_name
            )
        except ViewCostError as exc:
            _record_issue(
                issues, f"history row {row_number} was skipped: {exc}"
            )
            continue
        if not costs:
            _record_issue(
                issues,
                f"history row {row_number} for job {job_name!r} was skipped: "
                "costs are empty",
            )
            continue
        try:
            average_cost = math.fsum(costs) / len(costs)
        except OverflowError:
            average_cost = math.inf
        if not math.isfinite(average_cost):
            _record_issue(
                issues,
                f"history row {row_number} for job {job_name!r} was skipped: "
                "average cost is non-finite",
            )
            continue
        candidates.append(
            {
                "row_number": row_number,
                "job_name": job_name,
                "variables": variables,
                "costs": costs,
                "average_cost": average_cost,
            }
        )

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
    metadata = _metadata_by_job(workspace, recorded_api, issues=issues)
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
        job_metadata = metadata.get(job_name, {})
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
