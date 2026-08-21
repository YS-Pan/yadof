"""Terminal-friendly reports for the read-only surrogate viewer backend."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from .backend import CrossGenerationErrorAudit, SurrogateWorkspace


ReportPayload = dict[str, Any]


def _finite_or_none(value: object) -> float | None:
    if value is None:
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) else None


def _dimension_payload(dimension: object) -> ReportPayload:
    coordinates = np.asarray(
        getattr(dimension, "coordinates"),
        dtype=float,
    ).reshape(-1)
    finite = coordinates[np.isfinite(coordinates)]
    return {
        "index": int(getattr(dimension, "index")),
        "name": str(getattr(dimension, "name")),
        "unit": str(getattr(dimension, "unit")),
        "coordinate_count": int(coordinates.size),
        "coordinate_min": (
            None if finite.size == 0 else float(np.min(finite))
        ),
        "coordinate_max": (
            None if finite.size == 0 else float(np.max(finite))
        ),
    }


def build_workspace_summary(viewer: SurrogateWorkspace) -> ReportPayload:
    """Build a stable, JSON-serializable summary without model inference."""

    generation_counts = [
        {
            "generation": int(generation),
            "completed_results": len(
                viewer.results_for_generation(generation)
            ),
        }
        for generation in viewer.generations
    ]
    rawdata = [
        {
            "index": index,
            "name": name,
            "dimensions": [
                _dimension_payload(dimension)
                for dimension in viewer.dimensions_for_rawdata(index)
            ],
        }
        for index, name in enumerate(viewer.rawdata_names)
    ]
    return {
        "schema_version": 1,
        "analysis": "surrogate_workspace_summary",
        "workspace": str(Path(viewer.root).resolve()),
        "checkpoint_count": len(viewer.checkpoints),
        "checkpoints": [
            {
                "generation": int(checkpoint.generation),
                "sample_count": int(checkpoint.sample_count),
                "member_count": int(checkpoint.member_count),
                "training_policy": str(
                    checkpoint.payload["training_policy"]
                ),
                "state_signature": str(
                    checkpoint.payload["state_signature"]
                ),
                "path": str(Path(checkpoint.path).resolve()),
            }
            for checkpoint in viewer.checkpoints
        ],
        "optimization_generation_count": len(viewer.generations),
        "optimization_generations": generation_counts,
        "completed_result_count": len(viewer.real_results),
        "parameters": [
            {
                "name": parameter.name,
                "unit": parameter.unit,
                "ranges": [
                    [float(lower), float(upper)]
                    for lower, upper in parameter.ranges
                ],
            }
            for parameter in viewer.parameters
        ],
        "objectives": list(viewer.objective_names),
        "rawdata": rawdata,
    }


def _resolve_quantity(
    objective_names: tuple[str, ...],
    rawdata_names: tuple[str, ...],
    selector: str,
) -> tuple[str, int | None, str | None]:
    normalized = str(selector).strip()
    if normalized == "all-costs":
        return "cost", None, None
    if normalized == "all-rawdata":
        return "rawdata", None, None
    if ":" not in normalized:
        raise ValueError(
            "quantity must be all-costs, cost:NAME, all-rawdata, "
            "or rawdata:NAME"
        )
    prefix, name = normalized.split(":", 1)
    if not name:
        raise ValueError("quantity name cannot be empty")
    if prefix == "cost":
        names = objective_names
        kind = "cost"
    elif prefix == "rawdata":
        names = rawdata_names
        kind = "rawdata"
    else:
        raise ValueError(
            "quantity must be all-costs, cost:NAME, all-rawdata, "
            "or rawdata:NAME"
        )
    try:
        index = names.index(name)
    except ValueError as exc:
        available = ", ".join(names) or "(none)"
        raise ValueError(
            f"unknown {kind} quantity {name!r}; available names: {available}"
        ) from exc
    return kind, index, name


def _matrix_values(values: np.ndarray) -> list[list[float | None]]:
    matrix = np.asarray(values, dtype=float)
    return [
        [
            float(value) if math.isfinite(float(value)) else None
            for value in row
        ]
        for row in matrix
    ]


def build_error_audit_report(
    viewer: SurrogateWorkspace,
    *,
    sample_fraction: float = 0.1,
    random_seed: int | None = None,
    metric: str = "relative",
    quantity: str = "all-costs",
    progress: Callable[[int, int, str], None] | None = None,
) -> ReportPayload:
    """Calculate one audit and select terminal-report matrices from it."""

    if metric not in {"relative", "absolute", "both"}:
        raise ValueError("metric must be relative, absolute, or both")
    quantity_kind, quantity_index, quantity_name = _resolve_quantity(
        viewer.objective_names,
        viewer.rawdata_names,
        quantity,
    )
    audit = viewer.calculate_error_audit(
        sample_fraction=sample_fraction,
        random_seed=random_seed,
        progress=progress,
    )
    metrics = (
        ("relative", "absolute")
        if metric == "both"
        else (metric,)
    )
    matrices = []
    for selected_metric in metrics:
        matrix = audit.matrix(
            metric=selected_metric,
            quantity_kind=quantity_kind,
            quantity_index=quantity_index,
        )
        matrices.append(
            {
                "metric": selected_metric,
                "label": matrix.metric_label,
                "values": _matrix_values(matrix.values),
            }
        )
    return {
        "schema_version": 1,
        "analysis": "surrogate_cross_generation_error_audit",
        "workspace": str(Path(viewer.root).resolve()),
        "sample_fraction": float(audit.sample_fraction),
        "random_seed": random_seed,
        "quantity": {
            "selector": quantity,
            "kind": quantity_kind,
            "name": quantity_name,
        },
        "checkpoint_generations": list(audit.checkpoint_generations),
        "optimization_generations": list(
            audit.optimization_generations
        ),
        "sample_counts": list(audit.sample_counts),
        "matrices": matrices,
    }


def _format_number(value: object) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.6g}"


def _json_report(
    payload: Mapping[str, object],
    output_format: str,
) -> str | None:
    if output_format == "json":
        return json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
    if output_format != "text":
        raise ValueError("output_format must be text or json")
    return None


def format_workspace_summary(
    payload: Mapping[str, object],
    *,
    output_format: str = "text",
) -> str:
    """Render a workspace-summary payload as readable text or JSON."""

    encoded = _json_report(payload, output_format)
    if encoded is not None:
        return encoded

    lines = [
        "surrogate workspace summary",
        f"workspace: {payload['workspace']}",
        f"checkpoints: {payload['checkpoint_count']}",
    ]
    for checkpoint in payload["checkpoints"]:
        lines.append(
            "  generation "
            f"{checkpoint['generation']}: "
            f"samples={checkpoint['sample_count']}, "
            f"members={checkpoint['member_count']}, "
            f"policy={checkpoint['training_policy']}, "
            f"state={checkpoint['state_signature'][:12]}"
        )
    lines.append(
        "optimization generations: "
        + ", ".join(
            f"{item['generation']} ({item['completed_results']} results)"
            for item in payload["optimization_generations"]
        )
    )
    lines.append(
        f"completed results: {payload['completed_result_count']}"
    )
    lines.append(f"parameters: {len(payload['parameters'])}")
    for parameter in payload["parameters"]:
        ranges = ", ".join(
            f"[{_format_number(bounds[0])}, "
            f"{_format_number(bounds[1])}]"
            for bounds in parameter["ranges"]
        )
        unit = f" {parameter['unit']}" if parameter["unit"] else ""
        lines.append(f"  {parameter['name']}: {ranges}{unit}")
    lines.append(
        "objectives: " + ", ".join(payload["objectives"])
    )
    lines.append(f"rawData outputs: {len(payload['rawdata'])}")
    for item in payload["rawdata"]:
        dimensions = []
        for dimension in item["dimensions"]:
            unit = f" {dimension['unit']}" if dimension["unit"] else ""
            dimensions.append(
                f"{dimension['name']}[{dimension['coordinate_count']}; "
                f"{_format_number(dimension['coordinate_min'])}.."
                f"{_format_number(dimension['coordinate_max'])}{unit}]"
            )
        lines.append(
            f"  {item['name']}: "
            + (", ".join(dimensions) if dimensions else "scalar")
        )
    return "\n".join(lines)


def format_error_audit_report(
    payload: Mapping[str, object],
    *,
    output_format: str = "text",
) -> str:
    """Render an error-audit payload as TSV-like text or JSON."""

    encoded = _json_report(payload, output_format)
    if encoded is not None:
        return encoded

    checkpoint_generations = payload["checkpoint_generations"]
    optimization_generations = payload["optimization_generations"]
    sample_counts = payload["sample_counts"]
    lines = [
        "surrogate cross-generation error audit",
        f"workspace: {payload['workspace']}",
        f"sample fraction: {_format_number(payload['sample_fraction'])}",
        f"random seed: {payload['random_seed']}",
        f"quantity: {payload['quantity']['selector']}",
    ]
    for matrix in payload["matrices"]:
        lines.extend(
            (
                "",
                matrix["label"],
                "optimization_generation\tsamples\t"
                + "\t".join(
                    f"checkpoint_{generation}"
                    for generation in checkpoint_generations
                ),
            )
        )
        for generation, count, row in zip(
            optimization_generations,
            sample_counts,
            matrix["values"],
        ):
            lines.append(
                f"{generation}\t{count}\t"
                + "\t".join(_format_number(value) for value in row)
            )
    return "\n".join(lines)


def render_workspace_summary(
    workspace: str | Path,
    *,
    output_format: str = "text",
) -> str:
    """Load a workspace and render its non-inference surrogate summary."""

    viewer = SurrogateWorkspace(workspace)
    return format_workspace_summary(
        build_workspace_summary(viewer),
        output_format=output_format,
    )


def render_error_audit(
    workspace: str | Path,
    *,
    sample_fraction: float = 0.1,
    random_seed: int | None = None,
    metric: str = "relative",
    quantity: str = "all-costs",
    output_format: str = "text",
    progress: Callable[[int, int, str], None] | None = None,
) -> str:
    """Load a workspace, calculate an audit, and render selected matrices."""

    viewer = SurrogateWorkspace(workspace)
    payload = build_error_audit_report(
        viewer,
        sample_fraction=sample_fraction,
        random_seed=random_seed,
        metric=metric,
        quantity=quantity,
        progress=progress,
    )
    return format_error_audit_report(
        payload,
        output_format=output_format,
    )


__all__ = [
    "build_error_audit_report",
    "build_workspace_summary",
    "format_error_audit_report",
    "format_workspace_summary",
    "render_error_audit",
    "render_workspace_summary",
]
