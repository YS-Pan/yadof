"""Assess the frozen hierarchical-CAE development validation without test access."""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import statistics
from typing import Mapping, Sequence


MODEL_SEEDS = (69168527, 154538516, 321217228, 2018013841, 2089865461)
PRIMARY_ARMS = {
    "saw": "hierarchical-cae-mean-groups-none",
    "chrono": "gated-private-residual",
    "test-com": "hierarchical-cae-mean-groups-none",
}
BASELINE_ARM = "conditional-inr-mean"
QUALITY_ARMS = (
    "no-gating",
    "robust-weighting-only",
    "shared-latent-isolation",
    "gated-private-residual",
)


class Gate4AssessmentError(RuntimeError):
    """Raised when frozen evidence cannot be assessed safely."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Gate4AssessmentError(message)


def _load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), f"{path} must contain one JSON object")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _mean(values: Sequence[float]) -> float:
    _require(bool(values), "cannot aggregate an empty metric")
    converted = [float(value) for value in values]
    _require(all(math.isfinite(value) for value in converted), "metric is non-finite")
    return float(statistics.fmean(converted))


def _metric_stats(values: Sequence[float]) -> dict[str, float | int]:
    converted = sorted(float(value) for value in values)
    _require(bool(converted), "cannot summarize an empty metric")
    _require(all(math.isfinite(value) for value in converted), "metric is non-finite")
    return {
        "count": len(converted),
        "min": converted[0],
        "mean": _mean(converted),
        "median": float(statistics.median(converted)),
        "max": converted[-1],
        "population_std": float(statistics.pstdev(converted)),
    }


def _cell_key(cell: Mapping[str, object]) -> tuple[str, int, str, int | None]:
    seed = cell.get("seed")
    return (
        str(cell["case"]),
        int(cell["train_size"]),
        str(cell["arm"]),
        None if seed is None else int(seed),
    )


def _load_cells(
    validation_root: Path,
    *,
    summary: Mapping[str, object],
    plan_sha256: str,
    dataset_manifest_sha256: str,
) -> tuple[dict[tuple[str, int, str, int | None], dict[str, object]], str]:
    cell_paths = sorted((validation_root / "cells").glob("*.json"))
    expected_count = int(summary["completed_cell_count"])
    _require(len(cell_paths) == expected_count, "validation cell count does not match summary")
    cells: dict[tuple[str, int, str, int | None], dict[str, object]] = {}
    digest = hashlib.sha256()
    for path in cell_paths:
        payload_bytes = path.read_bytes()
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(payload_bytes).digest())
        cell = json.loads(payload_bytes)
        _require(isinstance(cell, dict), f"{path.name} must contain one JSON object")
        _require(cell["status"] == "completed", f"{path.name} is not completed")
        _require(cell["offline_test_locator_accessed"] is False, f"{path.name} accessed offline test")
        _require(cell["plan_sha256"] == plan_sha256, f"{path.name} plan hash drifted")
        _require(
            cell["dataset_manifest_sha256"] == dataset_manifest_sha256,
            f"{path.name} dataset hash drifted",
        )
        key = _cell_key(cell)
        _require(key not in cells, f"duplicate validation cell {key!r}")
        cells[key] = cell
    completed_ids = tuple(str(value) for value in summary["completed_cells"])
    _require(
        set(completed_ids) == {str(cell["cell_id"]) for cell in cells.values()},
        "summary completed-cell inventory drifted",
    )
    return cells, digest.hexdigest()


def _raw(cell: Mapping[str, object]) -> Mapping[str, object]:
    return cell["metrics"]["rawdata"]


def _cost(cell: Mapping[str, object]) -> Mapping[str, object]:
    return cell["metrics"]["current_cost"]


def _field_rows(cell: Mapping[str, object]) -> dict[tuple[str, str], Mapping[str, object]]:
    return {
        (str(row["selector"][0]), str(row["selector"][1])): row
        for row in _raw(cell)["fields"]
    }


def _paired_representation(
    cells: Mapping[tuple[str, int, str, int | None], Mapping[str, object]],
    *,
    case: str,
    train_size: int,
    arm: str,
    baseline_arm: str = BASELINE_ARM,
) -> dict[str, object]:
    mae_ratios: list[float] = []
    rmse_ratios: list[float] = []
    cost_ratios: list[float] = []
    pareto_differences: list[float] = []
    worst_field_ratios: list[float] = []
    per_seed: list[dict[str, object]] = []
    for seed in MODEL_SEEDS:
        baseline = cells[(case, train_size, baseline_arm, seed)]
        candidate = cells[(case, train_size, arm, seed)]
        baseline_raw = _raw(baseline)
        candidate_raw = _raw(candidate)
        mae_ratio = float(candidate_raw["field_macro_standardized_mae"]) / float(
            baseline_raw["field_macro_standardized_mae"]
        )
        rmse_ratio = float(candidate_raw["field_macro_standardized_rmse"]) / float(
            baseline_raw["field_macro_standardized_rmse"]
        )
        baseline_cost = _mean(_cost(baseline)["mae_per_objective"])
        candidate_cost = _mean(_cost(candidate)["mae_per_objective"])
        cost_ratio = candidate_cost / baseline_cost
        pareto_difference = float(_cost(candidate)["pareto_pairwise_consistency"]) - float(
            _cost(baseline)["pareto_pairwise_consistency"]
        )
        baseline_fields = _field_rows(baseline)
        candidate_fields = _field_rows(candidate)
        _require(
            set(baseline_fields) == set(candidate_fields),
            f"field inventory drifted in {case}/{train_size}/{seed}",
        )
        per_field = {
            "/".join(selector): float(candidate_fields[selector]["standardized_rmse"])
            / float(baseline_fields[selector]["standardized_rmse"])
            for selector in sorted(baseline_fields)
        }
        worst_selector, worst_ratio = max(per_field.items(), key=lambda item: item[1])
        mae_ratios.append(mae_ratio)
        rmse_ratios.append(rmse_ratio)
        cost_ratios.append(cost_ratio)
        pareto_differences.append(pareto_difference)
        worst_field_ratios.append(worst_ratio)
        per_seed.append(
            {
                "seed": seed,
                "field_macro_standardized_mae_ratio": mae_ratio,
                "field_macro_standardized_rmse_ratio": rmse_ratio,
                "current_cost_macro_mae_ratio": cost_ratio,
                "pareto_pairwise_consistency_difference": pareto_difference,
                "worst_field_standardized_rmse_ratio": worst_ratio,
                "worst_field_selector": worst_selector,
            }
        )
    return {
        "case": case,
        "train_size": train_size,
        "candidate_arm": arm,
        "baseline_arm": baseline_arm,
        "paired_seed_count": len(MODEL_SEEDS),
        "field_macro_standardized_mae_ratio": _metric_stats(mae_ratios),
        "field_macro_standardized_rmse_ratio": _metric_stats(rmse_ratios),
        "current_cost_macro_mae_ratio": _metric_stats(cost_ratios),
        "pareto_pairwise_consistency_difference": _metric_stats(pareto_differences),
        "worst_field_standardized_rmse_ratio": _metric_stats(worst_field_ratios),
        "per_seed": per_seed,
    }


def _quality_summary(
    cells: Mapping[tuple[str, int, str, int | None], Mapping[str, object]],
    *,
    train_size: int,
    arm: str,
) -> dict[str, object]:
    selected = [cells[("chrono", train_size, arm, seed)] for seed in MODEL_SEEDS]
    quality = [cell["metrics"]["quality_regime"] for cell in selected]
    output: dict[str, object] = {
        "train_size": train_size,
        "arm": arm,
        "clean_target_high_frequency_leakage_rate": _metric_stats(
            [metric["clean_target_high_frequency_leakage_rate"] for metric in quality]
        ),
        "strata_field_macro_standardized_mae": {
            stratum: _metric_stats(
                [metric["strata"][stratum]["field_macro_standardized_mae"] for metric in quality]
            )
            for stratum in ("smooth", "chatter", "failure", "boundary")
        },
    }
    classifiers = [metric["regime_classifier"] for metric in quality]
    if arm == "no-gating":
        _require(
            all(metric["auprc"] is None for metric in classifiers),
            "no-gating unexpectedly published an applicability metric",
        )
        output["regime_classifier"] = None
    else:
        output["regime_classifier"] = {
            "auprc": _metric_stats([metric["auprc"] for metric in classifiers]),
            "brier_score": _metric_stats([metric["brier_score"] for metric in classifiers]),
            "expected_calibration_error": _metric_stats(
                [metric["expected_calibration_error"] for metric in classifiers]
            ),
            "calibration_stage": "uncalibrated-validation-diagnostic-only",
        }
    smooth_hf_ratios = [
        float(row["predicted_to_real_median_ratio"])
        for metric in quality
        for row in metric["roughness_inflation"]
        if row["stratum"] == "smooth"
        and row["feature"] == "high_frequency_energy_ratio"
    ]
    output["smooth_high_frequency_roughness_inflation"] = _metric_stats(
        smooth_hf_ratios
    )
    return output


def _resource_summary(
    cells: Mapping[tuple[str, int, str, int | None], Mapping[str, object]]
) -> dict[str, object]:
    candidates = [
        cells[(case, train_size, PRIMARY_ARMS[case], seed)]
        for case in PRIMARY_ARMS
        for train_size in (1000, 2000)
        for seed in MODEL_SEEDS
    ]
    return {
        "cell_wall_sec": _metric_stats([cell["resources"]["wall_sec"] for cell in candidates]),
        "peak_process_rss_bytes": _metric_stats(
            [cell["resources"]["peak_process_rss_bytes"] for cell in candidates]
        ),
        "peak_torch_vram_bytes": _metric_stats(
            [cell["resources"]["peak_torch_vram_bytes"] for cell in candidates]
        ),
        "parameter_count": _metric_stats(
            [cell["resources"]["parameter_count"] for cell in candidates]
        ),
    }


def _apply_thresholds(
    representation: Sequence[Mapping[str, object]],
    quality: Sequence[Mapping[str, object]],
    thresholds: Mapping[str, object],
) -> dict[str, object]:
    representation_results = []
    for row in representation:
        size_key = f"train_{int(row['train_size'])}"
        limits = thresholds["representation_thresholds"][size_key]
        checks = {
            "field_macro_standardized_mae_ratio": float(
                row["field_macro_standardized_mae_ratio"]["mean"]
            )
            <= float(limits["field_macro_standardized_mae_ratio_max_vs_conditional_inr"]),
            "field_macro_standardized_rmse_ratio": float(
                row["field_macro_standardized_rmse_ratio"]["mean"]
            )
            <= float(limits["field_macro_standardized_rmse_ratio_max_vs_conditional_inr"]),
            "current_cost_macro_mae_ratio": float(
                row["current_cost_macro_mae_ratio"]["mean"]
            )
            <= float(limits["current_cost_macro_mae_ratio_max_vs_conditional_inr"]),
            "maximum_single_field_standardized_rmse_degradation_ratio": float(
                row["worst_field_standardized_rmse_ratio"]["max"]
            )
            <= float(limits["maximum_single_field_standardized_rmse_degradation_ratio"]),
        }
        representation_results.append(
            {
                "case": row["case"],
                "train_size": row["train_size"],
                "checks": checks,
                "passed": all(checks.values()),
            }
        )

    quality_by_key = {
        (int(row["train_size"]), str(row["arm"])): row for row in quality
    }
    limits = thresholds["quality_regime_thresholds"]
    quality_results = []
    for train_size in (1000, 2000):
        gated = quality_by_key[(train_size, "gated-private-residual")]
        shared = quality_by_key[(train_size, "shared-latent-isolation")]
        classifier = gated["regime_classifier"]
        shared_leakage = float(shared["clean_target_high_frequency_leakage_rate"]["mean"])
        gated_leakage = float(gated["clean_target_high_frequency_leakage_rate"]["mean"])
        improvement = (shared_leakage - gated_leakage) / shared_leakage
        strata = gated["strata_field_macro_standardized_mae"]
        checks = {
            "clean_target_high_frequency_leakage_rate": gated_leakage
            <= float(limits["clean_target_high_frequency_leakage_rate_max"]),
            "smooth_high_frequency_roughness_inflation": float(
                gated["smooth_high_frequency_roughness_inflation"]["median"]
            )
            <= float(limits["predicted_to_real_roughness_inflation_max"]),
            "regime_classifier_auprc": float(classifier["auprc"]["mean"])
            >= float(limits["regime_classifier_auprc_min"]),
            "regime_probability_expected_calibration_error": float(
                classifier["expected_calibration_error"]["mean"]
            )
            <= float(limits["regime_probability_expected_calibration_error_max"]),
            "regime_probability_brier_score": float(classifier["brier_score"]["mean"])
            <= float(limits["regime_probability_brier_score_max"]),
            "smooth_stratum_field_macro_error": float(strata["smooth"]["mean"])
            <= float(limits["smooth_stratum_field_macro_error_max"]),
            "chatter_stratum_field_macro_error": float(strata["chatter"]["mean"])
            <= float(limits["chatter_stratum_field_macro_error_max"]),
            "failure_stratum_field_macro_error": float(strata["failure"]["mean"])
            <= float(limits["failure_stratum_field_macro_error_max"]),
            "boundary_stratum_field_macro_error": float(strata["boundary"]["mean"])
            <= float(limits["boundary_stratum_field_macro_error_max"]),
            "gated_residual_vs_shared_isolation_improvement": improvement
            >= float(limits["gated_residual_vs_shared_isolation_required_improvement"]),
        }
        quality_results.append(
            {
                "train_size": train_size,
                "gated_vs_shared_leakage_relative_improvement": improvement,
                "checks": checks,
                "passed": all(checks.values()),
            }
        )
    representation_passed = all(row["passed"] for row in representation_results)
    quality_passed = all(row["passed"] for row in quality_results)
    return {
        "representation": representation_results,
        "quality_regime": quality_results,
        "representation_passed": representation_passed,
        "quality_regime_passed": quality_passed,
        "full_grid_gate_passed": representation_passed and quality_passed,
        "coordinate_gate_open": False,
        "offline_test_access_allowed": False,
    }


def assess(
    *,
    validation_root: Path,
    plan_path: Path,
    thresholds_path: Path,
) -> dict[str, object]:
    validation_root = validation_root.resolve()
    plan_path = plan_path.resolve()
    thresholds_path = thresholds_path.resolve()
    summary_path = validation_root / "validation_summary.json"
    run_spec_path = validation_root / "run_spec.json"
    summary = _load_json(summary_path)
    run_spec = _load_json(run_spec_path)
    plan = _load_json(plan_path)
    thresholds = _load_json(thresholds_path)
    plan_sha256 = _sha256(plan_path)
    _require(summary["status"] == "completed-development-validation-only", "validation is incomplete")
    _require(int(summary["completed_cell_count"]) == int(plan["expected_cell_count"]) == 116, "expected 116 cells")
    _require(summary["offline_test_locator_accessed"] is False, "summary reports offline-test access")
    _require(summary["plan_sha256"] == plan_sha256, "summary plan hash drifted")
    _require(summary["metric_implementation_sha256"] == plan["metric_implementation_sha256"], "metric hash drifted")
    dataset_manifest_sha256 = str(summary["dataset_manifest_sha256"])
    _require(
        dataset_manifest_sha256 == str(plan["dataset_manifest_sha256"]),
        "dataset manifest hash drifted",
    )
    _require(run_spec["offline_test_locator_accessed"] is False, "run spec reports offline-test access")
    _require(
        thresholds["evidence"]["dataset_manifest_sha256"] == dataset_manifest_sha256,
        "threshold dataset binding drifted",
    )
    _require(thresholds["evidence"]["validation_plan_sha256"] == plan_sha256, "threshold plan binding drifted")
    _require(
        thresholds["evidence"]["metric_implementation_sha256"]
        == summary["metric_implementation_sha256"],
        "threshold metric binding drifted",
    )
    cells, cells_inventory_sha256 = _load_cells(
        validation_root,
        summary=summary,
        plan_sha256=plan_sha256,
        dataset_manifest_sha256=dataset_manifest_sha256,
    )
    representation = [
        _paired_representation(
            cells,
            case=case,
            train_size=train_size,
            arm=PRIMARY_ARMS[case],
        )
        for case in ("saw", "chrono", "test-com")
        for train_size in (1000, 2000)
    ]
    quality = [
        _quality_summary(cells, train_size=train_size, arm=arm)
        for train_size in (1000, 2000)
        for arm in QUALITY_ARMS
    ]
    group_ablation = [
        _paired_representation(
            cells,
            case="test-com",
            train_size=train_size,
            arm="hierarchical-cae-mean-explicit-s11-gain-groups",
            baseline_arm="hierarchical-cae-mean-groups-none",
        )
        for train_size in (1000, 2000)
    ]
    sharing_ablation = [
        _paired_representation(
            cells,
            case="test-com",
            train_size=train_size,
            arm="hierarchical-cae-mean-groups-none",
            baseline_arm="hierarchical-cae-independent-fields",
        )
        for train_size in (1000, 2000)
    ]
    decision = _apply_thresholds(representation, quality, thresholds)
    return {
        "schema_version": 1,
        "assessment_id": "20260827-hierarchical-cae-gate4-development-validation-decision-v1",
        "status": "completed-full-grid-gate-failed-coordinate-blocked",
        "evidence": {
            "validation_root": validation_root.as_posix(),
            "validation_summary_sha256": _sha256(summary_path),
            "run_spec_sha256": _sha256(run_spec_path),
            "cell_count": len(cells),
            "cells_inventory_sha256": cells_inventory_sha256,
            "dataset_manifest_sha256": dataset_manifest_sha256,
            "validation_plan_sha256": plan_sha256,
            "metric_implementation_sha256": summary["metric_implementation_sha256"],
            "thresholds_sha256": _sha256(thresholds_path),
            "offline_test_locator_accessed": False,
            "simulator_launched_by_validation": False,
        },
        "model_config_sha256_by_arm": {
            arm: _canonical_sha256(cell["model_config"])
            for arm, cell in sorted(
                {
                    str(cell["arm"]): cell for cell in cells.values()
                }.items()
            )
        },
        "representation": representation,
        "quality_regime": quality,
        "explicit_group_ablation": group_ablation,
        "shared_vs_independent_ablation": sharing_ablation,
        "resource_envelope": _resource_summary(cells),
        "decision": decision,
        "handoff": {
            "coordinate_readout": "blocked: full-grid representation and quality/regime gates failed",
            "mixture_of_experts": "evidence-triggered future gate: leakage remains material; not implemented in 082608",
            "offline_test": "not accessed; remains blocked while the 082608 development gate fails",
        },
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validation-root", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--thresholds", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = assess(
            validation_root=args.validation_root,
            plan_path=args.plan,
            thresholds_path=args.thresholds,
        )
    except (
        Gate4AssessmentError,
        KeyError,
        TypeError,
        ValueError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        print(json.dumps({"schema_version": 1, "ok": False, "error": str(exc)}, sort_keys=True))
        return 1
    rendered = json.dumps(result, indent=2 if args.pretty else None, sort_keys=True) + "\n"
    if args.output is not None:
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.write_text(rendered, encoding="utf-8", newline="\n")
        temporary.replace(output)
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
