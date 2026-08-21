"""Read-only facade over one yadof workspace."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import math
from pathlib import Path
import threading
from typing import Mapping, Sequence

import numpy as np
import torch

from yadof.config import load_config
from yadof.job_template import api as job_template_api
from yadof.recorded_data import get_rawdata_samples, list_records

from .checkpoints import CheckpointPredictor, discover_checkpoints
from .rawdata import (
    flatten_samples_for_schema,
    rawdata_dimensions,
    rawdata_names,
)
from .types import (
    CheckpointInfo,
    CrossGenerationErrorAudit,
    DimensionSpec,
    ParameterSpec,
    PlotRequest,
    PredictionResult,
    ProgressCallback,
    RealResult,
    _check_cancelled,
)


def sample_real_results_by_generation(
    results: Sequence[RealResult],
    sample_fraction: float,
    *,
    random_seed: int | None = None,
) -> tuple[RealResult, ...]:
    """Sample each generation independently, without replacement."""

    fraction = float(sample_fraction)
    if not math.isfinite(fraction) or not 0.0 < fraction <= 1.0:
        raise ValueError("sample_fraction must be greater than 0 and at most 1")
    grouped: dict[int, list[RealResult]] = defaultdict(list)
    for result in results:
        grouped[int(result.generation)].append(result)
    rng = np.random.default_rng(random_seed)
    selected: list[RealResult] = []
    for generation in sorted(grouped):
        generation_rows = grouped[generation]
        count = min(
            len(generation_rows),
            max(1, math.ceil(len(generation_rows) * fraction)),
        )
        indices = np.sort(
            rng.choice(len(generation_rows), size=count, replace=False)
        )
        selected.extend(generation_rows[int(index)] for index in indices)
    return tuple(selected)


@dataclass(frozen=True)
class _HistoricalRow:
    generation: int
    normalized_values: tuple[float, ...]
    costs: tuple[float, ...]
    raw_sample: tuple[Mapping[str, object], ...]


class SurrogateWorkspace:
    """Read-only data and prediction access used by the GUI and tests."""

    def __init__(self, workspace: str | Path) -> None:
        self.root = Path(workspace).expanduser().resolve()
        self.config = load_config(self.root)
        self.checkpoints = discover_checkpoints(
            self.config.workspace.surrogate_checkpoint_dir,
            parameter_definition_signature=(
                job_template_api.get_parameter_definition_signature(self.root)
            ),
        )
        if not self.checkpoints:
            raise FileNotFoundError(
                "no trained surrogate checkpoints found below "
                f"{self.config.workspace.surrogate_checkpoint_dir}"
            )

        definitions = job_template_api.get_parameter_definitions(self.root)
        self.parameters = tuple(
            ParameterSpec(
                name=parameter.name,
                unit=str(parameter.unit or ""),
                ranges=tuple(
                    (float(bounds[0]), float(bounds[1]))
                    for bounds in parameter.ranges
                ),
            )
            for parameter in definitions
        )
        self.objective_names = job_template_api.get_objective_names(self.root)
        self.real_results = self._load_real_results()
        if not self.real_results:
            raise ValueError("workspace has no completed generation results")
        self._real_by_job = {
            item.job_name: item
            for item in self.real_results
        }
        self._template_sample = self.load_true_sample(
            self.real_results[0].job_name
        )
        self.rawdata_names = rawdata_names(self._template_sample)
        self._predictor: CheckpointPredictor | None = None
        self._predictor_lock = threading.RLock()

    def _load_real_results(self) -> tuple[RealResult, ...]:
        output: list[RealResult] = []
        for record in list_records(self.root):
            if str(record.get("status")) != "completed":
                continue
            generation_raw = record.get("generation_index")
            if generation_raw is None:
                continue
            raw_values = tuple(float(value) for value in record["raw_variables"])
            try:
                normalized = job_template_api.normalize_variables(
                    self.root,
                    raw_values,
                )
            except (TypeError, ValueError, KeyError):
                continue
            population_raw = record.get("population_index")
            output.append(
                RealResult(
                    job_name=str(record["job_name"]),
                    generation=int(generation_raw),
                    population_index=(
                        None
                        if population_raw is None
                        else int(population_raw)
                    ),
                    raw_values=raw_values,
                    normalized_values=tuple(
                        float(value)
                        for value in normalized
                    ),
                )
            )
        return tuple(
            sorted(
                output,
                key=lambda item: (
                    item.generation,
                    (
                        item.population_index
                        if item.population_index is not None
                        else 1_000_000_000
                    ),
                    item.job_name,
                ),
            )
        )

    @property
    def generations(self) -> tuple[int, ...]:
        return tuple(
            sorted({item.generation for item in self.real_results})
        )

    def results_for_generation(
        self,
        generation: int,
    ) -> tuple[RealResult, ...]:
        return tuple(
            item
            for item in self.real_results
            if item.generation == int(generation)
        )

    def dimensions_for_rawdata(
        self,
        item_index: int,
    ) -> tuple[DimensionSpec, ...]:
        return rawdata_dimensions(self._template_sample, item_index)

    def checkpoint_for_generation(
        self,
        generation: int,
    ) -> CheckpointInfo:
        for checkpoint in self.checkpoints:
            if checkpoint.generation == int(generation):
                return checkpoint
        raise KeyError(generation)

    def denormalize(
        self,
        normalized_values: Sequence[float],
    ) -> tuple[float, ...]:
        return tuple(
            float(value)
            for value in job_template_api.denormalize_variables(
                self.root,
                tuple(float(value) for value in normalized_values),
            )
        )

    def load_true_sample(
        self,
        job_name: str,
    ) -> tuple[Mapping[str, object], ...]:
        rows = get_rawdata_samples(
            self.root,
            job_names=(str(job_name),),
            status="completed",
            as_paths=False,
        )
        if not rows:
            raise FileNotFoundError(
                f"recorded rawData is missing for {job_name}"
            )
        return tuple(rows[0][1])

    def load_true_costs(
        self,
        result: RealResult,
        sample: Sequence[Mapping[str, object]] | None = None,
    ) -> tuple[float, ...]:
        selected = (
            self.load_true_sample(result.job_name)
            if sample is None
            else sample
        )
        rows = job_template_api.calculate_cost(
            self.root,
            (tuple(selected),),
            raw_variables=(result.raw_values,),
        )
        return tuple(float(value) for value in rows[0])

    def _get_predictor(self, generation: int) -> CheckpointPredictor:
        with self._predictor_lock:
            if (
                self._predictor is None
                or self._predictor.checkpoint.generation != int(generation)
            ):
                self._predictor = CheckpointPredictor(
                    self.root,
                    self.checkpoint_for_generation(generation),
                    self._template_sample,
                )
            return self._predictor

    def predict_one(
        self,
        checkpoint_generation: int,
        normalized_values: Sequence[float],
        *,
        true_job_name: str | None = None,
        plot_request: PlotRequest | None = None,
    ) -> PredictionResult:
        normalized = tuple(float(value) for value in normalized_values)
        predictor = self._get_predictor(checkpoint_generation)
        samples, costs, member_batches = predictor.predict(
            (normalized,),
            include_members=True,
        )
        true_sample = None
        true_costs = None
        if true_job_name:
            result = self._real_by_job[str(true_job_name)]
            true_sample = self.load_true_sample(result.job_name)
            true_costs = self.load_true_costs(result, true_sample)
        predicted_plot = None
        member_plots = ()
        plot_note = ""
        if (
            plot_request is not None
            and not self._plot_request_is_on_grid(plot_request)
        ):
            predicted_plot, member_plots = predictor.predict_plot(
                (normalized,),
                plot_request,
            )
            plot_note = (
                "Off-grid rawData query; no recorded real overlay exists. "
                "Objective comparison still uses the checkpoint grid."
            )
        return PredictionResult(
            checkpoint_generation=int(checkpoint_generation),
            normalized_values=normalized,
            raw_values=self.denormalize(normalized),
            predicted_sample=samples[0],
            member_samples=tuple(batch[0] for batch in member_batches),
            predicted_costs=tuple(float(value) for value in costs[0]),
            true_sample=true_sample,
            true_costs=true_costs,
            true_job_name=true_job_name,
            predicted_plot=predicted_plot,
            member_plots=member_plots,
            plot_note=plot_note,
        )

    def _plot_request_is_on_grid(self, request: PlotRequest) -> bool:
        dimensions = self.dimensions_for_rawdata(request.item_index)
        fixed = request.fixed_map
        for dimension in dimensions:
            if dimension.index in request.plotted_dimensions:
                continue
            if dimension.index not in fixed:
                return False
            coordinates = np.asarray(
                dimension.coordinates,
                dtype=np.float64,
            ).reshape(-1)
            value = float(fixed[dimension.index])
            tolerance = 1e-10 * max(
                1.0,
                abs(value),
                float(np.max(np.abs(coordinates)))
                if coordinates.size
                else 1.0,
            )
            if not np.any(
                np.isclose(
                    coordinates,
                    value,
                    rtol=1e-10,
                    atol=tolerance,
                )
            ):
                return False
        return True

    def _sampled_historical_rows(
        self,
        *,
        sample_fraction: float,
        random_seed: int | None,
        cancel_event: threading.Event | None,
    ) -> tuple[_HistoricalRow, ...]:
        selected = sample_real_results_by_generation(
            self.real_results,
            sample_fraction,
            random_seed=random_seed,
        )
        _check_cancelled(cancel_event)
        raw_by_job = {
            str(job_name): tuple(sample)
            for job_name, sample in get_rawdata_samples(
                self.root,
                job_names=tuple(item.job_name for item in selected),
                status="completed",
                as_paths=False,
            )
        }
        _check_cancelled(cancel_event)
        missing = tuple(
            item.job_name
            for item in selected
            if item.job_name not in raw_by_job
        )
        if missing:
            raise FileNotFoundError(
                f"recorded rawData is missing for "
                f"{len(missing)} sampled result(s)"
            )
        samples = tuple(
            raw_by_job[item.job_name]
            for item in selected
        )
        costs = job_template_api.calculate_cost(
            self.root,
            samples,
            raw_variables=tuple(item.raw_values for item in selected),
        )
        _check_cancelled(cancel_event)
        return tuple(
            _HistoricalRow(
                generation=item.generation,
                normalized_values=item.normalized_values,
                costs=tuple(float(value) for value in cost_row),
                raw_sample=tuple(sample),
            )
            for item, cost_row, sample in zip(selected, costs, samples)
        )

    def calculate_error_audit(
        self,
        *,
        sample_fraction: float = 1.0,
        random_seed: int | None = None,
        cancel_event: threading.Event | None = None,
        progress: ProgressCallback | None = None,
        batch_size: int = 512,
        cuda_sample_batch: int = 128,
    ) -> CrossGenerationErrorAudit:
        """Run expensive predictions once and retain compact error aggregates."""

        rows = self._sampled_historical_rows(
            sample_fraction=sample_fraction,
            random_seed=random_seed,
            cancel_event=cancel_event,
        )
        if not rows:
            raise ValueError("workspace has no completed historical objective rows")
        by_generation: dict[int, list[_HistoricalRow]] = defaultdict(list)
        for row in rows:
            by_generation[row.generation].append(row)

        optimization_generations = tuple(sorted(by_generation))
        checkpoint_generations = tuple(
            checkpoint.generation
            for checkpoint in self.checkpoints
        )
        cost_shape = (
            len(optimization_generations),
            len(checkpoint_generations),
            len(self.objective_names),
        )
        raw_shape = (
            len(optimization_generations),
            len(checkpoint_generations),
            len(self.rawdata_names),
        )
        relative_sums = np.zeros(cost_shape, dtype=np.float64)
        relative_counts = np.zeros(cost_shape, dtype=np.int64)
        absolute_sums = np.zeros(cost_shape, dtype=np.float64)
        absolute_counts = np.zeros(cost_shape, dtype=np.int64)
        raw_relative_sums = np.zeros(raw_shape, dtype=np.float64)
        raw_relative_counts = np.zeros(raw_shape, dtype=np.int64)
        raw_absolute_sums = np.zeros(raw_shape, dtype=np.float64)
        raw_absolute_counts = np.zeros(raw_shape, dtype=np.int64)

        ordered_rows = tuple(
            row
            for generation in optimization_generations
            for row in by_generation[generation]
        )
        sample_counts = tuple(
            len(by_generation[generation])
            for generation in optimization_generations
        )
        all_normalized = tuple(
            row.normalized_values
            for row in ordered_rows
        )
        all_true_costs = tuple(row.costs for row in ordered_rows)
        all_raw_samples = tuple(row.raw_sample for row in ordered_rows)
        total_predictions = len(ordered_rows) * len(checkpoint_generations)
        completed_predictions = 0
        epsilon = float(
            getattr(self.config, "SURROGATE_RELATIVE_ERROR_EPS", 1e-8)
        )
        true_flat_cache: dict[tuple[object, ...], np.ndarray] = {}

        for checkpoint_column, checkpoint in enumerate(self.checkpoints):
            _check_cancelled(cancel_event)
            predictor = CheckpointPredictor(
                self.root,
                checkpoint,
                self._template_sample,
            )
            schema_key = (
                int(predictor.schema.flat_dim),
                *(
                    (
                        slot.item_index,
                        slot.key,
                        slot.shape,
                        slot.start,
                        slot.end,
                        slot.field_id,
                    )
                    for slot in predictor.schema.modeled_slots
                ),
            )
            true_flats = true_flat_cache.get(schema_key)
            if true_flats is None:
                true_flats = flatten_samples_for_schema(
                    predictor.schema,
                    all_raw_samples,
                )
                true_flat_cache[schema_key] = true_flats
            prediction = predictor.predict_audit_rows(
                all_normalized,
                true_flats,
                relative_epsilon=epsilon,
                batch_size=batch_size,
                cuda_sample_batch=cuda_sample_batch,
                cancel_event=cancel_event,
                progress=progress,
                progress_offset=completed_predictions,
                progress_total=total_predictions,
            )
            completed_predictions += len(ordered_rows)

            offset = 0
            for generation_row, generation in enumerate(
                optimization_generations
            ):
                count = len(by_generation[generation])
                row_slice = slice(offset, offset + count)
                true_matrix = np.asarray(
                    all_true_costs[row_slice],
                    dtype=float,
                )
                predicted_matrix = np.asarray(
                    prediction.costs[row_slice],
                    dtype=float,
                )
                offset += count
                if (
                    true_matrix.ndim != 2
                    or predicted_matrix.shape != true_matrix.shape
                    or true_matrix.shape[1] != len(self.objective_names)
                ):
                    raise ValueError(
                        "historical and predicted objective matrices do not "
                        "match the current task definition"
                    )
                absolute = np.abs(predicted_matrix - true_matrix)
                relative = absolute / np.maximum(
                    np.abs(true_matrix),
                    epsilon,
                )
                absolute_finite = np.isfinite(absolute)
                relative_finite = np.isfinite(relative)
                absolute_sums[generation_row, checkpoint_column] = np.sum(
                    np.where(absolute_finite, absolute, 0.0),
                    axis=0,
                )
                absolute_counts[generation_row, checkpoint_column] = np.sum(
                    absolute_finite,
                    axis=0,
                    dtype=np.int64,
                )
                relative_sums[generation_row, checkpoint_column] = np.sum(
                    np.where(relative_finite, relative, 0.0),
                    axis=0,
                )
                relative_counts[generation_row, checkpoint_column] = np.sum(
                    relative_finite,
                    axis=0,
                    dtype=np.int64,
                )
                raw_absolute_sums[
                    generation_row,
                    checkpoint_column,
                ] = np.sum(
                    prediction.raw_absolute_sums[row_slice],
                    axis=0,
                )
                raw_absolute_counts[
                    generation_row,
                    checkpoint_column,
                ] = np.sum(
                    prediction.raw_absolute_counts[row_slice],
                    axis=0,
                    dtype=np.int64,
                )
                raw_relative_sums[
                    generation_row,
                    checkpoint_column,
                ] = np.sum(
                    prediction.raw_relative_sums[row_slice],
                    axis=0,
                )
                raw_relative_counts[
                    generation_row,
                    checkpoint_column,
                ] = np.sum(
                    prediction.raw_relative_counts[row_slice],
                    axis=0,
                    dtype=np.int64,
                )
            if progress is not None:
                progress(
                    completed_predictions,
                    total_predictions,
                    f"Checkpoint {checkpoint.generation} complete",
                )
            predictor_used_cuda = predictor.device.type == "cuda"
            del predictor
            if predictor_used_cuda:
                torch.cuda.empty_cache()

        _check_cancelled(cancel_event)
        return CrossGenerationErrorAudit(
            checkpoint_generations=checkpoint_generations,
            optimization_generations=optimization_generations,
            objective_names=self.objective_names,
            rawdata_names=self.rawdata_names,
            sample_counts=sample_counts,
            relative_sums=relative_sums,
            relative_counts=relative_counts,
            absolute_sums=absolute_sums,
            absolute_counts=absolute_counts,
            raw_relative_sums=raw_relative_sums,
            raw_relative_counts=raw_relative_counts,
            raw_absolute_sums=raw_absolute_sums,
            raw_absolute_counts=raw_absolute_counts,
            sample_fraction=float(sample_fraction),
        )
