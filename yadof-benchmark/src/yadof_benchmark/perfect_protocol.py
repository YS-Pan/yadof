"""Declared cumulative top-10 reference protocol, formal real rows only."""
from __future__ import annotations

from collections import Counter
import math

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
        summary = result.get("top10_protocol") or {}
        if not summary.get("budget_satisfied") or summary.get("final_top10") is None:
            raise BenchmarkError("top-10 reference lacks a valid full-budget threshold")
        threshold = summary["final_top10"]
    atomic_write_json(workspace / "benchmark_control.json", {
        "protocol": "formal-cumulative-top10-strict-reference", "root": str(root),
        "cell": cell["id"], "reference_cell": reference_cell, "threshold": threshold,
        "population": cell["population"], "max_generations": cell["generations"],
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
    formal = generation * context.population_size
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
    for generation in sorted(attempted):
        costs.extend(tuple(float(v) for v in row["costs"]) for row in rows
                     if row.get("generation_index") == generation - 1)
        value = top10(costs)
        trajectory.append({"generation": generation, "top10": value})
        if not control["reference"] and first is None and value is not None and value < control["threshold"]:
            first = generation
    last = max(attempted, default=0)
    expected = cell["generations"] if control["reference"] or first is None else first
    satisfied = (last == expected and set(attempted) == set(range(1, expected + 1))
                 and all(n == cell["population"] for n in attempted.values())
                 and len(records) == expected * cell["population"])
    metrics = [read_json(workspace / "experiment_metrics" / f"g{entry['generation']:04d}.json")
               for entry in trajectory]
    if any(a["generation"] != b["generation"] or a["top10"] != b["top10"]
           for a, b in zip(trajectory, metrics)):
        raise BenchmarkError("saved generation metrics disagree with durable formal history")
    final = trajectory[-1]["top10"] if trajectory else None
    return {"budget_satisfied": satisfied, "reference": control["reference"],
            "threshold": control["threshold"], "final_top10": final,
            "generations": last, "first_strictly_better_generation": first,
            "outcome": "reference" if control["reference"] else
                       first if first is not None else f"{cell['generations']} 代内未超过",
            "trajectory": trajectory, "formal_evaluations": len(records),
            "oracle": metrics[-1].get("oracle", {}) if metrics else {}}


def write_summary(context):
    spec = read_json(context.workspace / "spec.json")
    state = read_json(context.workspace / "state.json")
    comparisons = []
    for cell in spec["cells"]:
        path = context.workspace / "cells" / cell["id"] / "result.json"
        summary = (read_json(path).get("top10_protocol") or {}) if path.is_file() else {}
        comparisons.append({"baseline": cell["baseline"], "strategy": cell["strategy"],
                            "seed": cell["seed"], "cell": cell["id"],
                            "status": state["cells"][cell["id"]]["status"], **summary})
    atomic_write_json(context.reports / "perfect-surrogate-summary.json", {"comparisons": comparisons})
    lines = ["# Perfect surrogate GPSAF comparison", "", "Official real evaluations only; generation 1 is the initial design.", "",
             "| Baseline | Strategy | Generations | Formal | Threshold | Final top-10 | First strict crossing |", "|---|---|---:|---:|---:|---:|---|"]
    for item in comparisons:
        lines.append("| {baseline} | {strategy} | {generations} | {formal_evaluations} | {threshold} | {final_top10} | {outcome} |".format(
            **{**dict.fromkeys(("generations", "formal_evaluations", "threshold", "final_top10", "outcome"), "unavailable"), **item}))
    atomic_write_text(context.reports / "perfect-surrogate-summary.md", "\n".join(lines) + "\n")
    return {"summary": "reports/perfect-surrogate-summary.json", "cells": len(comparisons)}
