"""Declared cumulative top-10 reference protocol, formal real rows only."""
from __future__ import annotations

from collections import Counter, defaultdict
import math
import statistics

from .benchmark_runtime.contracts import BenchmarkError
from .benchmark_runtime.storage import atomic_write_json, atomic_write_text, read_json


def top10(costs):
    averages = sorted(math.fsum(row) / len(row) for row in costs
                      if row and all(math.isfinite(float(v)) for v in row))
    return math.fsum(averages[:10]) / 10 if len(averages) >= 10 else None


def prepare_control(root, spec, state, cell, workspace):
    from .runtime_freeze import task_fingerprint
    reference = cell["top10_reference"]
    threshold = None
    reference_cell = None
    if cell["strategy"] != reference:
        references = [c for c in spec["cells"] if c["comparison"] == cell["comparison"]
                      and c["baseline"] == cell["baseline"] and c["seed"] == cell["seed"]
                      and c["strategy"] == reference]
        if len(references) != 1:
            raise BenchmarkError("top-10 protocol requires exactly one paired reference")
        reference_cell = references[0]["id"]
        if state["cells"][reference_cell]["status"] != "collected":
            raise BenchmarkError("top-10 reference has not completed and been collected")
        result = read_json(root / "cells" / reference_cell / "result.json")
        from .benchmark_runtime.results import _cell_summaries
        validity = _cell_summaries({**spec, "cells": references}, state, {reference_cell: result})
        if not validity[0]["valid"]:
            raise BenchmarkError("top-10 reference failed collected-evidence validation")
        summary = result.get("top10_protocol") or {}
        if not summary.get("budget_satisfied") or summary.get("final_top10") is None:
            raise BenchmarkError("top-10 reference lacks a valid full-budget threshold")
        threshold = summary["final_top10"]
    atomic_write_json(workspace / "benchmark_control.json", {
        "protocol": "formal-cumulative-top10-strict-reference", "root": str(root),
        "cell": cell["id"], "reference_cell": reference_cell, "threshold": threshold,
        "population": cell["population"], "max_generations": cell["generations"],
        "batch_size": cell.get("batch_size") or cell["population"],
        "initial_population": cell.get("initial_population") or cell["population"],
        "reference": cell["strategy"] == reference,
        "task_files": task_fingerprint(workspace),
    })


def record_generation(context, current_costs, *, diagnostics=None):
    workspace = context.config.workspace.root
    control = read_json(workspace / "benchmark_control.json")
    generation = context.generation_index + 1
    costs = [row.costs for row in context.history] + list(current_costs)
    value = top10(costs)
    stop = not control["reference"] and value is not None and value < control["threshold"]
    finite = sum(all(math.isfinite(v) for v in row) for row in costs)
    formal = context.initial_population_size + (generation - 1) * context.batch_size
    receipt = {
        "generation": generation, "top10": value, "formal_evaluations": formal,
        "formal_finite": finite, "formal_failures_or_nonfinite": formal - finite,
        "threshold": control["threshold"], "strictly_better": stop,
        "oracle": {} if diagnostics is None else diagnostics,
        "scope": "formal-real-history-only; initial-generation-is-1",
    }
    atomic_write_json(workspace / "experiment_metrics" / f"g{generation:04d}.json", receipt)
    atomic_write_json(workspace / "experiment_metrics" / "latest.json", receipt)
    print(f"[benchmark] generation={generation} formal={formal} top10={value} stop={stop}", flush=True)
    return stop


def collect_top10(workspace, cell, records, rows):
    """Recompute the stop condition from durable evidence, independent of receipts."""
    control = read_json(workspace / "benchmark_control.json")
    attempted = Counter(int(row["generation_index"]) + 1 for row in records
                        if row.get("generation_index") is not None)
    costs, trajectory = [], []
    first = None
    formal = 0
    for generation in sorted(attempted):
        costs.extend(tuple(float(v) for v in row["costs"]) for row in rows
                     if row.get("generation_index") == generation - 1)
        value = top10(costs)
        formal += attempted[generation]
        trajectory.append({"generation": generation, "top10": value,
                           "formal_evaluations": formal})
        if not control["reference"] and first is None and value is not None and value < control["threshold"]:
            first = generation
    last = max(attempted, default=0)
    expected = cell["generations"] if control["reference"] or first is None else first
    initial = cell.get("initial_population") or cell["population"]
    batch = cell.get("batch_size") or cell["population"]
    satisfied = (last == expected and set(attempted) == set(range(1, expected + 1))
                 and all(n == (initial if g == 1 else batch) for g, n in attempted.items())
                 and len(records) == initial + (expected - 1) * batch)
    metrics = [read_json(workspace / "experiment_metrics" / f"g{entry['generation']:04d}.json")
               for entry in trajectory]
    if any(a["generation"] != b["generation"] or a["top10"] != b["top10"]
           or a["formal_evaluations"] != b["formal_evaluations"]
           for a, b in zip(trajectory, metrics)):
        raise BenchmarkError("saved generation metrics disagree with durable formal history")
    final = trajectory[-1]["top10"] if trajectory else None
    return {"budget_satisfied": satisfied, "reference": control["reference"],
            "threshold": control["threshold"], "final_top10": final,
            "generations": last, "first_strictly_better_generation": first,
            "first_strictly_better_evaluations": None if first is None else initial + (first - 1) * batch,
            "outcome": "reference" if control["reference"] else
                       first if first is not None else f"{cell['generations']} 代内未超过",
            "trajectory": trajectory, "formal_evaluations": len(records),
            "oracle": metrics[-1].get("oracle", {}) if metrics else {}}


