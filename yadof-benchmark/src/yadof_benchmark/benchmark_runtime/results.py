"""Generic public-yadof result collection and reporting."""
from __future__ import annotations

import csv
import io
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping

from .contracts import (
    BenchmarkError,
    evidence_notice,
    replication_notice,
    replication_scope,
)
from .progress import active_progress, estimate_run_timing
from .storage import (
    atomic_write_json,
    atomic_write_text,
    json_safe,
    load_run,
    object_digest,
    read_json,
    utc_now,
)


def _evidence(spec: Mapping[str, Any]) -> str:
    workflow = spec.get("workflow", {})
    if not isinstance(workflow, Mapping):
        return "unclassified"
    return str(workflow.get("evidence", "unclassified"))


def _replication_by_comparison(spec: Mapping[str, Any]) -> dict[str, str]:
    workflow = spec.get("workflow", {})
    if not isinstance(workflow, Mapping):
        return {}
    evidence = _evidence(spec)
    output: dict[str, str] = {}
    for item in workflow.get("comparisons", []):
        if not isinstance(item, Mapping):
            continue
        seeds = item.get("seeds", [])
        seed_count = len(seeds) if isinstance(seeds, (list, tuple)) else 0
        output[str(item.get("id", ""))] = str(
            item.get("replication_scope")
            or replication_scope(evidence, seed_count)
        )
    return output


def _replication_summary(spec: Mapping[str, Any]) -> dict[str, Any]:
    by_comparison = _replication_by_comparison(spec)
    scopes = sorted(set(by_comparison.values()))
    return {
        "by_comparison": by_comparison,
        "scopes": scopes,
        "notices": {scope: replication_notice(scope) for scope in scopes},
    }


def _metadata_int(value: Mapping[str, Any], key: str) -> int | None:
    selected = value.get(key)
    if isinstance(selected, bool):
        return None
    try:
        return int(selected)
    except (TypeError, ValueError):
        return None


def _generation_zero_population(
    workspace: Path,
    records: list[Mapping[str, Any]],
    cell: Mapping[str, Any],
    recorded_api,
) -> dict[str, Any]:
    issues: list[str] = []
    generation_zero = [
        item for item in records if _metadata_int(item, "generation_index") == 0
    ]
    expected = int(cell["population"])
    try:
        normalized = {
            str(name): tuple(float(value) for value in values)
            for name, values in recorded_api.get_normalized_variables(
                workspace, status=None
            )
        }
    except Exception as exc:
        normalized = {}
        issues.append(f"generation-0 normalized population unavailable: {exc}")

    indexed: list[tuple[int, str, tuple[float, ...]]] = []
    for record in generation_zero:
        name = str(record.get("job_name", ""))
        population_index = _metadata_int(record, "population_index")
        values = normalized.get(name)
        if population_index is None:
            issues.append(f"generation-0 record {name!r} has no population_index")
            continue
        if values is None:
            issues.append(f"generation-0 record {name!r} has no normalized variables")
            continue
        if not values or not all(math.isfinite(value) for value in values):
            issues.append(
                f"generation-0 record {name!r} has non-finite normalized variables"
            )
            continue
        indexed.append((population_index, name, values))

    indexed.sort(key=lambda item: (item[0], item[1]))
    observed_indices = [item[0] for item in indexed]
    if len(generation_zero) != expected:
        issues.append(
            "generation-0 attempted population count differs from the planned "
            f"population: expected {expected}, observed {len(generation_zero)}"
        )
    if observed_indices != list(range(expected)):
        issues.append(
            "generation-0 population_index values are not the complete ordered "
            f"range 0..{max(0, expected - 1)}"
        )
    widths = {len(item[2]) for item in indexed}
    if len(widths) > 1:
        issues.append("generation-0 normalized variable widths do not match")
    complete = not issues
    return {
        "expected": expected,
        "observed": len(generation_zero),
        "complete": complete,
        "fingerprint": (
            object_digest([list(item[2]) for item in indexed]) if complete else None
        ),
        "issues": issues,
    }


def _hypervolume_metrics(
    records: list[Mapping[str, Any]],
    rows: list[Mapping[str, Any]],
    cost_viewer,
) -> tuple[dict[str, Any], list[str]]:
    issues: list[str] = []
    attempted_by_generation: Counter[int] = Counter()
    completed_by_generation: Counter[int] = Counter()
    for item in records:
        generation = _metadata_int(item, "generation_index")
        if generation is None:
            issues.append(
                f"attempted record {item.get('job_name', '')!r} has no generation_index"
            )
            continue
        attempted_by_generation[generation] += 1
        if str(item.get("status")) == "completed":
            completed_by_generation[generation] += 1

    finite_by_generation: Counter[int] = Counter()
    finite_generation_order: list[int] = []
    for row in rows:
        generation = _metadata_int(row, "generation_index")
        if generation is None:
            issues.append(
                f"finite cost row {row.get('job_name', '')!r} has no generation_index"
            )
            continue
        finite_by_generation[generation] += 1
        if generation not in finite_generation_order:
            finite_generation_order.append(generation)

    cumulative_by_generation: dict[int, float] = {}
    current_by_generation: dict[int, float] = {}
    reference_point: list[float] | None = None
    if rows:
        try:
            _axis, cumulative, current, reference = cost_viewer.hypervolume_series(
                rows
            )
            if len(cumulative) != len(finite_generation_order):
                issues.append(
                    "hypervolume generation groups do not align with finite cost rows"
                )
            else:
                cumulative_by_generation = {
                    generation: float(value)
                    for generation, value in zip(finite_generation_order, cumulative)
                }
                current_by_generation = {
                    generation: float(value)
                    for generation, value in zip(finite_generation_order, current)
                }
                reference_point = [float(value) for value in reference]
        except Exception as exc:
            issues.append(f"hypervolume unavailable: {exc}")

    trajectory: list[dict[str, Any]] = []
    attempted = completed = finite = 0
    last_cumulative: float | None = 0.0 if cumulative_by_generation else None
    for generation in sorted(attempted_by_generation):
        attempted += int(attempted_by_generation[generation])
        completed += int(completed_by_generation[generation])
        finite += int(finite_by_generation[generation])
        if generation in cumulative_by_generation:
            last_cumulative = cumulative_by_generation[generation]
        trajectory.append(
            {
                "generation": generation,
                "attempted_evaluations": attempted,
                "completed_evaluations": completed,
                "finite_evaluations": finite,
                "cumulative_hypervolume": last_cumulative,
                "generation_hypervolume": current_by_generation.get(
                    generation, 0.0 if last_cumulative is not None else None
                ),
            }
        )

    auc: float | None = None
    auc_normalized: float | None = None
    if trajectory and all(
        item["cumulative_hypervolume"] is not None for item in trajectory
    ):
        area = 0.0
        previous_x = 0
        previous_y = 0.0
        for item in trajectory:
            current_x = int(item["attempted_evaluations"])
            current_y = float(item["cumulative_hypervolume"])
            area += (previous_y + current_y) * 0.5 * (current_x - previous_x)
            previous_x, previous_y = current_x, current_y
        auc = area
        auc_normalized = area / previous_x if previous_x else None
    return (
        {
            "alignment": "attempted_real_evaluations",
            "reference_point": reference_point,
            "trajectory": trajectory,
            "auc": auc,
            "auc_normalized": auc_normalized,
            "final": (
                None
                if not trajectory
                else trajectory[-1]["cumulative_hypervolume"]
            ),
        },
        issues,
    )


