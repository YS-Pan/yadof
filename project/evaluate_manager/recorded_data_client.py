from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from typing import Any

from .types import JobResult

_API_MODULE_CANDIDATES = ("project.recorded_data.api", "recorded_data.api")
_RECORD_FUNCTION_CANDIDATES = (
    "record_job_result",
    "write_job_result",
    "add_job_result",
    "record_evaluation",
    "add_evaluation",
)
_COST_FUNCTION_CANDIDATES = ("calculate_costs", "get_job_costs", "get_costs_for_job", "calculate_job_costs")


class RecordedDataApiUnavailable(RuntimeError):
    pass


def record_result(result: JobResult) -> tuple[float, ...] | None:
    api = _load_api_module()
    record_fn = _first_callable(api, _RECORD_FUNCTION_CANDIDATES)
    if record_fn is None:
        raise RecordedDataApiUnavailable(
            "recorded_data.api exists but has no supported record function: "
            + ", ".join(_RECORD_FUNCTION_CANDIDATES)
        )

    payload = _payload(result)
    response = _call_record_function(record_fn, payload)
    costs = _costs_from_response(response)
    if costs is not None:
        return costs

    cost_fn = _first_callable(api, _COST_FUNCTION_CANDIDATES)
    if cost_fn is None:
        return None
    return _costs_from_response(_call_cost_function(cost_fn, result.job_name))


def _load_api_module():
    errors = []
    for name in _API_MODULE_CANDIDATES:
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError as exc:
            errors.append(f"{name}: {exc}")
    raise RecordedDataApiUnavailable("Could not import recorded_data API. Tried: " + "; ".join(errors))


def _first_callable(module, names: tuple[str, ...]):
    for name in names:
        value = getattr(module, name, None)
        if callable(value):
            return value
    return None


def _payload(result: JobResult) -> dict[str, Any]:
    recorded_status = "completed" if result.status == "done" else result.status
    return {
        "job_name": result.job_name,
        "unnormalized_variables": result.unnormalized_variables,
        "raw_variables": result.unnormalized_variables,
        "raw_data_paths": tuple(Path(p) for p in result.raw_data_paths),
        "rawdata_source": tuple(Path(p) for p in result.raw_data_paths),
        "metadata": dict(result.metadata),
        "job_metadata": dict(result.metadata),
        "job_dir": Path(result.job_dir),
        "status": recorded_status,
    }


def _call_cost_function(fn, job_name: str):
    try:
        signature = inspect.signature(fn)
    except (TypeError, ValueError):
        signature = None
    if signature is not None and "job_names" in signature.parameters:
        kwargs: dict[str, Any] = {"job_names": (job_name,)}
        if "status" in signature.parameters:
            kwargs["status"] = None
        return fn(**kwargs)
    if signature is not None and "job_name" in signature.parameters:
        return fn(job_name=job_name)
    try:
        return fn(job_name=job_name)
    except TypeError:
        return fn(job_name)


def _call_record_function(fn, payload: dict[str, Any]):
    try:
        return fn(**payload)
    except TypeError as exc:
        filtered = _filter_payload_for_signature(fn, payload)
        if filtered == payload:
            raise exc
        return fn(**filtered)


def _filter_payload_for_signature(fn, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        signature = inspect.signature(fn)
    except (TypeError, ValueError):
        return payload
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in signature.parameters.values()):
        return payload
    return {key: value for key, value in payload.items() if key in signature.parameters}


def _costs_from_response(response) -> tuple[float, ...] | None:
    if response is None:
        return None
    if isinstance(response, dict):
        for key in ("costs", "cost", "objective_costs"):
            if key in response:
                return _as_cost_tuple(response[key])
        return None
    if isinstance(response, tuple) and len(response) == 1 and isinstance(response[0], tuple) and len(response[0]) == 2:
        return _as_cost_tuple(response[0][1])
    return _as_cost_tuple(response)


def _as_cost_tuple(value) -> tuple[float, ...] | None:
    if isinstance(value, (str, bytes)):
        return None
    try:
        return tuple(float(x) for x in value)
    except TypeError:
        try:
            return (float(value),)
        except (TypeError, ValueError):
            return None
