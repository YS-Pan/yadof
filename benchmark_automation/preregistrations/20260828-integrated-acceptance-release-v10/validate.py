"""Read-only validation of the 082612 integrated fail-closed release inputs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tomllib

import yadof
from yadof.optimize import posterior_assisted, qnehvi
from yadof.surrogate import conditional_inr_posterior, hierarchical_cae
from yadof.surrogate.exploitation import (
    PERFORMANCE_NOT_ACCEPTED,
    POSTERIOR_UNCALIBRATED,
)


ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = ROOT.parent.parent.parent
PLAN_PATH = ROOT / "acceptance_release_plan.json"
BENCHMARK_PATH = REPOSITORY_ROOT / "benchmark_automation" / "benchmark.toml"


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


def _mapping(value: object, label: str) -> dict[str, object]:
    _require(isinstance(value, dict), f"{label} must be an object")
    return dict(value)


def validate() -> dict[str, object]:
    plan = _json(PLAN_PATH)
    _require(
        plan.get("protocol")
        == "yadof.082612.integrated-acceptance-release-preregistration",
        "v10 plan protocol drifted",
    )
    _require(
        plan.get("status")
        == "sealed-before-v10-structural-regression-and-final-wheel-validation",
        "v10 plan is not sealed",
    )

    inherited = _mapping(plan.get("inherited_evidence"), "inherited_evidence")
    evidence: dict[str, dict[str, object]] = {}
    for version in ("v5", "v7", "v8", "v9"):
        declaration = _mapping(inherited.get(version), version)
        path = REPOSITORY_ROOT / str(declaration["path"])
        _require(path.is_file(), f"{version} evidence is missing")
        _require(
            _sha256(path) == declaration["sha256"],
            f"{version} frozen evidence hash drifted",
        )
        evidence[version] = _json(path)

    v5_decision = _mapping(evidence["v5"].get("decision"), "v5 decision")
    _require(v5_decision["representation_passed"] is False, "v5 representation changed")
    _require(v5_decision["quality_regime_passed"] is False, "v5 quality changed")
    _require(v5_decision["full_grid_gate_passed"] is False, "v5 gate changed")

    v7_mechanism = _mapping(evidence["v7"].get("mechanism_result"), "v7 mechanism")
    v7_science = _mapping(evidence["v7"].get("scientific_decision"), "v7 science")
    _require(v7_mechanism["coordinate_framework_executed"] is True, "v7 mechanism changed")
    _require(v7_mechanism["full_grid_remained_authoritative"] is True, "v7 authority changed")
    _require(v7_science["performance_accepted"] is False, "v7 performance changed")
    _require(
        v7_science["coordinate_performance_accepted"] is False,
        "v7 coordinate performance changed",
    )

    v8_aggregate = _mapping(evidence["v8"].get("aggregate_result"), "v8 aggregate")
    v8_boundary = _mapping(evidence["v8"].get("scientific_boundary"), "v8 boundary")
    _require(int(v8_aggregate["rawdata_calibrated_cell_count"]) == 0, "v8 rawData changed")
    _require(
        int(v8_aggregate["applicability_calibrated_cell_count"]) == 0,
        "v8 applicability changed",
    )
    _require(v8_aggregate["all_artifacts_non_transferable"] is True, "v8 transferability changed")
    _require(
        v8_aggregate["usable_probability_capability_for_082611"] is False,
        "v8 probability capability changed",
    )
    _require(v8_boundary["performance_accepted"] is False, "v8 performance boundary changed")
    _require(
        v8_boundary["formal_082612_same_budget_benchmark_completed"] is False,
        "v8 formal benchmark boundary changed",
    )

    _require(
        evidence["v9"].get("status")
        == "complete-framework-mechanism-performance-not-accepted",
        "v9 framework status changed",
    )
    v9_canary = _mapping(evidence["v9"].get("real_canary"), "v9 canary")
    v9_boundary = _mapping(evidence["v9"].get("scientific_boundary"), "v9 boundary")
    _require(int(v9_canary["completed"]) == 2, "v9 canary count changed")
    _require(v9_canary["surrogate_used"] is False, "v9 canary used a surrogate")
    _require(
        v9_canary["fallback_reason"] == "typed-exploitation-capability-blocked",
        "v9 fallback changed",
    )
    _require(
        v9_boundary["framework_may_control_current_exploitation"] is False,
        "v9 exploitation boundary changed",
    )

    component_states: dict[str, dict[str, object]] = {}
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
    _require(callable(posterior_assisted), "posterior_assisted is not callable")
    _require(qnehvi(batch_size=1, greedy_restarts=1).batch_size == 1, "qnehvi factory drifted")

    benchmark = tomllib.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
    performance = dict(benchmark["suites"]["performance"])
    _require(performance["purpose"] == "performance", "performance purpose changed")
    _require(performance["cases"] == ["saw", "chrono", "test-com"], "performance cases changed")
    _require(
        performance["arms"] == ["nsga3", "gpsaf-conditional-inr"],
        "performance arms changed without a new preregistration",
    )
    _require(performance["seeds"] == [104729], "performance seeds changed")
    budgets = benchmark["budgets"]["performance"]
    for case in performance["cases"]:
        for arm in performance["arms"]:
            budget = budgets[case][arm]
            _require(int(budget["population"]) == 100, "formal population changed")
            _require(int(budget["generations"]) == 20, "formal generations changed")

    matrix = list(plan["formal_comparison_matrix"])
    _require(len(matrix) == 7, "formal comparison matrix is incomplete")
    current_arms = {str(item["current_runner_arm"]) for item in matrix if item["current_runner_arm"]}
    _require(current_arms == set(performance["arms"]), "matrix/runner arm mapping drifted")
    missing_arms = [str(item["id"]) for item in matrix if item["current_runner_arm"] is None]
    _require(len(missing_arms) == 5, "unexpected formal arm readiness")

    gates = list(plan["acceptance_gates"])
    _require(
        all(
            item["status"] != "passed"
            for item in gates
            if item["id"] != "strategy-mechanism"
        ),
        "a scientific gate was silently opened",
    )
    phases = _mapping(plan.get("release_phases"), "release_phases")
    phase_b = _mapping(phases.get("phase_b"), "phase_b")
    phase_c = _mapping(phases.get("phase_c"), "phase_c")
    _require(phase_b["surrogate_may_control_exploitation"] is False, "Phase B exploitation opened")
    _require(phase_c["recommended_opt_in"] is False, "Phase C recommendation opened")
    reentry = list(plan["formal_reentry_conditions"])
    _require(
        [item["id"] for item in reentry] == [f"R{i}" for i in range(1, 10)],
        "re-entry contract drifted",
    )

    installed_origin = str(Path(yadof.__file__).resolve())
    _require("site-packages" in installed_origin.casefold(), "validator must use installed yadof")
    return {
        "protocol": "yadof.082612.integrated-acceptance-input-validation",
        "protocol_version": 1,
        "status": "valid-integrated-framework-formal-benchmark-blocked",
        "plan_sha256": _sha256(PLAN_PATH),
        "benchmark_toml_sha256": _sha256(BENCHMARK_PATH),
        "installed_yadof_origin": installed_origin,
        "installed_yadof_version": yadof.__version__,
        "component_states": component_states,
        "comparison_arm_count": len(matrix),
        "current_runner_arms": performance["arms"],
        "missing_formal_arms": missing_arms,
        "formal_cell_count_if_current_incomplete_suite_were_planned": 6,
        "formal_attempted_evaluations_if_current_incomplete_suite_were_planned": 12000,
        "release_phases": phases,
        "fallback_contract": plan["fallback_and_hard_stop_contract"],
        "formal_reentry_condition_ids": [item["id"] for item in reentry],
        "formal_benchmark_start_allowed": False,
        "formal_benchmark_started": False,
        "simulator_launched": False,
        "todos_may_archive": {
            "082608": False,
            "082609": False,
            "082611": False,
            "082612": False,
        },
    }


if __name__ == "__main__":
    print(json.dumps(validate(), sort_keys=True, allow_nan=False))