def _surrogate_training_summary(
    events: list[Mapping[str, Any]],
    representative_generation_seconds: float | None,
) -> dict[str, Any]:
    durations = [
        float(item["duration_sec"])
        for item in events
        if str(item.get("status")) == "completed"
        and isinstance(item.get("duration_sec"), (int, float))
        and not isinstance(item.get("duration_sec"), bool)
        and math.isfinite(float(item["duration_sec"]))
        and float(item["duration_sec"]) >= 0.0
    ]
    failed = sum(str(item.get("status")) != "completed" for item in events)
    maximum = max(durations) if durations else None
    reference = (
        None
        if representative_generation_seconds is None
        else float(representative_generation_seconds)
    )
    return {
        "event_count": len(events),
        "completed_events": sum(
            str(item.get("status")) == "completed" for item in events
        ),
        "failed_events": failed,
        "duration_sample_count": len(durations),
        "total_duration_seconds": sum(durations) if durations else None,
        "median_duration_seconds": (
            statistics.median(durations) if durations else None
        ),
        "maximum_duration_seconds": maximum,
        "representative_generation_seconds": reference,
        "maximum_fraction_of_representative_generation": (
            None if maximum is None or reference is None else maximum / reference
        ),
        "all_completed_within_representative_generation": (
            None if maximum is None or reference is None else maximum <= reference
        ),
        "notice": (
            "The reference is an explicitly configured representative expensive "
            "real-evaluation generation, not the cheap benchmark cell generation "
            "runtime and not an automatic acceptance decision."
        ),
    }


def _rawdata_shapes(
    workspace: Path,
    records: list[Mapping[str, Any]],
) -> dict[str, list[int]]:
    from yadof.job_template.rawdata_contract import load_rawdata_views
    from yadof.recorded_data import get_rawdata_samples

    completed = [item for item in records if item.get("status") == "completed"]
    if not completed:
        return {}
    name = str(completed[-1].get("job_name", ""))
    samples = get_rawdata_samples(workspace, job_names=[name], status="completed")
    if not samples:
        return {}
    return {
        view.name: [int(size) for size in view.data.shape]
        for view in load_rawdata_views(samples[-1][1])
    }


def collect_cell(workspace: Path, cell: Mapping[str, Any]) -> dict[str, Any]:
    """Collect one cell through public yadof APIs without classifying its strategy."""
    from yadof import recorded_data
    from yadof.tools import cost_viewer

    issues: list[str] = []
    try:
        records = list(recorded_data.list_records(workspace))
    except Exception as exc:
        raise BenchmarkError(f"public record collection failed: {exc}") from exc
    try:
        extensions = list(recorded_data.list_optimization_metadata(workspace))
    except Exception as exc:
        extensions = []
        issues.append(f"optimization metadata unavailable: {exc}")
    objective_names: list[str] = []
    try:
        rows = cost_viewer.build_rows(
            workspace,
            status="completed",
            issues=issues,
            objective_names_out=objective_names,
        )
        if not objective_names:
            objective_names = cost_viewer.objective_names(workspace, rows)
    except Exception as exc:
        rows = []
        issues.append(f"cost rows unavailable: {exc}")

    hypervolume, hypervolume_issues = _hypervolume_metrics(
        records, rows, cost_viewer
    )
    issues.extend(hypervolume_issues)
    generation_zero = _generation_zero_population(
        workspace, records, cell, recorded_data
    )
    issues.extend(generation_zero["issues"])
    try:
        surrogate_events = list(recorded_data.list_surrogate_metadata(workspace))
    except Exception as exc:
        surrogate_events = []
        issues.append(f"surrogate training metadata unavailable: {exc}")
    surrogate_training = _surrogate_training_summary(
        surrogate_events,
        cell.get("representative_generation_seconds"),
    )
    if surrogate_training["failed_events"]:
        issues.append(
            "surrogate training recorded "
            f"{surrogate_training['failed_events']} failed event(s)"
        )
    try:
        observed_shapes = _rawdata_shapes(workspace, records)
    except Exception as exc:
        observed_shapes = {}
        issues.append(f"rawData shapes unavailable: {exc}")
    status_counts = Counter(str(item.get("status", "unknown")) for item in records)
    planned = int(cell["planned_evaluations"])
    attempted = len(records)
    completed = int(status_counts.get("completed", 0))
    finite = len(rows)
    objective_count = len(rows[0]["costs"]) if rows else 0
    expected_contract = cell.get("contract", {})
    expected_shapes = expected_contract.get("rawdata_shapes", {})
    cost_rows: list[dict[str, Any]] = []
    for row in rows:
        costs = [float(value) for value in row["costs"]]
        names = objective_names if len(objective_names) == len(costs) else [
            f"objective_{index + 1}" for index in range(len(costs))
        ]
        metadata = {
            key: row.get(key)
            for key in ("optimization_index", "optimization_run_id", "job_static_hash")
            if row.get(key) is not None
        }
        cost_rows.append(
            {
                "evidence": cell.get("evidence", "unclassified"),
                "replication_scope": cell.get(
                    "replication_scope", "unclassified"
                ),
                "comparison": cell["comparison"],
                "baseline": cell["baseline"],
                "strategy": cell["strategy"],
                "seed": cell["seed"],
                "population": cell["population"],
                "generations": cell["generations"],
                "job": row.get("job_name"),
                "generation": row.get("generation_index"),
                "objectives": dict(zip(names, costs)),
                "average_objective": row.get("average_cost"),
                "metadata": metadata,
            }
        )
    contract = {
        "objective_count": {
            "expected": expected_contract.get("objective_count"),
            "observed": objective_count,
            "matches": objective_count == expected_contract.get("objective_count"),
        },
        "rawdata_shapes": {
            "expected": expected_shapes,
            "observed": observed_shapes,
            "matches": bool(observed_shapes) and observed_shapes == expected_shapes,
        },
    }
    result = {
        "cell": cell["id"],
        "evidence": cell.get("evidence", "unclassified"),
        "replication_scope": cell.get("replication_scope", "unclassified"),
        "comparison": cell["comparison"],
        "baseline": cell["baseline"],
        "strategy": cell["strategy"],
        "seed": cell["seed"],
        "budget": {
            "population": cell["population"],
            "generations": cell["generations"],
            "planned_evaluations": planned,
        },
        "counts": {
            "planned": planned,
            "attempted": attempted,
            "completed": completed,
            "finite": finite,
        },
        "status_counts": dict(sorted(status_counts.items())),
        "attempted_evaluations": attempted,
        "completed_evaluations": completed,
        "finite_evaluations": finite,
        "generation_zero_population": generation_zero,
        "objective_names": objective_names,
        "hypervolume": hypervolume,
        "final_hypervolume": hypervolume["final"],
        "hypervolume_auc": hypervolume["auc"],
        "hypervolume_auc_normalized": hypervolume["auc_normalized"],
        "surrogate_training": surrogate_training,
        "contract": contract,
        "rows": cost_rows,
        "extensions": {
            "yadof.optimization": extensions,
            "yadof.surrogate_training": surrogate_events,
        },
        "issues": issues,
    }
    return json_safe(result)


