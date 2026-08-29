"""Generic public-yadof result collection and reporting."""
from __future__ import annotations

import csv
import io
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping

from .contracts import BenchmarkError, evidence_notice
from .progress import active_progress, estimate_run_timing
from .storage import (
    atomic_write_json,
    atomic_write_text,
    json_safe,
    load_run,
    read_json,
    utc_now,
)


def _evidence(spec: Mapping[str, Any]) -> str:
    workflow = spec.get("workflow", {})
    if not isinstance(workflow, Mapping):
        return "unclassified"
    return str(workflow.get("evidence", "unclassified"))


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
                "evidence": cell.get("evidence", "unclassified"),
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
    evidence = _evidence(spec)
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
                    "evidence": evidence,
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
    fields = [
        "evidence", "comparison", "baseline", "strategy", "seed", "population",
        "generations", "job", "generation", "objectives", "average_objective",
        "metadata",
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
        output.append(
            {
                "evidence": evidence,
                "cell": cell_id,
                "comparison": cell["comparison"],
                "baseline": cell["baseline"],
                "strategy": cell["strategy"],
                "seed": cell["seed"],
                "status": cell_state.get("status"),
                "completed": completed,
                "valid": completed and objective_match and rawdata_match and not issues,
                "objective_contract_matches": objective_match,
                "rawdata_contract_matches": rawdata_match,
                "completed_evaluations": (
                    None if result is None else result.get("completed_evaluations")
                ),
                "planned_evaluations": cell.get("planned_evaluations"),
                "issues": issues,
                "error": cell_state.get("error"),
            }
        )
    return output


def _markdown(
    run_id: str,
    evidence: str,
    state: Mapping[str, Any],
    comparisons: list[Mapping[str, Any]],
    cells: list[Mapping[str, Any]],
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
        "## Cell completion and validity",
        "",
        "| Cell | Status | Completed | Valid | Evaluations | Objective contract | rawData contract | Issues |",
        "| --- | --- | --- | --- | ---: | --- | --- | ---: |",
    ]
    for row in cells:
        lines.append(
            "| `{cell}` | {status} | {completed} | {valid} | {done}/{planned} | {objective} | {rawdata} | {issues} |".format(
                cell=str(row["cell"]).replace("|", "\\|"),
                status=row.get("status"),
                completed="yes" if row.get("completed") else "no",
                valid="yes" if row.get("valid") else "no",
                done=row.get("completed_evaluations", "—"),
                planned=row.get("planned_evaluations", "—"),
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
            "| Comparison | Baseline | Seed | Strategy | Evaluations | Success | Runtime (s) | Final hypervolume | Reference delta |",
            "| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
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
    comparisons = _comparisons(spec, cells)
    cell_summaries = _cell_summaries(spec, state, cells)
    evidence = _evidence(spec)
    result = {
        "format": "yadof.benchmark.results",
        "run_id": state["run_id"],
        "generated_utc": utc_now(),
        "execution_status": state["status"],
        "evidence": {
            "class": evidence,
            "notice": evidence_notice(evidence),
        },
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
    }
    atomic_write_json(run_root / "results.json", result)
    atomic_write_text(run_root / "results.csv", _csv_text(rows))
    reports = run_root / "reports"
    atomic_write_text(reports / "summary.md", _markdown(
        str(state["run_id"]), evidence, state, comparisons, cell_summaries
    ))
    atomic_write_text(
        reports / "cell-validity.csv",
        _table_csv(
            cell_summaries,
            [
                "evidence", "cell", "comparison", "baseline", "strategy", "seed", "status",
                "completed", "valid", "completed_evaluations", "planned_evaluations",
                "objective_contract_matches", "rawdata_contract_matches", "issues", "error",
            ],
        ),
    )
    atomic_write_text(
        reports / "final-hypervolume.csv",
        _table_csv(
            comparisons,
            [
                "evidence", "comparison", "baseline", "seed", "strategy", "reference",
                "completed_evaluations", "planned_evaluations", "success_rate",
                "runtime_seconds", "final_hypervolume", "reference_delta",
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
            "generated_utc": result["generated_utc"],
            "cells": cell_summaries,
            "final_hypervolume": comparisons,
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
    return {
        "format": "yadof.benchmark.inspect",
        "run_id": state["run_id"],
        "run": str(run_root),
        "workflow": spec["workflow"]["name"],
        "evidence": {
            "class": evidence,
            "notice": evidence_notice(evidence),
        },
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
                "reports/final-hypervolume.csv", "reports/descriptive-results.json",
                "visualizations", "benchmark.log", "timing_history.json",
            )
            if (run_root / name).is_file()
            or (run_root / name).is_dir()
        },
    }


__all__ = ["collect_cell", "inspect_run", "publish_results"]
