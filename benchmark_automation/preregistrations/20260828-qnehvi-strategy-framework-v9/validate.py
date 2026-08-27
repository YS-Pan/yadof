"""Read-only validation of the 082611 framework and inherited blockers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yadof
from yadof.optimize import posterior_assisted, qnehvi
from yadof.surrogate import conditional_inr_posterior, hierarchical_cae
from yadof.surrogate.exploitation import (
    PERFORMANCE_NOT_ACCEPTED,
    POSTERIOR_UNCALIBRATED,
)


ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = ROOT.parent.parent.parent
PLAN_PATH = ROOT / "framework_plan.json"
V8_RESULT_PATH = (
    ROOT.parent
    / "20260827-new-surrogate-qnehvi-v8"
    / "calibration_result_receipt.json"
)
SOURCE_PATHS = (
    "benchmark_automation/preregistrations/20260828-qnehvi-strategy-framework-v9/canary_inputs/config.py",
    "benchmark_automation/preregistrations/20260828-qnehvi-strategy-framework-v9/canary_inputs/calc_cost.py",
    "benchmark_automation/preregistrations/20260828-qnehvi-strategy-framework-v9/canary_inputs/optimization.py",
    "src/yadof/optimize/posterior_assisted.py",
    "src/yadof/optimize/qnehvi_acquisition.py",
    "src/yadof/surrogate/exploitation.py",
    "tests/test_posterior_assisted_strategy.py",
)


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain one JSON object")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate() -> dict[str, object]:
    plan = _json(PLAN_PATH)
    v8 = _json(V8_RESULT_PATH)
    _require(
        plan.get("protocol")
        == "yadof.082611.posterior-assisted-framework-preregistration",
        "framework plan protocol drifted",
    )
    _require(
        plan.get("status")
        == "sealed-before-installed-wheel-and-real-canary-validation",
        "framework plan is not sealed",
    )
    aggregate = dict(v8["aggregate_result"])
    boundary = dict(v8["scientific_boundary"])
    _require(
        int(aggregate["rawdata_calibrated_cell_count"]) == 0,
        "v8 rawData calibration result changed",
    )
    _require(
        int(aggregate["applicability_calibrated_cell_count"]) == 0,
        "v8 applicability calibration result changed",
    )
    _require(
        aggregate["all_artifacts_non_transferable"] is True,
        "v8 transferability boundary changed",
    )
    _require(
        aggregate["usable_probability_capability_for_082611"] is False,
        "v8 unexpectedly exposes an exploitation capability",
    )
    _require(boundary["performance_accepted"] is False, "v8 performance changed")
    _require(
        boundary["formal_082612_same_budget_benchmark_completed"] is False,
        "082612 benchmark boundary changed",
    )

    component_states = {}
    for name, component in (
        ("conditional-inr", conditional_inr_posterior()),
        ("hierarchical-cae", hierarchical_cae()),
    ):
        identity = dict(component.exploitation_semantic_identity(None, None))
        _require(
            identity["performance_status"] == PERFORMANCE_NOT_ACCEPTED,
            f"{name} performance blocker changed",
        )
        _require(
            identity["posterior_status"] == POSTERIOR_UNCALIBRATED,
            f"{name} posterior blocker changed",
        )
        _require(identity["transferable"] is False, f"{name} became transferable")
        component_states[name] = identity

    acquisition = qnehvi(batch_size=1, greedy_restarts=1)
    _require(acquisition.batch_size == 1, "qnehvi public factory changed")
    _require(callable(posterior_assisted), "posterior_assisted is not callable")
    installed_origin = str(Path(yadof.__file__).resolve())
    _require(
        "site-packages" in installed_origin.casefold(),
        "validator must use the installed wheel",
    )
    source_hashes = {}
    for relative in SOURCE_PATHS:
        path = REPOSITORY_ROOT / relative
        _require(path.is_file(), f"required framework file is missing: {relative}")
        source_hashes[relative] = _sha256(path)
    return {
        "protocol": "yadof.082611.framework-validation-receipt",
        "protocol_version": 1,
        "status": "valid-fail-closed-framework-inputs",
        "plan_sha256": _sha256(PLAN_PATH),
        "v8_result_sha256": _sha256(V8_RESULT_PATH),
        "installed_yadof_origin": installed_origin,
        "installed_yadof_version": yadof.__version__,
        "source_hashes": source_hashes,
        "current_component_states": component_states,
        "architecture_performance_accepted": False,
        "transferable_calibration_available": False,
        "082612_performance_started": False,
        "simulator_launched": False
    }


if __name__ == "__main__":
    print(json.dumps(validate(), sort_keys=True, allow_nan=False))