def _latest_result(
    run_root: Path,
    cell_state: Mapping[str, Any],
) -> dict[str, Any] | None:
    attempts = cell_state.get("attempts", [])
    if not attempts:
        return None
    value = attempts[-1].get("result")
    if not value:
        return None
    path = run_root / str(value)
    return read_json(path) if path.is_file() else None


def _pairing_summaries(
    spec: Mapping[str, Any],
    cells: Mapping[str, Mapping[str, Any]],
    cell_summaries: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    evidence = _evidence(spec)
    replication = _replication_by_comparison(spec)
    summary_by_cell = {str(item["cell"]): item for item in cell_summaries}
    groups: dict[tuple[str, str, int], list[Mapping[str, Any]]] = defaultdict(list)
    for cell in spec["cells"]:
        groups[
            (
                str(cell["comparison"]),
                str(cell["baseline"]),
                int(cell["seed"]),
            )
        ].append(cell)
    output: list[dict[str, Any]] = []
    for key, members in sorted(groups.items()):
        arms: list[dict[str, Any]] = []
        for cell in members:
            cell_id = str(cell["id"])
            result = cells.get(cell_id)
            summary = summary_by_cell.get(cell_id, {})
            generation_zero = (
                result.get("generation_zero_population", {})
                if isinstance(result, Mapping)
                else {}
            )
            counts = (
                result.get("counts", {}) if isinstance(result, Mapping) else {}
            )
            arms.append(
                {
                    "cell": cell_id,
                    "strategy": cell["strategy"],
                    "task_snapshot": cell.get("baseline_digest"),
                    "planned_evaluations": cell.get("planned_evaluations"),
                    "attempted_evaluations": (
                        counts.get("attempted")
                        if isinstance(counts, Mapping)
                        else None
                    ),
                    "generation_zero_population_fingerprint": (
                        generation_zero.get("fingerprint")
                        if isinstance(generation_zero, Mapping)
                        else None
                    ),
                    "generation_zero_population_complete": bool(
                        isinstance(generation_zero, Mapping)
                        and generation_zero.get("complete")
                    ),
                    "cell_valid": bool(summary.get("valid")),
                }
            )

        task_snapshots = {item["task_snapshot"] for item in arms}
        planned_budgets = {item["planned_evaluations"] for item in arms}
        attempted_budgets = {item["attempted_evaluations"] for item in arms}
        population_fingerprints = {
            item["generation_zero_population_fingerprint"] for item in arms
        }
        checks = {
            "task_snapshot_matches": (
                len(task_snapshots) == 1 and None not in task_snapshots
            ),
            "planned_budget_matches": (
                len(planned_budgets) == 1 and None not in planned_budgets
            ),
            "attempted_budget_matches": (
                len(attempted_budgets) == 1 and None not in attempted_budgets
            ),
            "generation_zero_population_matches": (
                all(item["generation_zero_population_complete"] for item in arms)
                and len(population_fingerprints) == 1
                and None not in population_fingerprints
            ),
            "all_cells_valid": all(item["cell_valid"] for item in arms),
        }
        issues = [
            label.replace("_", " ")
            for label, passed in checks.items()
            if not passed
        ]
        output.append(
            {
                "evidence": evidence,
                "replication_scope": replication.get(key[0], "unclassified"),
                "comparison": key[0],
                "baseline": key[1],
                "seed": key[2],
                "valid": all(checks.values()),
                "checks": checks,
                "issues": issues,
                "arms": arms,
            }
        )
    return output


def _comparisons(
    spec: Mapping[str, Any],
    cells: Mapping[str, Mapping[str, Any]],
    cell_summaries: list[Mapping[str, Any]],
    pairings: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    evidence = _evidence(spec)
    references = {
        str(item["id"]): item.get("reference")
        for item in spec["workflow"]["comparisons"]
    }
    replication = _replication_by_comparison(spec)
    summary_by_cell = {str(item["cell"]): item for item in cell_summaries}
    pairing_by_key = {
        (str(item["comparison"]), str(item["baseline"]), int(item["seed"])): item
        for item in pairings
    }
    groups: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for cell in spec["cells"]:
        key = (
            cell["comparison"],
            cell["baseline"],
            cell["seed"],
            cell["population"],
            cell["generations"],
        )
        groups[key].append(cell)
    output: list[dict[str, Any]] = []
    for key, members in sorted(groups.items()):
        reference = references[str(key[0])]
        reference_spec = next(
            (item for item in members if item["strategy"] == reference), None
        )
        reference_cell = (
            None
            if reference_spec is None
            else cells.get(str(reference_spec["id"]))
        )
        reference_hv = (
            None
            if reference_cell is None
            else reference_cell.get("final_hypervolume")
        )
        pairing = pairing_by_key.get((str(key[0]), str(key[1]), int(key[2])), {})
        pairing_valid = bool(pairing.get("valid"))
        reference_summary = (
            {}
            if reference_spec is None
            else summary_by_cell.get(str(reference_spec["id"]), {})
        )
        reference_eligible = pairing_valid and bool(reference_summary.get("valid"))
        for item_spec in sorted(members, key=lambda value: str(value["strategy"])):
            cell_id = str(item_spec["id"])
            item = cells.get(cell_id, {})
            value = item.get("final_hypervolume")
            summary = summary_by_cell.get(cell_id, {})
            aggregate_eligible = pairing_valid and bool(summary.get("valid"))
            delta = (
                None
                if (
                    value is None
                    or reference_hv is None
                    or not aggregate_eligible
                    or not reference_eligible
                )
                else float(value) - float(reference_hv)
            )
            counts = item.get("counts", {})
            output.append(
                {
                    "cell": cell_id,
                    "evidence": evidence,
                    "replication_scope": replication.get(
                        str(key[0]), "unclassified"
                    ),
                    "comparison": key[0],
                    "baseline": key[1],
                    "seed": key[2],
                    "population": key[3],
                    "generations": key[4],
                    "strategy": item_spec["strategy"],
                    "reference": reference,
                    "cell_valid": bool(summary.get("valid")),
                    "pairing_valid": pairing_valid,
                    "aggregate_eligible": aggregate_eligible,
                    "attempted_evaluations": (
                        counts.get("attempted")
                        if isinstance(counts, Mapping)
                        else item.get("attempted_evaluations")
                    ),
                    "completed_evaluations": item.get("completed_evaluations"),
                    "finite_evaluations": item.get("finite_evaluations"),
                    "planned_evaluations": item_spec.get("planned_evaluations"),
                    "final_hypervolume": value,
                    "hypervolume_auc": item.get("hypervolume_auc"),
                    "hypervolume_auc_normalized": item.get(
                        "hypervolume_auc_normalized"
                    ),
                    "surrogate_training": item.get("surrogate_training"),
                    "reference_delta": delta,
                }
            )
    return output


def _metric_summary(values: list[float]) -> dict[str, Any]:
    return {
        "count": len(values),
        "mean": statistics.fmean(values) if values else None,
        "median": statistics.median(values) if values else None,
        "minimum": min(values) if values else None,
        "maximum": max(values) if values else None,
    }


def _cross_seed_aggregates(
    comparisons: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for item in comparisons:
        groups[
            (
                item["evidence"],
                item["replication_scope"],
                item["comparison"],
                item["baseline"],
                item["strategy"],
                item["population"],
                item["generations"],
            )
        ].append(item)
    output: list[dict[str, Any]] = []
    for key, rows in sorted(groups.items()):
        eligible = [item for item in rows if item.get("aggregate_eligible")]
        excluded = [item for item in rows if not item.get("aggregate_eligible")]
        final_hv = [
            float(item["final_hypervolume"])
            for item in eligible
            if item.get("final_hypervolume") is not None
        ]
        normalized_auc = [
            float(item["hypervolume_auc_normalized"])
            for item in eligible
            if item.get("hypervolume_auc_normalized") is not None
        ]
        output.append(
            {
                "evidence": key[0],
                "replication_scope": key[1],
                "comparison": key[2],
                "baseline": key[3],
                "strategy": key[4],
                "population": key[5],
                "generations": key[6],
                "seed_count_total": len(rows),
                "seed_count_included": len(eligible),
                "included_seeds": sorted(int(item["seed"]) for item in eligible),
                "excluded_seeds": sorted(int(item["seed"]) for item in excluded),
                "counts": {
                    name: sum(int(item.get(name) or 0) for item in eligible)
                    for name in (
                        "planned_evaluations",
                        "attempted_evaluations",
                        "completed_evaluations",
                        "finite_evaluations",
                    )
                },
                "final_hypervolume": _metric_summary(final_hv),
                "hypervolume_auc_normalized": _metric_summary(normalized_auc),
                "notice": (
                    "Only valid, complete cells from valid paired case/seed groups "
                    "are included. Excluded seed evidence remains in cell results."
                ),
            }
        )
    return output


def _csv_text(rows: list[Mapping[str, Any]]) -> str:
    fields = [
        "evidence", "replication_scope", "comparison", "baseline", "strategy",
        "seed", "population", "generations", "job", "generation", "objectives",
        "average_objective", "metadata",
    ]
    return _table_csv(rows, fields)


def _table_csv(rows: list[Mapping[str, Any]], fields: list[str]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        value = dict(row)
        for key, item in list(value.items()):
            if isinstance(item, (dict, list, tuple)):
                value[key] = json.dumps(
                    item,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
        writer.writerow({field: value.get(field) for field in fields})
    return stream.getvalue()


def _cell_summaries(
    spec: Mapping[str, Any],
    state: Mapping[str, Any],
    cells: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    evidence = _evidence(spec)
    output: list[dict[str, Any]] = []
    for cell in spec["cells"]:
        cell_id = str(cell["id"])
        cell_state = state["cells"][cell_id]
        result = cells.get(cell_id)
        contract = {} if result is None else result.get("contract", {})
        objective_contract = (
            contract.get("objective_count", {})
            if isinstance(contract, Mapping)
            else {}
        )
        rawdata_contract = (
            contract.get("rawdata_shapes", {})
            if isinstance(contract, Mapping)
            else {}
        )
        objective_match = bool(
            isinstance(objective_contract, Mapping)
            and objective_contract.get("matches")
        )
        rawdata_match = bool(
            isinstance(rawdata_contract, Mapping)
            and rawdata_contract.get("matches")
        )
        issues = [] if result is None else list(result.get("issues", []))
        completed = cell_state.get("status") == "collected"
        counts = result.get("counts", {}) if isinstance(result, Mapping) else {}
        planned = int(cell.get("planned_evaluations", 0))
        attempted = counts.get("attempted") if isinstance(counts, Mapping) else None
        completed_evaluations = (
            counts.get("completed") if isinstance(counts, Mapping) else None
        )
        finite = counts.get("finite") if isinstance(counts, Mapping) else None
        counts_complete = (
            attempted == planned
            and completed_evaluations == attempted
            and finite == completed_evaluations
        )
        generation_zero = (
            result.get("generation_zero_population", {})
            if isinstance(result, Mapping)
            else {}
        )
        generation_zero_complete = bool(
            isinstance(generation_zero, Mapping)
            and generation_zero.get("complete")
        )
        output.append(
            {
                "evidence": evidence,
                "replication_scope": cell.get(
                    "replication_scope", "unclassified"
                ),
                "cell": cell_id,
                "comparison": cell["comparison"],
                "baseline": cell["baseline"],
                "strategy": cell["strategy"],
                "seed": cell["seed"],
                "status": cell_state.get("status"),
                "completed": completed,
                "valid": (
                    completed
                    and objective_match
                    and rawdata_match
                    and counts_complete
                    and generation_zero_complete
                    and not issues
                ),
                "objective_contract_matches": objective_match,
                "rawdata_contract_matches": rawdata_match,
                "counts_complete": counts_complete,
                "generation_zero_population_complete": generation_zero_complete,
                "generation_zero_population_fingerprint": (
                    generation_zero.get("fingerprint")
                    if isinstance(generation_zero, Mapping)
                    else None
                ),
                "attempted_evaluations": attempted,
                "completed_evaluations": completed_evaluations,
                "finite_evaluations": finite,
                "planned_evaluations": planned,
                "issues": issues,
                "error": cell_state.get("error"),
            }
        )
    return output


def _markdown(
    run_id: str,
    evidence: str,
    replication: Mapping[str, Any],
    state: Mapping[str, Any],
    comparisons: list[Mapping[str, Any]],
    cells: list[Mapping[str, Any]],
    pairings: list[Mapping[str, Any]],
    aggregates: list[Mapping[str, Any]],
) -> str:
    lines = [
        f"# Benchmark run {run_id}",
        "",
        f"Status: `{state['status']}`",
        "",
        f"Evidence class: `{evidence}`",
        "",
        f"> {evidence_notice(evidence)}",
        "",
        "## Seed replication scope",
        "",
    ]
    for comparison, scope in sorted(replication.get("by_comparison", {}).items()):
        lines.append(
            f"- `{comparison}`: `{scope}` — {replication_notice(str(scope))}"
        )
    lines.extend([
        "",
        "## Cell completion and validity",
        "",
        "| Cell | Status | Completed | Valid | Planned/attempted/completed/finite | Initial population | Objective contract | rawData contract | Issues |",
        "| --- | --- | --- | --- | ---: | --- | --- | --- | ---: |",
    ])
    for row in cells:
        lines.append(
            "| `{cell}` | {status} | {completed} | {valid} | {planned}/{attempted}/{done}/{finite} | {population} | {objective} | {rawdata} | {issues} |".format(
                cell=str(row["cell"]).replace("|", "\\|"),
                status=row.get("status"),
                completed="yes" if row.get("completed") else "no",
                valid="yes" if row.get("valid") else "no",
                done=row.get("completed_evaluations", "—"),
                attempted=row.get("attempted_evaluations", "—"),
                finite=row.get("finite_evaluations", "—"),
                planned=row.get("planned_evaluations", "—"),
                population=(
                    "complete"
                    if row.get("generation_zero_population_complete")
                    else "incomplete"
                ),
                objective="match" if row.get("objective_contract_matches") else "mismatch",
                rawdata="match" if row.get("rawdata_contract_matches") else "mismatch",
                issues=len(row.get("issues", [])),
            )
        )
    lines.extend(
        [
            "",
            "## Final hypervolume",
            "",
            "| Comparison | Baseline | Seed | Strategy | P/A/C/F | Pair valid | Aggregate eligible | Final hypervolume | HV-AUC/evaluation | Reference delta |",
            "| --- | --- | ---: | --- | ---: | --- | --- | ---: | ---: | ---: |",
        ]
    )
    for row in comparisons:
        hv = row.get("final_hypervolume")
        delta = row.get("reference_delta")
        auc = row.get("hypervolume_auc_normalized")
        lines.append(
            "| {comparison} | {baseline} | {seed} | {strategy} | {planned}/{attempted}/{done}/{finite} | {paired} | {eligible} | {hv} | {auc} | {delta} |".format(
                comparison=str(row["comparison"]).replace("|", "\\|"),
                baseline=str(row["baseline"]).replace("|", "\\|"),
                seed=row["seed"],
                strategy=str(row["strategy"]).replace("|", "\\|"),
                done=row.get("completed_evaluations", "—"),
                attempted=row.get("attempted_evaluations", "—"),
                finite=row.get("finite_evaluations", "—"),
                planned=row.get("planned_evaluations", "—"),
                paired="yes" if row.get("pairing_valid") else "no",
                eligible="yes" if row.get("aggregate_eligible") else "no",
                hv="—" if hv is None else f"{float(hv):.8g}",
                auc="—" if auc is None else f"{float(auc):.8g}",
                delta="—" if delta is None else f"{float(delta):+.8g}",
            )
        )
    lines.extend(
        [
            "",
            "## Paired fairness",
            "",
            "| Comparison | Baseline | Seed | Valid | Task snapshot | Planned budget | Attempted budget | Generation-0 population | All cells valid |",
            "| --- | --- | ---: | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in pairings:
        checks = row.get("checks", {})
        lines.append(
            "| {comparison} | {baseline} | {seed} | {valid} | {task} | {planned} | {attempted} | {population} | {cells} |".format(
                comparison=str(row["comparison"]).replace("|", "\\|"),
                baseline=str(row["baseline"]).replace("|", "\\|"),
                seed=row["seed"],
                valid="yes" if row.get("valid") else "no",
                task="match" if checks.get("task_snapshot_matches") else "mismatch",
                planned="match" if checks.get("planned_budget_matches") else "mismatch",
                attempted="match" if checks.get("attempted_budget_matches") else "mismatch",
                population=(
                    "match"
                    if checks.get("generation_zero_population_matches")
                    else "mismatch"
                ),
                cells="yes" if checks.get("all_cells_valid") else "no",
            )
        )
    lines.extend(
        [
            "",
            "## Cross-seed descriptive aggregates",
            "",
            "| Comparison | Baseline | Strategy | Included seeds | Excluded seeds | Mean final HV | Mean HV-AUC/evaluation |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in aggregates:
        hv = row.get("final_hypervolume", {})
        auc = row.get("hypervolume_auc_normalized", {})
        lines.append(
            "| {comparison} | {baseline} | {strategy} | {included}/{total} | {excluded} | {hv} | {auc} |".format(
                comparison=str(row["comparison"]).replace("|", "\\|"),
                baseline=str(row["baseline"]).replace("|", "\\|"),
                strategy=str(row["strategy"]).replace("|", "\\|"),
                included=row.get("seed_count_included", 0),
                total=row.get("seed_count_total", 0),
                excluded=",".join(str(value) for value in row.get("excluded_seeds", [])) or "—",
                hv="—" if hv.get("mean") is None else f"{float(hv['mean']):.8g}",
                auc="—" if auc.get("mean") is None else f"{float(auc['mean']):.8g}",
            )
        )
    training_rows = [
        row
        for row in comparisons
        if isinstance(row.get("surrogate_training"), Mapping)
        and row["surrogate_training"].get("event_count")
    ]
    lines.extend(
        [
            "",
            "## Surrogate training time",
            "",
            "| Baseline | Seed | Strategy | Completed/failed events | Median (s) | Maximum (s) | Representative expensive generation (s) | Maximum/reference |",
            "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in training_rows:
        training = row["surrogate_training"]
        median = training.get("median_duration_seconds")
        maximum = training.get("maximum_duration_seconds")
        reference = training.get("representative_generation_seconds")
        fraction = training.get("maximum_fraction_of_representative_generation")
        lines.append(
            "| {baseline} | {seed} | {strategy} | {completed}/{failed} | {median} | {maximum} | {reference} | {fraction} |".format(
                baseline=str(row["baseline"]).replace("|", "\\|"),
                seed=row["seed"],
                strategy=str(row["strategy"]).replace("|", "\\|"),
                completed=training.get("completed_events", 0),
                failed=training.get("failed_events", 0),
                median="—" if median is None else f"{float(median):.3f}",
                maximum="—" if maximum is None else f"{float(maximum):.3f}",
                reference="—" if reference is None else f"{float(reference):.3f}",
                fraction="—" if fraction is None else f"{float(fraction):.3f}",
            )
        )
    if not training_rows:
        lines.append("| — | — | No surrogate training events were recorded. | — | — | — | — | — |")
    lines.extend(
        [
            "",
            "Values are descriptive observations. This report does not rank strategies, "
            "apply significance tests, or make scientific acceptance decisions.",
            "",
        ]
    )
    incomplete = [
        (cell_id, cell)
        for cell_id, cell in state["cells"].items()
        if cell.get("status") != "collected"
    ]
    if incomplete:
        lines.extend(["", "## Incomplete cells", ""])
        for cell_id, cell in incomplete:
            lines.append(
                f"- `{cell_id}`: {cell.get('status')} — "
                f"{cell.get('error') or 'no error detail'}"
            )
        lines.append("")
    return "\n".join(lines)


def _publish_workspace_indexes(
    run_root: Path,
    spec: Mapping[str, Any],
    state: Mapping[str, Any],
) -> None:
    workspace = Path(str(spec["workflow"]["workspace"])).resolve()
    if not (workspace / ".benchmark" / "workspace.json").is_file():
        return
    run_id = str(state["run_id"])
    payload = {
        "format": "yadof.benchmark.workspace-run-index",
        "run_id": run_id,
        "status": state["status"],
        "evidence": _evidence(spec),
        "replication": _replication_summary(spec),
        "updated_utc": state["updated_utc"],
        "run": str(run_root),
        "reports": str(run_root / "reports"),
        "visualizations": str(run_root / "visualizations"),
    }
    report_index = workspace / "reports" / run_id
    visualization_index = workspace / "visualizations" / run_id
    report_index.mkdir(parents=True, exist_ok=True)
    visualization_index.mkdir(parents=True, exist_ok=True)
    atomic_write_json(report_index / "index.json", payload)
    atomic_write_text(
        report_index / "README.md",
        "\n".join(
            [
                f"# Benchmark run {run_id}",
                "",
                f"Status: `{state['status']}`",
                "",
                f"Evidence class: `{payload['evidence']}`",
                "",
                f"> {evidence_notice(payload['evidence'])}",
                "",
                "Seed replication scopes: "
                f"`{', '.join(payload['replication']['scopes'])}`",
                "",
                f"Authoritative run root: `{run_root}`",
                "",
                f"Run report: `{run_root / 'reports' / 'summary.md'}`",
                "",
            ]
        ),
    )
    atomic_write_json(visualization_index / "index.json", payload)


def publish_results(
    run_root: Path,
    spec: Mapping[str, Any],
    state: Mapping[str, Any],
) -> dict[str, Any]:
    cells = {
        cell_id: result
        for cell_id, cell_state in state["cells"].items()
        if (result := _latest_result(run_root, cell_state)) is not None
    }
    rows = [
        row
        for cell in cells.values()
        for row in cell.get("rows", [])
        if isinstance(row, Mapping)
    ]
    cell_summaries = _cell_summaries(spec, state, cells)
    pairings = _pairing_summaries(spec, cells, cell_summaries)
    comparisons = _comparisons(spec, cells, cell_summaries, pairings)
    aggregates = _cross_seed_aggregates(comparisons)
    evidence = _evidence(spec)
    replication = _replication_summary(spec)
    result = {
        "format": "yadof.benchmark.results",
        "run_id": state["run_id"],
        "generated_utc": utc_now(),
        "execution_status": state["status"],
        "evidence": {
            "class": evidence,
            "notice": evidence_notice(evidence),
        },
        "replication": replication,
        "cell_states": {
            cell_id: {"status": item.get("status"), "error": item.get("error")}
            for cell_id, item in state["cells"].items()
        },
        "postprocessor_states": {
            item_id: {"status": item.get("status"), "error": item.get("error")}
            for item_id, item in state.get("postprocessors", {}).items()
        },
        "cells": cells,
        "rows": rows,
        "comparisons": comparisons,
        "cell_summaries": cell_summaries,
        "pairings": pairings,
        "cross_seed_aggregates": aggregates,
    }
    atomic_write_json(run_root / "results.json", result)
    atomic_write_text(run_root / "results.csv", _csv_text(rows))
    reports = run_root / "reports"
    atomic_write_text(reports / "summary.md", _markdown(
        str(state["run_id"]), evidence, replication, state, comparisons,
        cell_summaries, pairings, aggregates
    ))
    atomic_write_text(
        reports / "cell-validity.csv",
        _table_csv(
            cell_summaries,
            [
                "evidence", "replication_scope", "cell", "comparison", "baseline",
                "strategy", "seed", "status", "completed", "valid",
                "planned_evaluations", "attempted_evaluations",
                "completed_evaluations", "finite_evaluations", "counts_complete",
                "generation_zero_population_complete",
                "generation_zero_population_fingerprint",
                "objective_contract_matches", "rawdata_contract_matches", "issues",
                "error",
            ],
        ),
    )
    atomic_write_text(
        reports / "final-hypervolume.csv",
        _table_csv(
            comparisons,
            [
                "evidence", "replication_scope", "cell", "comparison", "baseline",
                "seed", "strategy", "reference", "cell_valid", "pairing_valid",
                "aggregate_eligible", "planned_evaluations",
                "attempted_evaluations", "completed_evaluations",
                "finite_evaluations", "final_hypervolume", "hypervolume_auc",
                "hypervolume_auc_normalized", "reference_delta",
            ],
        ),
    )
    trajectory_rows: list[dict[str, Any]] = []
    for cell_id, cell_result in cells.items():
        hypervolume = cell_result.get("hypervolume", {})
        trajectory = (
            hypervolume.get("trajectory", [])
            if isinstance(hypervolume, Mapping)
            else []
        )
        for point in trajectory:
            if not isinstance(point, Mapping):
                continue
            trajectory_rows.append(
                {
                    "cell": cell_id,
                    "evidence": cell_result.get("evidence"),
                    "replication_scope": cell_result.get("replication_scope"),
                    "comparison": cell_result.get("comparison"),
                    "baseline": cell_result.get("baseline"),
                    "strategy": cell_result.get("strategy"),
                    "seed": cell_result.get("seed"),
                    **point,
                }
            )
    atomic_write_text(
        reports / "hypervolume-trajectory.csv",
        _table_csv(
            trajectory_rows,
            [
                "cell", "evidence", "replication_scope", "comparison", "baseline",
                "strategy", "seed", "generation", "attempted_evaluations",
                "completed_evaluations", "finite_evaluations",
                "cumulative_hypervolume", "generation_hypervolume",
            ],
        ),
    )
    pairing_rows = [
        {
            "evidence": item["evidence"],
            "replication_scope": item["replication_scope"],
            "comparison": item["comparison"],
            "baseline": item["baseline"],
            "seed": item["seed"],
            "valid": item["valid"],
            **item["checks"],
            "issues": item["issues"],
            "arms": item["arms"],
        }
        for item in pairings
    ]
    atomic_write_text(
        reports / "pairing-validity.csv",
        _table_csv(
            pairing_rows,
            [
                "evidence", "replication_scope", "comparison", "baseline",
                "seed", "valid",
                "task_snapshot_matches", "planned_budget_matches",
                "attempted_budget_matches", "generation_zero_population_matches",
                "all_cells_valid", "issues", "arms",
            ],
        ),
    )
    atomic_write_text(
        reports / "cross-seed-aggregates.csv",
        _table_csv(
            aggregates,
            [
                "evidence", "replication_scope", "comparison", "baseline",
                "strategy", "population", "generations", "seed_count_total",
                "seed_count_included", "included_seeds", "excluded_seeds",
                "counts", "final_hypervolume", "hypervolume_auc_normalized",
                "notice",
            ],
        ),
    )
    training_rows = [
        {
            key: item.get(key)
            for key in (
                "cell", "evidence", "replication_scope", "comparison", "baseline",
                "strategy", "seed",
            )
        }
        | dict(item["surrogate_training"])
        for item in comparisons
        if isinstance(item.get("surrogate_training"), Mapping)
    ]
    atomic_write_text(
        reports / "surrogate-training.csv",
        _table_csv(
            training_rows,
            [
                "cell", "evidence", "replication_scope", "comparison", "baseline",
                "strategy", "seed", "event_count", "completed_events",
                "failed_events", "duration_sample_count", "total_duration_seconds",
                "median_duration_seconds", "maximum_duration_seconds",
                "representative_generation_seconds",
                "maximum_fraction_of_representative_generation",
                "all_completed_within_representative_generation", "notice",
            ],
        ),
    )
    atomic_write_json(
        reports / "descriptive-results.json",
        {
            "format": "yadof.benchmark.descriptive-results",
            "run_id": state["run_id"],
            "status": state["status"],
            "evidence": result["evidence"],
            "replication": replication,
            "generated_utc": result["generated_utc"],
            "cells": cell_summaries,
            "final_hypervolume": comparisons,
            "pairings": pairings,
            "cross_seed_aggregates": aggregates,
            "hypervolume_trajectories": trajectory_rows,
            "surrogate_training": training_rows,
        },
    )
    _publish_workspace_indexes(run_root, spec, state)
    return result


def inspect_run(run: str | Path) -> dict[str, Any]:
    run_root = Path(run).resolve()
    spec, state = load_run(run_root)
    counts = Counter(str(cell.get("status", "unknown")) for cell in state["cells"].values())
    errors = {
        cell_id: cell.get("error")
        for cell_id, cell in state["cells"].items()
        if cell.get("error")
    }
    errors.update(
        {
            f"postprocessor:{item_id}": item.get("error")
            for item_id, item in state.get("postprocessors", {}).items()
            if item.get("error")
        }
    )
    report_path = run_root / "reports" / "descriptive-results.json"
    report = read_json(report_path) if report_path.is_file() else {}
    legacy_results_path = run_root / "results.json"
    report_source_path = (
        report_path
        if report_path.is_file()
        else legacy_results_path
        if legacy_results_path.is_file()
        else report_path
    )
    reported_cells = (
        list(report.get("cells", []))
        if isinstance(report.get("cells"), list)
        else []
    )
    validity = {
        "completed": sum(bool(item.get("completed")) for item in reported_cells),
        "valid": sum(bool(item.get("valid")) for item in reported_cells),
        "invalid": sum(
            bool(item.get("completed")) and not bool(item.get("valid"))
            for item in reported_cells
        ),
        "incomplete": max(0, len(state["cells"]) - sum(
            bool(item.get("completed")) for item in reported_cells
        )),
    }
    comparison_rows = (
        list(report.get("final_hypervolume", []))
        if isinstance(report.get("final_hypervolume"), list)
        else []
    )
    if not reported_cells or not comparison_rows:
        legacy_results = (
            read_json(legacy_results_path) if legacy_results_path.is_file() else {}
        )
        legacy_cells = legacy_results.get("cells", {})
        if not reported_cells and isinstance(legacy_cells, Mapping):
            reported_cells = _cell_summaries(spec, state, legacy_cells)
            validity = {
                "completed": sum(
                    bool(item.get("completed")) for item in reported_cells
                ),
                "valid": sum(bool(item.get("valid")) for item in reported_cells),
                "invalid": sum(
                    bool(item.get("completed")) and not bool(item.get("valid"))
                    for item in reported_cells
                ),
                "incomplete": max(
                    0,
                    len(state["cells"])
                    - sum(bool(item.get("completed")) for item in reported_cells),
                ),
            }
        legacy_comparisons = legacy_results.get("comparisons", [])
        if not comparison_rows and isinstance(legacy_comparisons, list):
            comparison_rows = legacy_comparisons
    anomalies: list[dict[str, Any]] = [
        {"scope": key, "message": str(value)}
        for key, value in sorted(errors.items())
    ]
    for item in reported_cells:
        issues = item.get("issues", [])
        if isinstance(issues, list):
            anomalies.extend(
                {
                    "scope": str(item.get("cell", "unknown")),
                    "message": str(issue),
                }
                for issue in issues
            )
        if item.get("completed") and not item.get("valid") and not issues:
            anomalies.append(
                {
                    "scope": str(item.get("cell", "unknown")),
                    "message": "collected cell did not satisfy its validity contract",
                }
            )
    active = active_progress(run_root, state)
    inspect_command = [
        "yadof-benchmark", "inspect", "--run", str(run_root)
    ]
    next_commands: dict[str, list[str]] = {"inspect_later": inspect_command}
    if state["status"] in {"failed", "planned"} and active is None:
        next_commands["resume"] = [
            "yadof-benchmark", "resume", "--run", str(run_root)
        ]
    progressive = [
        {"step": "inspect", "path": None},
        {
            "step": "report_markdown",
            "path": str(run_root / "reports" / "summary.md"),
        },
        {
            "step": (
                "report_json"
                if report_source_path == report_path
                else "legacy_results_json"
            ),
            "path": str(report_source_path),
        },
    ]
    if active is not None:
        logs = active.get("logs", {})
        if isinstance(logs, Mapping):
            for name in ("stdout", "stderr"):
                if logs.get(name):
                    progressive.append(
                        {"step": f"active_cell_{name}", "path": logs[name]}
                    )
    if legacy_results_path != report_source_path:
        progressive.append(
            {
                "step": "targeted_metrics_fields",
                "path": str(legacy_results_path),
            }
        )
    postprocessor_counts = Counter(
        str(item.get("status", "unknown"))
        for item in state.get("postprocessors", {}).values()
    )
    evidence = _evidence(spec)
    replication = _replication_summary(spec)
    return {
        "format": "yadof.benchmark.inspect",
        "run_id": state["run_id"],
        "run": str(run_root),
        "workflow": spec["workflow"]["name"],
        "evidence": {
            "class": evidence,
            "notice": evidence_notice(evidence),
        },
        "replication": replication,
        "status": state["status"],
        "updated_utc": state["updated_utc"],
        "cell_counts": dict(sorted(counts.items())),
        "postprocessor_counts": dict(sorted(postprocessor_counts.items())),
        "active": active,
        "timing": estimate_run_timing(run_root, spec, state),
        "validity": validity,
        "comparison": {
            "rows": len(comparison_rows),
            "final_hypervolume_available": sum(
                item.get("final_hypervolume") is not None
                for item in comparison_rows
            ),
            "reference_deltas_available": sum(
                item.get("reference_delta") is not None
                for item in comparison_rows
            ),
            "hypervolume_auc_available": sum(
                item.get("hypervolume_auc_normalized") is not None
                for item in comparison_rows
            ),
            "paired_valid_rows": sum(
                bool(item.get("pairing_valid")) for item in comparison_rows
            ),
            "aggregate_eligible_rows": sum(
                bool(item.get("aggregate_eligible")) for item in comparison_rows
            ),
            "report": str(report_source_path),
        },
        "anomalies": anomalies[:8],
        "anomalies_truncated": max(0, len(anomalies) - 8),
        "next_commands": next_commands,
        "progressive_disclosure": progressive,
        "artifacts": {
            name: str(run_root / name)
            for name in (
                "spec.json", "state.json", "results.json", "results.csv",
                "reports/summary.md", "reports/cell-validity.csv",
                "reports/final-hypervolume.csv",
                "reports/hypervolume-trajectory.csv",
                "reports/pairing-validity.csv",
                "reports/cross-seed-aggregates.csv",
                "reports/surrogate-training.csv",
                "reports/descriptive-results.json",
                "visualizations", "benchmark.log", "timing_history.json",
            )
            if (run_root / name).is_file()
            or (run_root / name).is_dir()
        },
    }


__all__ = ["collect_cell", "inspect_run", "publish_results"]
