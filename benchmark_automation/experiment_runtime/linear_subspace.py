"""Design-partitioned four-arm PCA/SVD benchmark runtime."""

from __future__ import annotations

import json
from io import BytesIO
from importlib import metadata
from pathlib import Path
import threading
import time
from typing import Mapping, Sequence

import numpy as np
import psutil

from yadof.job_template import api as job_template_api
from yadof.recorded_data import api as recorded_api
from yadof.surrogate import pca_svd


CASE_IDS = ("saw", "chrono", "test-com")
ARM_IDS = (
    "pca-reconstruction-oracle",
    "svd-reconstruction-oracle",
    "pca-ridge-rawdata-surrogate",
    "svd-ridge-rawdata-surrogate",
)


def load_partition(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("protocol") != "yadof.pca-svd-design-partition" or int(
        payload.get("protocol_version", 0)
    ) != 1:
        raise ValueError("partition must use yadof.pca-svd-design-partition v1")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("partition must declare case rows")
    seen = set()
    for case in cases:
        if not isinstance(case, Mapping):
            raise ValueError("partition case must be an object")
        case_id = str(case.get("id", ""))
        if case_id not in CASE_IDS or case_id in seen:
            raise ValueError(f"invalid or duplicate case id: {case_id!r}")
        seen.add(case_id)
        workspace = Path(str(case.get("workspace", "")))
        if not workspace.is_absolute() or not workspace.is_dir():
            raise ValueError(f"case {case_id!r} workspace must be an existing absolute path")
        train = tuple(str(value) for value in case.get("training_job_names", ()))
        validation = tuple(str(value) for value in case.get("validation_job_names", ()))
        if not train or not validation or len(train) != len(set(train)) or len(validation) != len(set(validation)):
            raise ValueError(f"case {case_id!r} needs unique non-empty train/validation rows")
        if set(train) & set(validation):
            raise ValueError(f"case {case_id!r} train/validation design rows overlap")
        if any("test" in str(key).lower() for key in case if key != "id"):
            raise ValueError("v11 partition must not contain test locators")
    return payload


def preflight(path: str | Path) -> dict[str, object]:
    payload = load_partition(path)
    try:
        torch_version = metadata.version("torch")
    except metadata.PackageNotFoundError as exc:
        raise RuntimeError(
            "PCA/SVD validation requires the yadof surrogate extra (torch)"
        ) from exc
    return {
        "status": "preflight-valid-no-fit",
        "case_ids": [str(case["id"]) for case in payload["cases"]],
        "arm_ids": list(ARM_IDS),
        "measured_run_started": False,
        "torch_version": torch_version,
    }


def run_partition(path: str | Path) -> dict[str, object]:
    payload = load_partition(path)
    authority = payload.get("execution_authority")
    if authority != "explicit-user-authorized-measured-v11-run":
        raise PermissionError("measured v11 run needs explicit execution authority")
    thresholds = payload.get("thresholds")
    if not isinstance(thresholds, Mapping) or thresholds.get("sealed") is not True:
        raise PermissionError("measured v11 run needs sealed thresholds")
    results = []
    for case in payload["cases"]:
        results.extend(_run_case(case))
    _add_oracle_gaps(results)
    return {
        "protocol": "yadof.pca-svd-linear-subspace-results",
        "protocol_version": 1,
        "plan_id": "20260828-gate0-v11-pca-svd-linear-subspace",
        "results": results,
        "formal_claim_allowed": False,
        "posterior_exploitation_allowed": False,
    }


def _run_case(case: Mapping[str, object]) -> list[dict[str, object]]:
    workspace = Path(str(case["workspace"]))
    training_names = tuple(str(value) for value in case["training_job_names"])
    validation_names = tuple(str(value) for value in case["validation_job_names"])
    historical = {
        name: (tuple(parameters), tuple(costs))
        for name, parameters, costs in recorded_api.get_historical_results(workspace)
    }
    named = dict(
        recorded_api.get_named_rawdata_samples(
            workspace,
            job_names=training_names + validation_names,
            status="completed",
        )
    )
    missing = tuple(
        name
        for name in training_names + validation_names
        if name not in historical or name not in named
    )
    if missing:
        raise ValueError(f"partition rows are missing public recorded evidence: {missing!r}")
    train_x = tuple(historical[name][0] for name in training_names)
    validation_x = tuple(historical[name][0] for name in validation_names)
    train_samples = tuple(named[name] for name in training_names)
    validation_samples = tuple(named[name] for name in validation_names)
    true_costs = tuple(historical[name][1] for name in validation_names)
    parameter_names = tuple(job_template_api.get_parameter_names(workspace))
    output = []
    for arm_id in ARM_IDS:
        decomposition = arm_id.split("-", 1)[0]
        component = pca_svd(decomposition=decomposition, rank=32)
        started = time.perf_counter()
        with _resource_monitor() as resources:
            if "oracle" in arm_id:
                codec = component.fit_codec(train_samples)
                fit_wall = time.perf_counter() - started
                prediction_started = time.perf_counter()
                prediction = component.evaluate_oracle(codec, validation_samples).samples
                predicted_costs = None
                checkpoint_bytes = _serialized_state_bytes(codec)
            else:
                model = component.fit_deployable(
                    train_x,
                    train_samples,
                    parameter_names=parameter_names,
                )
                codec = model
                fit_wall = time.perf_counter() - started
                prediction_started = time.perf_counter()
                prediction = component.predict_rawdata(model, validation_x)
                raw_variables = tuple(
                    job_template_api.denormalize_variables(workspace, row)
                    for row in validation_x
                )
                predicted_costs = tuple(
                    tuple(float(value) for value in row)
                    for row in job_template_api.calculate_costs_from_raw_data(
                        workspace,
                        tuple(sample.cost_items() for sample in prediction),
                        raw_variables=raw_variables,
                    )
                )
                checkpoint_bytes = _serialized_state_bytes(codec, model=model)
            predict_wall = time.perf_counter() - prediction_started
        row = {
            "case": str(case["id"]),
            "arm": arm_id,
            "diagnostic_only": "oracle" in arm_id,
            "field_metrics": _field_metrics(
                codec, train_samples, validation_samples, prediction
            ),
            "field_macro": {},
            "resources": {
                "fit_wall_sec": fit_wall,
                "predict_wall_sec": predict_wall,
                "peak_process_rss_bytes": resources[0],
                "peak_device_bytes": 0,
                "checkpoint_bytes": checkpoint_bytes,
            },
        }
        row["field_macro"] = _field_macro(row["field_metrics"])
        if predicted_costs is not None:
            row["cost_metrics"] = _cost_metrics(true_costs, predicted_costs)
        output.append(row)
    return output


class _resource_monitor:
    def __enter__(self):
        self.result = [int(psutil.Process().memory_info().rss)]
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._watch, daemon=True)
        self.thread.start()
        return self.result

    def _watch(self):
        process = psutil.Process()
        while not self.stop.wait(0.01):
            self.result[0] = max(self.result[0], int(process.memory_info().rss))

    def __exit__(self, exc_type, exc, traceback):
        self.stop.set()
        self.thread.join(timeout=1.0)


