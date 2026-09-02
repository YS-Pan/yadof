"""Transient real-simulation oracle for the packaged perfect-GPSAF experiment.

Only explicitly declared physical failures become failed +inf predictions.
Task import, interface, rawData and cost errors are fatal contract violations.
No evaluation-manager request, recorder or optimization history is created here.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
from pathlib import Path
import struct
import tempfile
import threading
from types import MappingProxyType, SimpleNamespace

from yadof.evaluate_manager.fast_resources import plan_fast_workers
from yadof.job_template import (
    StructuredRawDataSample, assign_parameters, calculate_costs_from_raw_data,
    validate_named_rawdata_items,
)
from yadof.surrogate import SurrogateContractError, SurrogatePrediction, SurrogateTrainingData
from yadof.task_loader import task_module


def _json_cost(row):
    return [value if math.isfinite(value) else None for value in row]


class PerfectSimulationOracle:
    def __init__(self):
        self._lock = threading.Lock()
        self._calls = self._simulations = self._failures = self._errors = 0
        self._matched = 0
        self._workers = 0

    def validate(self, config, problem):
        if config.EVALUATION_MODE != "fast" or problem.objective_count < 1:
            raise SurrogateContractError("perfect oracle requires fast mode and positive objective width")

    def semantic_identity(self, config, problem):
        return {"component": "perfect-simulation-oracle", "contract": "rawdata-cost-items",
                "failure_cost": "+inf", "recording": "selection-only", "objectives": problem.objective_count}

    def training_data(self, dataset, cost_table, **kwargs):
        # No fitted model: do not load the growing rawData archive just to establish
        # readiness. The real archive stays owned by the optimization workflow.
        return SurrogateTrainingData(tuple(dataset.parameter_names), (), ())

    def latest_trained_generation(self, context, training_data):
        # There is no fitted state to age: the real kernel uses this exact context.
        return context.generation_index

    def has_trained_state(self, context, training_data):
        return True

    def ensure_fresh_enough(self, context, training_data):
        return SimpleNamespace(action="oracle-always-fresh", pending_generation_index=None, error="")

    def start_training(self, context, training_data):
        return SimpleNamespace(action="oracle-no-training", pending_generation_index=None, error="")

    def finish_training(self, context):
        return self.start_training(context, None)

    def estimate_initial_error(self, context, training_data, *, folds=5):
        # This provider evaluates the same real kernel and cost function. There is
        # no fitted approximation to cross-validate. Selected rows are audited.
        return (0.0,) * context.problem.objective_count

    def _one(self, evaluator, failure_types, context, parameters, index, scratch):
        with self._lock:
            self._simulations += 1
        try:
            with tempfile.TemporaryDirectory(prefix=f"p{index:04d}-", dir=scratch) as directory:
                task_context = MappingProxyType({
                    "evaluation_name": f"oracle-g{context.generation_index:04d}-p{index:04d}",
                    "scratch_dir": Path(directory),
                    "timeout_sec": float(context.config.EVALUATION_TIMEOUT_SEC),
                    "environment": MappingProxyType({}),
                    "run_id": context.run_id,
                    "optimization_index": context.optimization_index,
                    "generation_index": context.generation_index,
                    "population_index": index,
                    "task_static_signature": context.snapshot.evaluation_fingerprint,
                })
                output = evaluator(parameters, task_context)
                if isinstance(output, tuple):
                    from collections.abc import Mapping
                    if len(output) != 2 or not isinstance(output[1], Mapping):
                        raise TypeError("fast evaluation must return rawData or (rawData, diagnostics)")
                    output = output[0]
                sample = StructuredRawDataSample.from_items(validate_named_rawdata_items(output))
                return sample, ""
        except failure_types as exc:
            with self._lock:
                self._failures += 1
            return None, f"{type(exc).__name__}: {exc}"[:1000]

    def predict_for_selection(self, context, population, training_data=None):
        if not isinstance(training_data, SurrogateTrainingData):
            raise SurrogateContractError("perfect oracle requires explicit SurrogateTrainingData")
        rows = tuple(tuple(float(value) for value in row) for row in population)
        try:
            self._calls += 1
            assigned = tuple(MappingProxyType({p.name: float(p.value) for p in assign_parameters(
                context.config.workspace, row)}) for row in rows)
            plan = plan_fast_workers(context.config, population_size=len(rows),
                                     configured_max=int(context.config.FAST_EVALUATION_MAX_WORKERS))
            self._workers = int(plan.worker_count)
            scratch = context.config.workspace.fast_evaluation_scratch_dir / "perfect-oracle"
            scratch.mkdir(parents=True, exist_ok=True)
            with task_module(context.config.workspace, "evaluation") as module:
                failure_types = getattr(module, "PHYSICAL_FAILURE_TYPES", ())
                if not isinstance(failure_types, tuple) or any(
                    not isinstance(t, type) or not issubclass(t, Exception) or t in (Exception, BaseException)
                    for t in failure_types
                ):
                    raise TypeError("PHYSICAL_FAILURE_TYPES must explicitly list specific exception types")
                with ThreadPoolExecutor(max_workers=self._workers, thread_name_prefix="perfect-oracle") as pool:
                    futures = [pool.submit(self._one, module.evaluate_rawdata, failure_types,
                                           context, parameters, i, scratch)
                               for i, parameters in enumerate(assigned)]
                    outcomes = tuple(future.result() for future in futures)
            successful = [i for i, (sample, _) in enumerate(outcomes) if sample is not None]
            computed = calculate_costs_from_raw_data(
                context.config.workspace,
                tuple(outcomes[i][0].cost_items() for i in successful),
                tuple(assigned[i] for i in successful),
            ) if successful else ()
            if len(computed) != len(successful):
                raise ValueError("cost interface returned the wrong number of oracle rows")
            by_index = dict(zip(successful, computed))
            costs = tuple(tuple(by_index.get(i, (math.inf,) * context.problem.objective_count))
                          for i in range(len(rows)))
            if any(len(row) != context.problem.objective_count for row in costs):
                raise ValueError("oracle objective width differs from the real problem")
            prediction = SurrogatePrediction(
                state_signature=hashlib.sha256(("perfect-oracle:" + context.snapshot.evaluation_fingerprint
                                                + context.snapshot.interpretation_fingerprint).encode()).hexdigest(),
                training_data_digest=training_data.content_digest,
                normalized_variables=rows,
                raw_data=tuple(sample for sample, _ in outcomes), costs=costs,
                intervals=tuple(tuple((v, v) for v in row) for row in costs),
                interpretation_fingerprint=context.snapshot.interpretation_fingerprint,
                valid_mask=tuple(sample is not None for sample, _ in outcomes),
                diagnostics={"perfect_oracle": True, "oracle_recorded_in_history": False},
            )
            self._audit(context, {"event": "prediction", "generation": context.generation_index + 1,
                                  "rows": len(rows), "physical_failures": len(rows) - len(successful),
                                  "errors": [error for _, error in outcomes if error], **self.diagnostics()})
            return prediction
        except SurrogateContractError:
            raise
        except Exception as exc:
            self._errors += 1
            try:
                self._audit(context, {"event": "contract-error", "error": f"{type(exc).__name__}: {exc}",
                                      **self.diagnostics()})
            except Exception as audit_error:
                raise SurrogateContractError(f"oracle audit persistence failed: {audit_error}") from exc
            raise SurrogateContractError(f"perfect oracle {type(exc).__name__}: {exc}") from exc

    def verify_selected(self, context, selected, actual_costs):
        if selected.predicted_costs and len(selected.predicted_costs) != len(actual_costs):
            raise SurrogateContractError("selected prediction and real outcome counts differ")
        pairs = []
        for index, (predicted, actual) in enumerate(zip(selected.predicted_costs, actual_costs)):
            if predicted is None:
                continue
            a, b = tuple(predicted), tuple(float(v) for v in actual)
            equal = len(a) == len(b) and struct.pack(f"{len(a)}d", *a) == struct.pack(f"{len(b)}d", *b)
            pairs.append({"index": index, "prediction": _json_cost(a), "actual": _json_cost(b), "bitwise_equal": equal})
        self._matched += sum(pair["bitwise_equal"] for pair in pairs)
        self._audit(context, {"event": "selected-real-correspondence", "generation": context.generation_index + 1,
                              "pairs": pairs, **self.diagnostics()})
        if any(not pair["bitwise_equal"] for pair in pairs):
            raise SurrogateContractError("perfect oracle selected prediction differs from formal real evaluation")

    def _audit(self, context, payload):
        root = context.config.workspace.root / "oracle_audit"
        root.mkdir(parents=True, exist_ok=True)
        with (root / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, allow_nan=False, sort_keys=True) + "\n")

    def diagnostics(self):
        return {"oracle_prediction_calls": self._calls, "oracle_simulation_evaluations": self._simulations,
                "oracle_simulation_failures": self._failures, "oracle_contract_errors": self._errors,
                "oracle_selected_bitwise_matches": self._matched, "oracle_worker_count": self._workers,
                "oracle_recorded_in_history": False}
