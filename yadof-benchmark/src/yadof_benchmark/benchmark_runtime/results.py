"""Generic public-yadof result collection and reporting."""
from __future__ import annotations

import csv
import io
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping

from .contracts import BenchmarkError
from .progress import active_progress
from .storage import (
    atomic_write_json,
    atomic_write_text,
    json_safe,
    load_run,
    read_json,
    utc_now,
)


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

    final_hypervolume: float | None = None
    if rows:
        try:
            _axis, cumulative, _current, _reference = cost_viewer.hypervolume_series(rows)
            if len(cumulative):
                final_hypervolume = float(cumulative[-1])
        except Exception as exc:
            issues.append(f"hypervolume unavailable: {exc}")
    try:
        observed_shapes = _rawdata_shapes(workspace, records)
    except Exception as exc:
        observed_shapes = {}
        issues.append(f"rawData shapes unavailable: {exc}")
    status_counts = Counter(str(item.get("status", "unknown")) for item in records)
    planned = int(cell["planned_evaluations"])
    completed = int(status_counts.get("completed", 0))
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
        "comparison": cell["comparison"],
        "baseline": cell["baseline"],
        "strategy": cell["strategy"],
        "seed": cell["seed"],
        "budget": {
            "population": cell["population"],
            "generations": cell["generations"],
            "planned_evaluations": planned,
        },
        "status_counts": dict(sorted(status_counts.items())),
        "completed_evaluations": completed,
        "success_rate": completed / planned if planned else None,
        "objective_names": objective_names,
        "final_hypervolume": final_hypervolume,
        "contract": contract,
        "rows": cost_rows,
        "extensions": {"yadof.optimization": extensions},
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


def _comparisons(
    spec: Mapping[str, Any],
    cells: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    references = {
        str(item["id"]): item.get("reference")
        for item in spec["workflow"]["comparisons"]
    }
    groups: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for cell in cells.values():
        budget = cell["budget"]
        key = (
            cell["comparison"],
            cell["baseline"],
            cell["seed"],
            budget["population"],
            budget["generations"],
        )
        groups[key].append(cell)
    output: list[dict[str, Any]] = []
    for key, members in sorted(groups.items()):
        reference = references[str(key[0])]
        reference_cell = next(
            (item for item in members if item["strategy"] == reference), None
        )
        reference_hv = None if reference_cell is None else reference_cell.get(
            "final_hypervolume"
        )
        for item in sorted(members, key=lambda value: str(value["strategy"])):
            value = item.get("final_hypervolume")
            delta = (
                None
                if value is None or reference_hv is None
                else float(value) - float(reference_hv)
            )
            output.append(
                {
                    "comparison": key[0],
                    "baseline": key[1],
                    "seed": key[2],
                    "population": key[3],
                    "generations": key[4],
                    "strategy": item["strategy"],
                    "reference": reference,
                    "completed_evaluations": item.get("completed_evaluations"),
                    "planned_evaluations": item.get("budget", {}).get(
                        "planned_evaluations"
                    ),
                    "success_rate": item.get("success_rate"),
                    "runtime_seconds": item.get("runtime_seconds"),
                    "final_hypervolume": value,
                    "reference_delta": delta,
                }
            )
    return output


def _csv_text(rows: list[Mapping[str, Any]]) -> str:
    stream = io.StringIO(newline="")
    fields = [
        "comparison", "baseline", "strategy", "seed", "population",
        "generations", "job", "generation", "objectives", "average_objective",
        "metadata",
    ]
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        value = dict(row)
        for field in ("objectives", "metadata"):
            value[field] = json.dumps(
                value.get(field, {}),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        writer.writerow({field: value.get(field) for field in fields})
    return stream.getvalue()


def _markdown(
    run_id: str,
    state: Mapping[str, Any],
    comparisons: list[Mapping[str, Any]],
) -> str:
    lines = [
        f"# Benchmark run {run_id}",
        "",
        f"Status: `{state['status']}`",
        "",
        "| Comparison | Baseline | Seed | Strategy | Evaluations | Success | Runtime (s) | Final hypervolume | Reference delta |",
        "| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in comparisons:
        hv = row.get("final_hypervolume")
        delta = row.get("reference_delta")
        rate = row.get("success_rate")
        runtime = row.get("runtime_seconds")
        lines.append(
            "| {comparison} | {baseline} | {seed} | {strategy} | {done}/{planned} | {rate} | {runtime} | {hv} | {delta} |".format(
                comparison=str(row["comparison"]).replace("|", "\\|"),
                baseline=str(row["baseline"]).replace("|", "\\|"),
                seed=row["seed"],
                strategy=str(row["strategy"]).replace("|", "\\|"),
                done=row.get("completed_evaluations", "—"),
                planned=row.get("planned_evaluations", "—"),
                rate="—" if rate is None else f"{float(rate):.1%}",
                runtime="—" if runtime is None else f"{float(runtime):.3f}",
                hv="—" if hv is None else f"{float(hv):.8g}",
                delta="—" if delta is None else f"{float(delta):+.8g}",
            )
        )
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
    comparisons = _comparisons(spec, cells)
    result = {
        "format": "yadof.benchmark.results",
        "run_id": state["run_id"],
        "generated_utc": utc_now(),
        "execution_status": state["status"],
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
    }
    atomic_write_json(run_root / "results.json", result)
    atomic_write_text(run_root / "results.csv", _csv_text(rows))
    atomic_write_text(run_root / "reports" / "summary.md", _markdown(
        str(state["run_id"]), state, comparisons
    ))
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
    return {
        "format": "yadof.benchmark.inspect",
        "run_id": state["run_id"],
        "run": str(run_root),
        "workflow": spec["workflow"]["name"],
        "status": state["status"],
        "updated_utc": state["updated_utc"],
        "cell_counts": dict(sorted(counts.items())),
        "postprocessors": state.get("postprocessors", {}),
        "active": active_progress(run_root, state),
        "errors": errors,
        "artifacts": {
            name: str(run_root / name)
            for name in ("spec.json", "state.json", "results.json", "results.csv", "reports/summary.md")
            if (run_root / name).is_file()
        },
    }


__all__ = ["collect_cell", "inspect_run", "publish_results"]