def _field_metrics(codec, training, truth, prediction):
    output = []
    train_maps = [sample.as_mapping() for sample in training]
    truth_maps = [sample.as_mapping() for sample in truth]
    predicted_maps = [sample.as_mapping() for sample in prediction]
    for field in codec.fields:
        filename, key = field.selector
        train = np.asarray([row[filename][key].reshape(-1) for row in train_maps])
        actual = np.asarray([row[filename][key].reshape(-1) for row in truth_maps])
        predicted = np.asarray(
            [row[filename][key].reshape(-1) for row in predicted_maps]
        )
        error = predicted - actual
        scale = max(float(np.sqrt(np.mean(np.var(train, axis=0)))), 1e-12)
        actual_energy = float(np.sum(np.square(actual)))
        residual_energy = float(np.sum(np.square(error)))
        output.append(
            {
                "selector": list(field.selector),
                "physical_mae": float(np.mean(np.abs(error))),
                "physical_rmse": float(np.sqrt(np.mean(np.square(error)))),
                "standardized_mae": float(np.mean(np.abs(error)) / scale),
                "standardized_rmse": float(np.sqrt(np.mean(np.square(error))) / scale),
                "explained_energy_ratio": 1.0
                - residual_energy / max(actual_energy, 1e-30),
                "requested_rank": field.requested_rank,
                "effective_rank": field.effective_rank,
                "singular_values": field.singular_values.tolist(),
                "reconstruction_energy_ratio": float(
                    np.sum(np.square(field.singular_values))
                )
                / max(float(np.sum(np.square(train - field.mean))), 1e-30),
            }
        )
    return output