def crossing_summary(comparisons):
    """Descriptive medians retain capped runs; failed cells invalidate the estimate."""
    groups = defaultdict(list)
    for item in comparisons:
        if not item.get("reference"):
            groups[(item["baseline"], item["strategy"], item["population"],
                    item["batch_size"], item["initial_population"])].append(item)
    summaries = []
    for key, rows in sorted(groups.items()):
        valid = [r for r in rows if r["status"] == "collected" and r.get("budget_satisfied")
                 and r.get("evidence_valid", True)]
        crossings = [r.get("first_strictly_better_evaluations") for r in valid]
        values = sorted(math.inf if v is None else v for v in crossings)
        complete = len(valid) == len(rows)
        median = statistics.median(values) if complete and values else None
        summaries.append(dict(zip(("baseline", "strategy", "population", "batch_size", "initial_population"), key),
            seeds=[r["seed"] for r in rows], runs=len(rows), valid_runs=len(valid),
            crossings=sum(v is not None for v in crossings),
            censored=sum(v is None for v in crossings),
            median_evaluations=median if median is not None and math.isfinite(median) else None,
            median_status="unavailable" if median is None else "right-censored" if math.isinf(median) else "observed",
            budget_cap=rows[0]["planned_evaluations"],
            quartile_method="empirical inverse CDF (nearest rank)",
            quartiles=[None if not complete or not values or math.isinf(values[math.ceil(q * len(values)) - 1])
                       else values[math.ceil(q * len(values)) - 1] for q in (0.25, 0.75)]))
    return summaries


def write_summary(context):
    from .benchmark_runtime.results import _cell_summaries
    spec = read_json(context.workspace / "spec.json")
    state = read_json(context.workspace / "state.json")
    results = {}
    for cell in spec["cells"]:
        path = context.workspace / "cells" / cell["id"] / "result.json"
        if path.is_file():
            results[cell["id"]] = read_json(path)
    validity = {row["cell"]: row["valid"] for row in _cell_summaries(spec, state, results)}
    comparisons = []
    for cell in spec["cells"]:
        summary = results.get(cell["id"], {}).get("top10_protocol") or {}
        comparisons.append({"baseline": cell["baseline"], "strategy": cell["strategy"],
                            "population": cell["population"],
                            "batch_size": cell.get("batch_size") or cell["population"],
                            "initial_population": cell.get("initial_population") or cell["population"],
                            "planned_evaluations": cell["planned_evaluations"],
                            "reference": cell["strategy"] == cell.get("top10_reference"),
                            "seed": cell["seed"], "cell": cell["id"],
                            "status": state["cells"][cell["id"]]["status"], **summary,
                            "evidence_valid": validity[cell["id"]]})
    aggregates = crossing_summary(comparisons)
    atomic_write_json(context.reports / "perfect-surrogate-summary.json",
                      {"comparisons": comparisons, "crossing_aggregates": aggregates})
    lines = ["# Perfect surrogate GPSAF comparison", "", "Official real evaluations only; generation 1 is the initial design.", "",
             "| Baseline | Strategy | Generations | Formal | Threshold | Final top-10 | First strict crossing |", "|---|---|---:|---:|---:|---:|---|"]
    for item in comparisons:
        lines.append("| {baseline} | {strategy} | {generations} | {formal_evaluations} | {threshold} | {final_top10} | {outcome} |".format(
            **{**dict.fromkeys(("generations", "formal_evaluations", "threshold", "final_top10", "outcome"), "unavailable"), **item}))
    lines += ["", "## Crossing distributions", "",
              "Capped runs remain in the median. A failed cell makes its group estimate unavailable.", "",
              "| Baseline | Strategy | P | B | I | Crossings / runs | Median formal evaluations |",
              "|---|---|---:|---:|---:|---:|---:|"]
    for item in aggregates:
        median = (item["median_evaluations"] if item["median_status"] == "observed" else
                  f">{item['budget_cap']}" if item["median_status"] == "right-censored" else "unavailable")
        lines.append(f"| {item['baseline']} | {item['strategy']} | {item['population']} | {item['batch_size']} | {item['initial_population']} | {item['crossings']} / {item['runs']} | {median} |")
    atomic_write_text(context.reports / "perfect-surrogate-summary.md", "\n".join(lines) + "\n")
    return {"summary": "reports/perfect-surrogate-summary.json", "cells": len(comparisons)}
