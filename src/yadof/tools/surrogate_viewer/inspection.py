"""Deterministic, headless single-case surrogate inspection."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
import csv
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
from uuid import uuid4

import numpy as np

from .backend import (
    CheckpointInfo,
    DimensionSpec,
    PlotData,
    PlotRequest,
    RealResult,
    SurrogateWorkspace,
    extract_plot,
    finite_plot_bounds,
)
from .errors import SurrogateToolError


INSPECTION_SCHEMA_VERSION = 1
INLINE_GRID_SCALAR_LIMIT = 4096


@dataclass(frozen=True)
class CaseInspection:
    """JSON payload plus exact selected arrays used for evidence export."""

    payload: Mapping[str, object]
    dimension_names: tuple[str, ...]
    dimension_units: tuple[str, ...]
    coordinates: tuple[np.ndarray, ...]
    prediction: np.ndarray
    truth: np.ndarray | None
    ensemble_minimum: np.ndarray | None
    ensemble_maximum: np.ndarray | None


def _failure(
    code: str,
    message: str,
    *,
    details: Mapping[str, object] | None = None,
    hints: Sequence[str] = (),
) -> SurrogateToolError:
    return SurrogateToolError(
        code,
        message,
        details=details,
        hints=hints,
    )


def _finite_or_none(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if math.isfinite(parsed) else None


def _json_array(array: np.ndarray) -> object:
    values = np.asarray(array)
    if values.ndim == 0:
        return _finite_or_none(values.item())
    return _json_nested(values.tolist())


def _json_nested(value: object) -> object:
    if isinstance(value, list):
        return [_json_nested(item) for item in value]
    return _finite_or_none(value)


def _array_payload(
    values: np.ndarray,
    *,
    inline: bool,
) -> dict[str, object]:
    array = np.asarray(values, dtype=float)
    finite = array[np.isfinite(array)]
    if finite.size == 0:
        mean = None
    else:
        scale = float(np.max(np.abs(finite)))
        if scale == 0.0:
            mean = 0.0
        else:
            with np.errstate(over="ignore", invalid="ignore"):
                mean = _finite_or_none(scale * float(np.mean(finite / scale)))
    return {
        "shape": list(array.shape),
        "scalar_count": int(array.size),
        "finite_count": int(finite.size),
        "minimum": None if finite.size == 0 else float(np.min(finite)),
        "maximum": None if finite.size == 0 else float(np.max(finite)),
        "mean": mean,
        "values_omitted": not inline,
        "values": _json_array(array) if inline else None,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _checkpoint_manifest_hash(checkpoint: CheckpointInfo) -> str | None:
    try:
        return _sha256(Path(checkpoint.path))
    except OSError:
        return None


def _resolve_checkpoint(
    viewer: SurrogateWorkspace,
    requested: int | str,
) -> CheckpointInfo:
    available = tuple(
        sorted(int(checkpoint.generation) for checkpoint in viewer.checkpoints)
    )
    if not available:
        raise _failure(
            "NO_COMPATIBLE_CHECKPOINT",
            "The active strategy has no viewer-compatible checkpoint.",
            details={"available_generations": []},
        )
    if requested == "latest":
        generation = available[-1]
    else:
        try:
            generation = int(requested)
        except (TypeError, ValueError) as exc:
            raise _failure(
                "CHECKPOINT_NOT_FOUND",
                "Checkpoint generation must be a non-negative integer or 'latest'.",
                details={
                    "requested_generation": requested,
                    "available_generations": list(available),
                },
            ) from exc
        if generation < 0:
            raise _failure(
                "CHECKPOINT_NOT_FOUND",
                "Checkpoint generation must be non-negative.",
                details={
                    "requested_generation": generation,
                    "available_generations": list(available),
                },
            )
    matches = tuple(
        checkpoint
        for checkpoint in viewer.checkpoints
        if int(checkpoint.generation) == generation
    )
    if len(matches) != 1:
        raise _failure(
            "CHECKPOINT_NOT_FOUND",
            (
                f"Checkpoint generation {generation} was not found."
                if not matches
                else f"Checkpoint generation {generation} is not unique."
            ),
            details={
                "requested_generation": requested,
                "resolved_generation": generation,
                "matching_count": len(matches),
                "available_generations": list(available),
            },
            hints=("Use one generation listed in available_generations.",),
        )
    return matches[0]


def _resolve_real_result(
    viewer: SurrogateWorkspace,
    *,
    job_name: str | None,
    real_generation: int | None,
    population_index: int | None,
) -> tuple[RealResult, dict[str, object]]:
    has_job = job_name is not None
    has_generation = real_generation is not None
    has_population = population_index is not None
    if has_job and (has_generation or has_population):
        raise _failure(
            "INVALID_REAL_RESULT_SELECTOR",
            "Do not combine --job-name with generation/population selection.",
            details={
                "job_name": job_name,
                "real_generation": real_generation,
                "population_index": population_index,
            },
            hints=(
                "Use either --job-name or both --real-generation and "
                "--population-index.",
            ),
        )
    if not has_job and has_generation != has_population:
        raise _failure(
            "INVALID_REAL_RESULT_SELECTOR",
            "Generation/population selection requires both values.",
            details={
                "real_generation": real_generation,
                "population_index": population_index,
            },
            hints=(
                "Provide both --real-generation and --population-index, or use "
                "--job-name.",
            ),
        )
    if not has_job and not has_generation:
        raise _failure(
            "INVALID_REAL_RESULT_SELECTOR",
            "A real-result selector is required.",
            details={},
            hints=(
                "Provide --job-name, or both --real-generation and "
                "--population-index.",
            ),
        )

    if has_job:
        selected_job = str(job_name)
        if not selected_job:
            raise _failure(
                "INVALID_REAL_RESULT_SELECTOR",
                "--job-name cannot be empty.",
            )
        matches = tuple(
            row
            for row in viewer.real_results
            if row.job_name == selected_job
        )
        selector = {"type": "job_name", "job_name": selected_job}
    else:
        generation = int(real_generation)
        population = int(population_index)
        if generation < 0 or population < 0:
            raise _failure(
                "INVALID_REAL_RESULT_SELECTOR",
                "Generation and population index must be non-negative.",
                details={
                    "real_generation": generation,
                    "population_index": population,
                },
            )
        matches = tuple(
            row
            for row in viewer.real_results
            if row.generation == generation
            and row.population_index == population
        )
        selector = {
            "type": "generation_population",
            "generation": generation,
            "population_index": population,
        }

    if not matches:
        raise _failure(
            "REAL_RESULT_NOT_FOUND",
            "No completed real result matches the requested selector.",
            details={"selector": selector, "matching_count": 0},
            hints=(
                "Use a job name or generation/population pair from surrogate "
                "summary/history metadata.",
            ),
        )
    if len(matches) > 1:
        raise _failure(
            "REAL_RESULT_AMBIGUOUS",
            "More than one completed real result matches the selector.",
            details={
                "selector": selector,
                "matching_count": len(matches),
                "matching_job_names": [row.job_name for row in matches[:20]],
            },
            hints=("Use the exact unique --job-name selector.",),
        )
    return matches[0], selector


def _resolve_rawdata_index(
    viewer: SurrogateWorkspace,
    name: str,
) -> int:
    requested = str(name)
    matches = tuple(
        index
        for index, candidate in enumerate(viewer.rawdata_names)
        if candidate == requested
    )
    if not matches:
        raise _failure(
            "RAWDATA_NOT_FOUND",
            f"rawData output {requested!r} was not found.",
            details={
                "requested_name": requested,
                "available_names": list(viewer.rawdata_names),
            },
            hints=("Choose one exact name from available_names.",),
        )
    if len(matches) > 1:
        raise _failure(
            "RAWDATA_AMBIGUOUS",
            f"rawData output {requested!r} is not unique.",
            details={
                "requested_name": requested,
                "matching_indices": list(matches),
                "available_names": list(viewer.rawdata_names),
            },
        )
    return matches[0]


def _dimension_by_name(
    dimensions: Sequence[DimensionSpec],
    name: str,
) -> DimensionSpec:
    matches = tuple(
        dimension
        for dimension in dimensions
        if dimension.name == str(name)
    )
    if not matches:
        raise _failure(
            "INVALID_PLOT_REQUEST",
            f"rawData dimension {name!r} was not found.",
            details={
                "requested_dimension": str(name),
                "available_dimensions": [
                    dimension.name for dimension in dimensions
                ],
            },
            hints=("Use exact dimension names from available_dimensions.",),
        )
    if len(matches) > 1:
        raise _failure(
            "INVALID_PLOT_REQUEST",
            f"rawData dimension {name!r} is ambiguous.",
            details={
                "requested_dimension": str(name),
                "matching_indices": [dimension.index for dimension in matches],
            },
        )
    return matches[0]


def _grid_match(
    dimension: DimensionSpec,
    requested: float,
) -> tuple[bool, float]:
    coordinates = np.asarray(dimension.coordinates, dtype=float).reshape(-1)
    if coordinates.size == 0:
        return False, float(requested)
    nearest_index = int(np.argmin(np.abs(coordinates - requested)))
    nearest = float(coordinates[nearest_index])
    tolerance = 1e-10 * max(
        1.0,
        abs(float(requested)),
        float(np.max(np.abs(coordinates))),
    )
    matched = math.isclose(
        nearest,
        float(requested),
        rel_tol=1e-10,
        abs_tol=tolerance,
    )
    return matched, nearest if matched else float(requested)


def _resolve_plot_request(
    viewer: SurrogateWorkspace,
    *,
    item_index: int,
    plot_dimension_names: Sequence[str],
    fixed_coordinates: Sequence[tuple[str, float]],
) -> tuple[
    PlotRequest,
    tuple[DimensionSpec, ...],
    dict[str, object],
    bool,
]:
    dimensions = viewer.dimensions_for_rawdata(item_index)
    requested_plot_names = tuple(str(name) for name in plot_dimension_names)
    if len(requested_plot_names) > 2:
        raise _failure(
            "INVALID_PLOT_REQUEST",
            "Choose at most two --plot-dimension values.",
            details={"requested_dimensions": list(requested_plot_names)},
        )
    if len(set(requested_plot_names)) != len(requested_plot_names):
        raise _failure(
            "INVALID_PLOT_REQUEST",
            "Plot dimensions must be unique.",
            details={"requested_dimensions": list(requested_plot_names)},
        )
    if requested_plot_names:
        plotted = tuple(
            _dimension_by_name(dimensions, name)
            for name in requested_plot_names
        )
        plot_source = "explicit"
    elif dimensions:
        default = next(
            (
                dimension
                for dimension in dimensions
                if dimension.name.casefold() == "freq"
            ),
            dimensions[0],
        )
        plotted = (default,)
        plot_source = "default"
    else:
        plotted = ()
        plot_source = "scalar"

    explicit_fixed: dict[str, float] = {}
    for name, value in fixed_coordinates:
        text_name = str(name)
        if text_name in explicit_fixed:
            raise _failure(
                "INVALID_PLOT_REQUEST",
                f"Fixed coordinate {text_name!r} was provided more than once.",
                details={"coordinate_name": text_name},
            )
        parsed = float(value)
        if not math.isfinite(parsed):
            raise _failure(
                "INVALID_PLOT_REQUEST",
                f"Fixed coordinate {text_name!r} must be finite.",
                details={"coordinate_name": text_name, "value": parsed},
            )
        _dimension_by_name(dimensions, text_name)
        explicit_fixed[text_name] = parsed

    plotted_indices = tuple(dimension.index for dimension in plotted)
    plotted_names = {dimension.name for dimension in plotted}
    conflicting = sorted(plotted_names.intersection(explicit_fixed))
    if conflicting:
        raise _failure(
            "INVALID_PLOT_REQUEST",
            "A plotted dimension cannot also be fixed.",
            details={"conflicting_dimensions": conflicting},
        )

    fixed_values: list[tuple[int, float]] = []
    fixed_payload: list[dict[str, object]] = []
    all_fixed_on_grid = True
    for dimension in dimensions:
        if dimension.index in plotted_indices:
            continue
        if dimension.name in explicit_fixed:
            requested = explicit_fixed[dimension.name]
            source = "explicit"
        else:
            requested = float(dimension.default_value)
            source = "default"
        on_grid, resolved = _grid_match(dimension, requested)
        all_fixed_on_grid = all_fixed_on_grid and on_grid
        fixed_values.append((dimension.index, requested))
        fixed_payload.append(
            {
                "index": int(dimension.index),
                "name": dimension.name,
                "unit": dimension.unit,
                "requested_value": float(requested),
                "value": float(resolved),
                "source": source,
                "on_grid": on_grid,
            }
        )

    unused = sorted(set(explicit_fixed).difference(
        dimension.name
        for dimension in dimensions
        if dimension.index not in plotted_indices
    ))
    if unused:  # pragma: no cover - earlier validation identifies the cause.
        raise _failure(
            "INVALID_PLOT_REQUEST",
            "Some fixed coordinates do not identify fixed dimensions.",
            details={"coordinates": unused},
        )

    request = PlotRequest(
        item_index=int(item_index),
        plotted_dimensions=plotted_indices,
        fixed_values=tuple(fixed_values),
    )
    query = {
        "plot_dimension_source": plot_source,
        "plot_dimensions": [
            {
                "index": int(dimension.index),
                "name": dimension.name,
                "unit": dimension.unit,
                "coordinate_count": int(
                    np.asarray(dimension.coordinates).size
                ),
                "coordinate_min": _finite_or_none(
                    np.min(dimension.coordinates)
                    if np.asarray(dimension.coordinates).size
                    else None
                ),
                "coordinate_max": _finite_or_none(
                    np.max(dimension.coordinates)
                    if np.asarray(dimension.coordinates).size
                    else None
                ),
            }
            for dimension in plotted
        ],
        "fixed_coordinates": fixed_payload,
    }
    return request, plotted, query, all_fixed_on_grid


def _selected_plots(
    prediction: object,
    request: PlotRequest,
) -> tuple[PlotData, tuple[PlotData, ...], PlotData | None, bool]:
    direct = getattr(prediction, "predicted_plot")
    if direct is not None:
        return (
            direct,
            tuple(getattr(prediction, "member_plots")),
            None,
            False,
        )
    predicted_plot = extract_plot(
        getattr(prediction, "predicted_sample"),
        request.item_index,
        request.plotted_dimensions,
        request.fixed_map,
    )
    member_plots = tuple(
        extract_plot(
            sample,
            request.item_index,
            request.plotted_dimensions,
            request.fixed_map,
        )
        for sample in getattr(prediction, "member_samples")
    )
    true_sample = getattr(prediction, "true_sample")
    truth_plot = (
        None
        if true_sample is None
        else extract_plot(
            true_sample,
            request.item_index,
            request.plotted_dimensions,
            request.fixed_map,
        )
    )
    return predicted_plot, member_plots, truth_plot, True


def _error_summary(
    prediction: np.ndarray,
    truth: np.ndarray,
    dimensions: Sequence[DimensionSpec],
) -> dict[str, object]:
    predicted = np.asarray(prediction, dtype=float)
    actual = np.asarray(truth, dtype=float)
    if predicted.shape != actual.shape:
        raise _failure(
            "INFERENCE_FAILED",
            "Predicted and true rawData slices have different shapes.",
            details={
                "prediction_shape": list(predicted.shape),
                "truth_shape": list(actual.shape),
            },
        )
    pairwise_finite = np.isfinite(predicted) & np.isfinite(actual)
    with np.errstate(over="ignore", invalid="ignore"):
        absolute = np.abs(predicted - actual)
    finite = pairwise_finite & np.isfinite(absolute)
    count = int(np.count_nonzero(finite))
    if count == 0:
        return {
            "finite_count": 0,
            "mae": None,
            "rmse": None,
            "max_absolute_error": None,
            "max_error_coordinate": None,
        }
    selected = absolute[finite]
    finite_flat_indices = np.flatnonzero(finite.reshape(-1))
    selected_offset = int(np.argmax(selected))
    flat_index = int(finite_flat_indices[selected_offset])
    array_index = np.unravel_index(flat_index, predicted.shape)
    coordinate = {
        dimension.name: _finite_or_none(
            np.asarray(dimension.coordinates, dtype=float)[axis_index]
        )
        for dimension, axis_index in zip(dimensions, array_index)
    }
    scale = float(np.max(selected))
    if scale == 0.0:
        mae = 0.0
        rmse = 0.0
    else:
        scaled = selected / scale
        with np.errstate(over="ignore", invalid="ignore"):
            mae = _finite_or_none(scale * float(np.mean(scaled)))
            rmse = _finite_or_none(
                scale * float(np.sqrt(np.mean(np.square(scaled))))
            )
    return {
        "finite_count": count,
        "mae": mae,
        "rmse": rmse,
        "max_absolute_error": _finite_or_none(scale),
        "max_error_coordinate": coordinate,
    }


def build_case_inspection(
    viewer: SurrogateWorkspace,
    *,
    checkpoint_generation: int | str = "latest",
    job_name: str | None = None,
    real_generation: int | None = None,
    population_index: int | None = None,
    rawdata_name: str,
    plot_dimension_names: Sequence[str] = (),
    fixed_coordinates: Sequence[tuple[str, float]] = (),
) -> CaseInspection:
    """Resolve one exact real case and return bounded diagnostic evidence."""

    checkpoint = _resolve_checkpoint(viewer, checkpoint_generation)
    real_result, real_selector = _resolve_real_result(
        viewer,
        job_name=job_name,
        real_generation=real_generation,
        population_index=population_index,
    )
    item_index = _resolve_rawdata_index(viewer, rawdata_name)
    request, _resolved_dimensions, query, expected_on_grid = _resolve_plot_request(
        viewer,
        item_index=item_index,
        plot_dimension_names=plot_dimension_names,
        fixed_coordinates=fixed_coordinates,
    )

    try:
        predicted = viewer.predict_one(
            checkpoint.generation,
            real_result.normalized_values,
            true_job_name=real_result.job_name,
            plot_request=request,
        )
    except SurrogateToolError:
        raise
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        if not expected_on_grid:
            raise _failure(
                "INVALID_PLOT_REQUEST",
                "The selected off-grid rawData query is not supported.",
                details={
                    "rawdata_name": rawdata_name,
                    "exception_type": type(exc).__name__,
                    "reason": str(exc),
                },
                hints=("Use stored coordinates or a supported in-domain query.",),
            ) from exc
        raise _failure(
            "INFERENCE_FAILED",
            "Surrogate inference failed for the selected checkpoint and case.",
            details={
                "checkpoint_generation": checkpoint.generation,
                "job_name": real_result.job_name,
                "exception_type": type(exc).__name__,
                "reason": str(exc),
            },
        ) from exc
    except Exception as exc:
        raise _failure(
            "INFERENCE_FAILED",
            "Surrogate inference failed for the selected checkpoint and case.",
            details={
                "checkpoint_generation": checkpoint.generation,
                "job_name": real_result.job_name,
                "exception_type": type(exc).__name__,
            },
        ) from exc

    try:
        predicted_plot, member_plots, truth_plot, on_grid = _selected_plots(
            predicted,
            request,
        )
    except SurrogateToolError:
        raise
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise _failure(
            "INVALID_PLOT_REQUEST",
            "The selected rawData slice could not be extracted.",
            details={
                "rawdata_name": rawdata_name,
                "exception_type": type(exc).__name__,
                "reason": str(exc),
            },
        ) from exc

    prediction_values = np.asarray(predicted_plot.values, dtype=float)
    truth_values = (
        None
        if truth_plot is None
        else np.asarray(truth_plot.values, dtype=float)
    )
    bounds = finite_plot_bounds(member_plots)
    ensemble_minimum = None if bounds is None else np.asarray(bounds[0], dtype=float)
    ensemble_maximum = None if bounds is None else np.asarray(bounds[1], dtype=float)
    dimensions = tuple(predicted_plot.dimensions)
    coordinates = tuple(
        np.asarray(dimension.coordinates, dtype=float).copy()
        for dimension in dimensions
    )
    grid_scalar_count = int(prediction_values.size)
    inline = grid_scalar_count <= INLINE_GRID_SCALAR_LIMIT

    for dimension_payload, coordinates_array in zip(
        query["plot_dimensions"],
        coordinates,
    ):
        dimension_payload["coordinates_omitted"] = not inline
        dimension_payload["coordinates"] = (
            _json_array(coordinates_array) if inline else None
        )

    objective_names = tuple(str(name) for name in viewer.objective_names)
    predicted_costs = tuple(float(value) for value in predicted.predicted_costs)
    true_costs = (
        None
        if predicted.true_costs is None
        else tuple(float(value) for value in predicted.true_costs)
    )
    if len(predicted_costs) != len(objective_names) or (
        true_costs is not None and len(true_costs) != len(objective_names)
    ):
        raise _failure(
            "INFERENCE_FAILED",
            "Predicted or true objective width does not match the current task.",
            details={
                "objective_count": len(objective_names),
                "predicted_count": len(predicted_costs),
                "true_count": None if true_costs is None else len(true_costs),
            },
        )

    warnings: list[str] = []
    if not on_grid:
        warnings.append(
            "The rawData query is off-grid; recorded truth and rawData error "
            "statistics are unavailable."
        )
    if not inline:
        warnings.append(
            f"Selected grid has {grid_scalar_count} scalars, above the inline "
            f"limit of {INLINE_GRID_SCALAR_LIMIT}; use --output for full arrays."
        )
    error_summary = (
        None
        if truth_values is None
        else _error_summary(prediction_values, truth_values, dimensions)
    )
    if error_summary is not None and error_summary["finite_count"] == 0:
        warnings.append(
            "The selected prediction/truth slices have no pairwise finite values."
        )

    checkpoint_payload = checkpoint.payload
    parameters = []
    if not (
        len(viewer.parameters)
        == len(real_result.raw_values)
        == len(real_result.normalized_values)
    ):
        raise _failure(
            "INFERENCE_FAILED",
            "The selected real result does not match current parameter width.",
            details={
                "parameter_count": len(viewer.parameters),
                "raw_value_count": len(real_result.raw_values),
                "normalized_value_count": len(real_result.normalized_values),
            },
        )
    for parameter, raw, normalized in zip(
        viewer.parameters,
        real_result.raw_values,
        real_result.normalized_values,
    ):
        parameters.append(
            {
                "name": parameter.name,
                "unit": parameter.unit,
                "raw_value": _finite_or_none(raw),
                "normalized_value": _finite_or_none(normalized),
            }
        )

    query.update(
        {
            "rawdata_name": str(rawdata_name),
            "rawdata_index": int(item_index),
            "slice_rank": len(dimensions),
            "shape": list(prediction_values.shape),
            "grid_scalar_count": grid_scalar_count,
            "inline_grid_scalar_limit": INLINE_GRID_SCALAR_LIMIT,
            "on_grid": on_grid,
            "mode": "stored_grid" if on_grid else "off_grid",
            "slice_label": predicted_plot.slice_label,
        }
    )
    payload: dict[str, object] = {
        "schema_version": INSPECTION_SCHEMA_VERSION,
        "analysis": "surrogate_case_inspection",
        "workspace": str(Path(viewer.root).resolve()),
        "strategy_signature": str(viewer.strategy_signature),
        "run_namespace": str(viewer.run_namespace),
        "component_namespace": str(viewer.component_namespace),
        "checkpoint": {
            "requested_generation": checkpoint_generation,
            "generation": int(checkpoint.generation),
            "sample_count": int(checkpoint.sample_count),
            "member_count": int(checkpoint.member_count),
            "surrogate_method": str(
                checkpoint_payload.get("surrogate_method", "")
            ),
            "training_policy": str(
                checkpoint_payload.get("training_policy", "")
            ),
            "state_signature": str(
                checkpoint_payload.get("state_signature", "")
            ),
            "strategy_signature": str(
                checkpoint_payload.get("strategy_signature", "")
            ),
            "run_namespace": str(
                checkpoint_payload.get("run_namespace", "")
            ),
            "component_namespace": str(
                checkpoint_payload.get("component_namespace", "")
            ),
            "publication_id": str(
                checkpoint_payload.get("publication_id", "")
            ),
            "manifest_path": str(Path(checkpoint.path).resolve()),
            "manifest_sha256": _checkpoint_manifest_hash(checkpoint),
        },
        "real_result": {
            "selector": real_selector,
            "job_name": real_result.job_name,
            "generation": int(real_result.generation),
            "population_index": real_result.population_index,
        },
        "parameters": parameters,
        "query": query,
        "prediction": _array_payload(prediction_values, inline=inline),
        "truth": (
            None
            if truth_values is None
            else _array_payload(truth_values, inline=inline)
        ),
        "ensemble": {
            "checkpoint_member_count": int(checkpoint.member_count),
            "available_member_count": len(member_plots),
            "minimum": (
                None
                if ensemble_minimum is None
                else _array_payload(ensemble_minimum, inline=inline)
            ),
            "maximum": (
                None
                if ensemble_maximum is None
                else _array_payload(ensemble_maximum, inline=inline)
            ),
        },
        "objectives": [
            {
                "name": name,
                "predicted": _finite_or_none(predicted_value),
                "true": (
                    None
                    if true_costs is None
                    else _finite_or_none(true_costs[index])
                ),
                "absolute_error": (
                    None
                    if true_costs is None
                    or _finite_or_none(predicted_value) is None
                    or _finite_or_none(true_costs[index]) is None
                    else _finite_or_none(
                        abs(float(predicted_value) - float(true_costs[index]))
                    )
                ),
            }
            for index, (name, predicted_value) in enumerate(
                zip(objective_names, predicted_costs)
            )
        ],
        "error_summary": error_summary,
        "warnings": warnings,
        "artifacts": {
            "output_directory": None,
            "manifest": None,
            "files": [],
        },
    }
    return CaseInspection(
        payload=payload,
        dimension_names=tuple(dimension.name for dimension in dimensions),
        dimension_units=tuple(dimension.unit for dimension in dimensions),
        coordinates=coordinates,
        prediction=prediction_values.copy(),
        truth=None if truth_values is None else truth_values.copy(),
        ensemble_minimum=(
            None if ensemble_minimum is None else ensemble_minimum.copy()
        ),
        ensemble_maximum=(
            None if ensemble_maximum is None else ensemble_maximum.copy()
        ),
    )


def _validate_output_destination(output: str | Path) -> Path:
    path = Path(output).expanduser().resolve()
    try:
        exists = path.exists()
        is_directory = path.is_dir() if exists else False
        entries = tuple(path.iterdir()) if is_directory else ()
    except OSError as exc:
        raise _failure(
            "OUTPUT_WRITE_FAILED",
            "The inspection output destination could not be inspected.",
            details={
                "output": str(path),
                "exception_type": type(exc).__name__,
            },
        ) from exc
    if exists and not is_directory:
        raise _failure(
            "OUTPUT_CONFLICT",
            "The inspection output path exists and is not a directory.",
            details={"output": str(path)},
        )
    if entries:
        raise _failure(
            "OUTPUT_CONFLICT",
            "The inspection output directory is not empty.",
            details={
                "output": str(path),
                "existing_entries": [entry.name for entry in entries[:20]],
            },
            hints=("Choose a new or empty output directory.",),
        )
    return path


def _publish_exclusive(temporary: Path, destination: Path) -> None:
    with temporary.open("rb+") as stream:
        os.fsync(stream.fileno())
    os.link(temporary, destination)
    temporary.unlink()


def _write_npz(path: Path, inspection: CaseInspection) -> None:
    arrays: dict[str, np.ndarray] = {
        "coordinate_names": np.asarray(inspection.dimension_names),
        "coordinate_units": np.asarray(inspection.dimension_units),
        "prediction": np.asarray(inspection.prediction),
        "truth": (
            np.asarray([], dtype=float)
            if inspection.truth is None
            else np.asarray(inspection.truth)
        ),
        "ensemble_minimum": (
            np.asarray([], dtype=float)
            if inspection.ensemble_minimum is None
            else np.asarray(inspection.ensemble_minimum)
        ),
        "ensemble_maximum": (
            np.asarray([], dtype=float)
            if inspection.ensemble_maximum is None
            else np.asarray(inspection.ensemble_maximum)
        ),
    }
    arrays.update(
        {
            f"coordinate_{index}": np.asarray(coordinates)
            for index, coordinates in enumerate(inspection.coordinates)
        }
    )
    with path.open("wb") as stream:
        np.savez_compressed(stream, **arrays)


def _write_curve_csv(path: Path, inspection: CaseInspection) -> None:
    coordinate = np.asarray(inspection.coordinates[0], dtype=float).reshape(-1)
    prediction = np.asarray(inspection.prediction, dtype=float).reshape(-1)
    truth = (
        None
        if inspection.truth is None
        else np.asarray(inspection.truth, dtype=float).reshape(-1)
    )
    minimum = (
        None
        if inspection.ensemble_minimum is None
        else np.asarray(inspection.ensemble_minimum, dtype=float).reshape(-1)
    )
    maximum = (
        None
        if inspection.ensemble_maximum is None
        else np.asarray(inspection.ensemble_maximum, dtype=float).reshape(-1)
    )
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(
            (
                "coordinate",
                "prediction",
                "truth",
                "ensemble_minimum",
                "ensemble_maximum",
            )
        )
        for index, coordinate_value in enumerate(coordinate):
            writer.writerow(
                (
                    repr(float(coordinate_value)),
                    repr(float(prediction[index])),
                    "" if truth is None else repr(float(truth[index])),
                    "" if minimum is None else repr(float(minimum[index])),
                    "" if maximum is None else repr(float(maximum[index])),
                )
            )


def _artifact_entry(kind: str, path: Path, output: Path) -> dict[str, object]:
    return {
        "kind": kind,
        "path": path.relative_to(output).as_posix(),
        "size_bytes": int(path.stat().st_size),
        "sha256": _sha256(path),
    }


def export_case_inspection(
    inspection: CaseInspection,
    output: str | Path,
) -> dict[str, object]:
    """Write a self-contained evidence directory, publishing manifest last."""

    destination = _validate_output_destination(output)
    created_directory = False
    if not destination.exists():
        try:
            destination.mkdir(parents=True, exist_ok=False)
        except FileExistsError as exc:
            raise _failure(
                "OUTPUT_CONFLICT",
                "The inspection output destination was created concurrently.",
                details={"output": str(destination)},
            ) from exc
        except OSError as exc:
            raise _failure(
                "OUTPUT_WRITE_FAILED",
                "The inspection output directory could not be created.",
                details={
                    "output": str(destination),
                    "exception_type": type(exc).__name__,
                },
            ) from exc
        created_directory = True
    token = uuid4().hex
    temporary_paths: list[Path] = []
    published_paths: list[Path] = []
    stage = "prepare"
    try:
        if tuple(destination.iterdir()):
            raise _failure(
                "OUTPUT_CONFLICT",
                "The inspection output directory changed before export.",
                details={"output": str(destination)},
            )

        data_temp = destination / f".data.{token}.tmp"
        temporary_paths.append(data_temp)
        stage = "data.npz"
        _write_npz(data_temp, inspection)

        curve_temp = None
        if len(inspection.coordinates) == 1:
            curve_temp = destination / f".curve.{token}.tmp"
            temporary_paths.append(curve_temp)
            stage = "curve.csv"
            _write_curve_csv(curve_temp, inspection)

        plot_temp = destination / f".plot.{token}.tmp"
        temporary_paths.append(plot_temp)
        stage = "plot.png"
        try:
            from .renderer import render_case_plot
        except ImportError as exc:
            raise _failure(
                "MISSING_OPTIONAL_DEPENDENCY",
                "PNG export requires the surrogate viewer's Matplotlib dependency.",
                details={"dependency": getattr(exc, "name", None)},
                hints=("Install yadof with the 'viewer' extra and retry.",),
            ) from exc
        try:
            render_case_plot(
                plot_temp,
                dimension_names=inspection.dimension_names,
                dimension_units=inspection.dimension_units,
                coordinates=inspection.coordinates,
                prediction=inspection.prediction,
                truth=inspection.truth,
                ensemble_minimum=inspection.ensemble_minimum,
                ensemble_maximum=inspection.ensemble_maximum,
                objectives=inspection.payload["objectives"],
                title=(
                    f"{inspection.payload['query']['rawdata_name']} · "
                    f"checkpoint {inspection.payload['checkpoint']['generation']} · "
                    f"{inspection.payload['real_result']['job_name']}"
                ),
            )
        except SurrogateToolError:
            raise
        except Exception as exc:
            raise _failure(
                "RENDER_FAILED",
                "Headless PNG rendering failed.",
                details={
                    "output": str(destination),
                    "exception_type": type(exc).__name__,
                },
            ) from exc

        final_files: list[tuple[str, Path, Path]] = [
            ("data", data_temp, destination / "data.npz"),
        ]
        if curve_temp is not None:
            final_files.append(("curve", curve_temp, destination / "curve.csv"))
        final_files.append(("plot", plot_temp, destination / "plot.png"))
        artifact_entries: list[dict[str, object]] = []
        stage = "publish artifacts"
        for kind, temporary, final in final_files:
            _publish_exclusive(temporary, final)
            published_paths.append(final)
            artifact_entries.append(
                _artifact_entry(kind, final, destination)
            )

        payload = deepcopy(dict(inspection.payload))
        payload["artifacts"] = {
            "output_directory": str(destination),
            "manifest": {"path": "manifest.json"},
            "files": artifact_entries,
        }
        manifest_temp = destination / f".manifest.{token}.tmp"
        temporary_paths.append(manifest_temp)
        stage = "manifest.json"
        manifest_temp.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )
        manifest = destination / "manifest.json"
        _publish_exclusive(manifest_temp, manifest)
        published_paths.append(manifest)
        return payload
    except SurrogateToolError:
        raise
    except (FileExistsError, IsADirectoryError, NotADirectoryError) as exc:
        raise _failure(
            "OUTPUT_CONFLICT",
            "An inspection artifact already exists.",
            details={
                "output": str(destination),
                "stage": stage,
                "exception_type": type(exc).__name__,
            },
            hints=("Choose a new or empty output directory.",),
        ) from exc
    except OSError as exc:
        raise _failure(
            "OUTPUT_WRITE_FAILED",
            "Inspection evidence could not be written.",
            details={
                "output": str(destination),
                "stage": stage,
                "exception_type": type(exc).__name__,
            },
        ) from exc
    except Exception as exc:
        raise _failure(
            "OUTPUT_WRITE_FAILED",
            "Inspection evidence export did not complete.",
            details={
                "output": str(destination),
                "stage": stage,
                "exception_type": type(exc).__name__,
            },
        ) from exc
    finally:
        for path in temporary_paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        if not (destination / "manifest.json").is_file():
            for path in reversed(published_paths):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
            if created_directory:
                try:
                    destination.rmdir()
                except OSError:
                    pass


def format_case_inspection(
    payload: Mapping[str, object],
    *,
    output_format: str = "text",
) -> str:
    """Render a completed single-case inspection."""

    if output_format == "json":
        return json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
    if output_format != "text":
        raise ValueError("output_format must be text or json")
    checkpoint = payload["checkpoint"]
    result = payload["real_result"]
    query = payload["query"]
    error = payload["error_summary"]
    lines = [
        "surrogate case inspection",
        f"workspace: {payload['workspace']}",
        (
            f"checkpoint: generation {checkpoint['generation']} · "
            f"samples={checkpoint['sample_count']} · "
            f"members={checkpoint['member_count']}"
        ),
        (
            f"real result: generation {result['generation']} · "
            f"population {result['population_index']} · {result['job_name']}"
        ),
        (
            f"rawData: {query['rawdata_name']} · {query['mode']} · "
            f"shape={query['shape']}"
        ),
    ]
    if error is None:
        lines.append("rawData error: unavailable")
    else:
        lines.append(
            "rawData error: "
            f"finite={error['finite_count']} · "
            f"MAE={error['mae']} · RMSE={error['rmse']} · "
            f"max={error['max_absolute_error']}"
        )
    lines.append("objectives:")
    for objective in payload["objectives"]:
        lines.append(
            f"  {objective['name']}: predicted={objective['predicted']}, "
            f"true={objective['true']}, abs_error={objective['absolute_error']}"
        )
    artifacts = payload["artifacts"]
    if artifacts["output_directory"] is not None:
        lines.append(f"artifacts: {artifacts['output_directory']}")
    lines.extend(f"warning: {warning}" for warning in payload["warnings"])
    return "\n".join(lines)


def render_case_inspection(
    workspace: str | Path,
    *,
    checkpoint_generation: int | str = "latest",
    job_name: str | None = None,
    real_generation: int | None = None,
    population_index: int | None = None,
    rawdata_name: str,
    plot_dimension_names: Sequence[str] = (),
    fixed_coordinates: Sequence[tuple[str, float]] = (),
    output_format: str = "text",
    output: str | Path | None = None,
) -> str:
    """Load, inspect, optionally export, and format one surrogate case."""

    if output is not None:
        _validate_output_destination(output)
    viewer = SurrogateWorkspace(workspace)
    inspection = build_case_inspection(
        viewer,
        checkpoint_generation=checkpoint_generation,
        job_name=job_name,
        real_generation=real_generation,
        population_index=population_index,
        rawdata_name=rawdata_name,
        plot_dimension_names=plot_dimension_names,
        fixed_coordinates=fixed_coordinates,
    )
    payload = (
        dict(inspection.payload)
        if output is None
        else export_case_inspection(inspection, output)
    )
    return format_case_inspection(payload, output_format=output_format)


__all__ = [
    "CaseInspection",
    "INLINE_GRID_SCALAR_LIMIT",
    "INSPECTION_SCHEMA_VERSION",
    "build_case_inspection",
    "export_case_inspection",
    "format_case_inspection",
    "render_case_inspection",
]