def _serialized_state_bytes(codec, *, model=None) -> int:
    arrays = {}
    for index, field in enumerate(codec.fields):
        arrays[f"field_{index:04d}_mean"] = field.mean
        arrays[f"field_{index:04d}_basis"] = field.basis
        arrays[f"field_{index:04d}_singular_values"] = field.singular_values
    if model is not None:
        arrays["ridge_weights"] = model.ridge_weights
        arrays["coefficient_offsets"] = np.asarray(
            model.coefficient_offsets, dtype=np.int64
        )
    stream = BytesIO()
    np.savez_compressed(stream, **arrays)
    return len(stream.getvalue())


def _field_macro(rows):
    return {
        name: float(np.mean([row[name] for row in rows]))
        for name in ("standardized_mae", "standardized_rmse")
    }


def _cost_metrics(
    truth: Sequence[Sequence[float]], prediction: Sequence[Sequence[float]]
):
    actual = np.asarray(truth, dtype=np.float64)
    predicted = np.asarray(prediction, dtype=np.float64)
    error = predicted - actual
    return {
        "mae_per_objective": np.mean(np.abs(error), axis=0).tolist(),
        "rmse_per_objective": np.sqrt(np.mean(np.square(error), axis=0)).tolist(),
        "spearman_per_objective": [
            _spearman(actual[:, index], predicted[:, index])
            for index in range(actual.shape[1])
        ],
        "pareto_pairwise_consistency": _pareto_consistency(actual, predicted),
    }


def _spearman(left, right):
    left_rank = np.argsort(np.argsort(left, kind="stable"), kind="stable")
    right_rank = np.argsort(np.argsort(right, kind="stable"), kind="stable")
    if np.std(left_rank) == 0 or np.std(right_rank) == 0:
        return 1.0 if np.array_equal(left_rank, right_rank) else 0.0
    return float(np.corrcoef(left_rank, right_rank)[0, 1])


def _pareto_consistency(actual, predicted):
    matches = total = 0
    for left in range(len(actual)):
        for right in range(left + 1, len(actual)):
            actual_relation = (
                np.all(actual[left] <= actual[right]),
                np.all(actual[right] <= actual[left]),
            )
            predicted_relation = (
                np.all(predicted[left] <= predicted[right]),
                np.all(predicted[right] <= predicted[left]),
            )
            matches += actual_relation == predicted_relation
            total += 1
    return 1.0 if total == 0 else float(matches / total)


def _add_oracle_gaps(results):
    by_key = {(row["case"], row["arm"]): row for row in results}
    for row in results:
        if "ridge" not in row["arm"]:
            continue
        decomposition = row["arm"].split("-", 1)[0]
        oracle = by_key[
            (row["case"], f"{decomposition}-reconstruction-oracle")
        ]
        row["deployable_minus_oracle_field_macro"] = {
            name: row["field_macro"][name] - oracle["field_macro"][name]
            for name in row["field_macro"]
        }


__all__ = ["ARM_IDS", "CASE_IDS", "load_partition", "preflight", "run_partition"]
