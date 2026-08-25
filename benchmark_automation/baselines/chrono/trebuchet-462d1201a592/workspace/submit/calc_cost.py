"""Interpret release-aligned rawData into four normalized objectives."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math

import numpy as np

from task_spec import (
    ModelSpec,
    RELEASE_KINEMATICS_RAWDATA_FIELDS,
    RELEASE_PHASE_SAMPLE_COUNT,
    RELEASE_SUMMARY_RAWDATA_FIELDS,
    STRESS_HISTORY_RAWDATA_FIELDS,
    TOTAL_TIME_RAWDATA_FIELD,
    ballistic_flight_from_release,
    global_elevation_deg,
    model_spec,
)
from yadof.job_template.cost_misc import (
    RawVariables,
    calculate_rawdata_cost,
    soft_cost,
)
from yadof.job_template.rawdata_contract import (
    RawDataItem,
    RawDataView,
    load_rawdata_views,
)


OBJECTIVE_NAMES = (
    "cost_range",
    "cost_moving_mass_limit",
    "cost_loaded_height_limit",
    "cost_material_strength_limit",
)
ERROR_COST = 1.0
SOFT_COST_EDGE = 0.1

# Fixed physical anchors. Goal/worst map to 0.1/0.9 under soft_cost; values
# outside the anchors retain ordering in the algebraic-sigmoid tails.
RANGE_GOAL_M = 100.0
RANGE_WORST_M = 5.0
MOVING_MASS_GOAL_KG = 4.5
MOVING_MASS_WORST_KG = 50.0
LOADED_HEIGHT_GOAL_M = 2.35
LOADED_HEIGHT_WORST_M = 5.00
STRENGTH_UTILIZATION_GOAL = 0.50
STRENGTH_UTILIZATION_WORST = 1.00

TOTAL_TIME_SHAPE = ()
RELEASE_CURVE_SHAPE = (RELEASE_PHASE_SAMPLE_COUNT,)
SUMMARY_RAWDATA_NAMES = {
    quantity_name: rawdata_name
    for rawdata_name, quantity_name, _unit in RELEASE_SUMMARY_RAWDATA_FIELDS
}
KINEMATICS_RAWDATA_NAMES = {
    quantity_name: rawdata_name
    for rawdata_name, quantity_name, _unit in RELEASE_KINEMATICS_RAWDATA_FIELDS
}
STRESS_RAWDATA_NAMES = {
    quantity_name: rawdata_name
    for rawdata_name, quantity_name, _unit in STRESS_HISTORY_RAWDATA_FIELDS
}
TOTAL_TIME_RAWDATA_NAME = TOTAL_TIME_RAWDATA_FIELD[0]
MINIMUM_VALID_BALL_CENTER_Z_M = 0.0325
MINIMUM_VALID_MOVING_GROUND_CLEARANCE_M = -0.005


def _finite_array(
    views: dict[str, RawDataView],
    name: str,
    shape: tuple[int, ...],
) -> np.ndarray:
    values = np.asarray(views[name].data, dtype=np.float64)
    if values.shape != shape or not np.all(np.isfinite(values)):
        raise ValueError(f"{name} must be a finite {shape} array")
    return values


def _assigned_values(raw_variables: RawVariables | None) -> dict[str, float]:
    """Return the exact task inputs used by real and surrogate cost paths."""

    if raw_variables is None:
        raise ValueError("moving-mass cost requires assigned raw_variables")
    parameter_names = tuple(ModelSpec.__dataclass_fields__)
    if isinstance(raw_variables, Mapping):
        assigned = {
            str(name): float(value) for name, value in raw_variables.items()
        }
    else:
        values = tuple(float(value) for value in raw_variables)
        if len(values) != len(parameter_names):
            raise ValueError(
                f"expected {len(parameter_names)} raw variables, got {len(values)}"
            )
        assigned = dict(zip(parameter_names, values, strict=True))
    return assigned


def moving_mass_from_variables(raw_variables: RawVariables | None) -> float:
    """Compute moving mass analytically instead of predicting it as rawData."""

    return float(model_spec(_assigned_values(raw_variables)).moving_mass_kg)


def _physical_metrics_from_loaded(
    loaded_items: Sequence[RawDataView],
    raw_variables: RawVariables | None,
) -> dict[str, float | bool]:
    views = {view.name: view for view in loaded_items}
    total_time = float(
        _finite_array(views, TOTAL_TIME_RAWDATA_NAME, TOTAL_TIME_SHAPE)
    )

    def summary_value(quantity_name: str) -> float:
        return float(
            _finite_array(
                views,
                SUMMARY_RAWDATA_NAMES[quantity_name],
                (),
            )
        )

    def release_curve(quantity_name: str) -> np.ndarray:
        return _finite_array(
            views,
            KINEMATICS_RAWDATA_NAMES[quantity_name],
            RELEASE_CURVE_SHAPE,
        )

    release_x = float(release_curve("ball_x_m")[-1])
    release_z = float(release_curve("ball_z_m")[-1])
    release_vx = float(release_curve("ball_vx_mps")[-1])
    release_vz = float(release_curve("ball_vz_mps")[-1])
    loaded_max_height = summary_value("loaded_max_height_m")
    minimum_ball_center_z = summary_value("minimum_ball_center_z_m")
    trigger_time = summary_value("trigger_time_s")
    released = bool(summary_value("released_flag") >= 0.5)
    release_sling_arm_rotation = summary_value(
        "release_sling_arm_rotation_deg"
    )
    minimum_arm_ground_clearance = summary_value(
        "minimum_arm_ground_clearance_m"
    )
    minimum_hanger_ground_clearance = summary_value(
        "minimum_hanger_ground_clearance_m"
    )
    minimum_counterweight_ground_clearance = summary_value(
        "minimum_counterweight_ground_clearance_m"
    )
    mechanism_ground_valid = bool(
        min(
            minimum_arm_ground_clearance,
            minimum_hanger_ground_clearance,
            minimum_counterweight_ground_clearance,
        )
        >= MINIMUM_VALID_MOVING_GROUND_CLEARANCE_M
    )
    ground_valid = bool(
        minimum_ball_center_z >= MINIMUM_VALID_BALL_CENTER_Z_M
        and mechanism_ground_valid
    )
    time_valid = bool(math.isfinite(total_time) and total_time > 0.0)

    landed = False
    range_m = 0.0
    signed_range_m = 0.0
    flight_time_s = 0.0
    peak_height_m = release_z
    if released and ground_valid and time_valid:
        try:
            flight = ballistic_flight_from_release(
                release_x_m=release_x,
                release_z_m=release_z,
                release_vx_mps=release_vx,
                release_vz_mps=release_vz,
            )
        except ValueError:
            flight = None
        if flight is not None:
            landed = bool(flight.landed)
            range_m = float(flight.range_m)
            signed_range_m = float(flight.signed_range_m)
            flight_time_s = float(flight.flight_time_s)
            peak_height_m = float(flight.peak_height_m)

    peak_strength_utilization = float(
        np.max(
            _finite_array(
                views,
                STRESS_RAWDATA_NAMES["peak_strength_utilization"],
                RELEASE_CURVE_SHAPE,
            )
        )
    )
    release_speed = math.hypot(release_vx, release_vz)
    release_angle = (
        global_elevation_deg(release_vx, release_vz)
        if release_speed > 1.0e-12
        else 0.0
    )
    return {
        "total_time_s": total_time,
        "released": released,
        "ground_valid": ground_valid,
        "mechanism_ground_valid": mechanism_ground_valid,
        "landed": landed,
        "range_m": range_m,
        "signed_range_m": signed_range_m,
        "flight_time_s": flight_time_s,
        "peak_height_m": peak_height_m,
        "release_x_m": release_x,
        "release_z_m": release_z,
        "release_vx_mps": release_vx,
        "release_vz_mps": release_vz,
        "release_speed_mps": release_speed,
        "release_velocity_angle_deg": release_angle,
        "moving_mass_kg": moving_mass_from_variables(raw_variables),
        "loaded_max_height_m": loaded_max_height,
        "minimum_ball_center_z_m": minimum_ball_center_z,
        "minimum_arm_ground_clearance_m": minimum_arm_ground_clearance,
        "minimum_hanger_ground_clearance_m": minimum_hanger_ground_clearance,
        "minimum_counterweight_ground_clearance_m": (
            minimum_counterweight_ground_clearance
        ),
        "trigger_time_s": trigger_time,
        "release_sling_arm_rotation_deg": release_sling_arm_rotation,
        "peak_strength_utilization": peak_strength_utilization,
    }


def extract_physical_metrics(
    sample_rawdata: Sequence[RawDataItem],
    raw_variables: RawVariables,
) -> dict[str, float | bool]:
    """Expose the same task interpretation to validation/visualization tools."""

    return _physical_metrics_from_loaded(
        load_rawdata_views(sample_rawdata),
        raw_variables,
    )


def _calculate_loaded_cost(
    loaded_items: Sequence[RawDataView],
    raw_variables: RawVariables | None,
) -> tuple[float, ...]:
    metrics = _physical_metrics_from_loaded(loaded_items, raw_variables)
    if not bool(metrics["mechanism_ground_valid"]):
        return (ERROR_COST,) * len(OBJECTIVE_NAMES)
    valid_range = bool(
        metrics["released"]
        and metrics["ground_valid"]
        and metrics["landed"]
    )
    peak_utilization = float(metrics["peak_strength_utilization"])
    return (
        soft_cost(
            float(metrics["range_m"]),
            goal=RANGE_GOAL_M,
            worst=RANGE_WORST_M,
            error_cost=ERROR_COST,
            edge_cost=SOFT_COST_EDGE,
        )
        if valid_range
        else ERROR_COST,
        soft_cost(
            float(metrics["moving_mass_kg"]),
            goal=MOVING_MASS_GOAL_KG,
            worst=MOVING_MASS_WORST_KG,
            error_cost=ERROR_COST,
            edge_cost=SOFT_COST_EDGE,
        ),
        soft_cost(
            float(metrics["loaded_max_height_m"]),
            goal=LOADED_HEIGHT_GOAL_M,
            worst=LOADED_HEIGHT_WORST_M,
            error_cost=ERROR_COST,
            edge_cost=SOFT_COST_EDGE,
        ),
        soft_cost(
            peak_utilization,
            goal=STRENGTH_UTILIZATION_GOAL,
            worst=STRENGTH_UTILIZATION_WORST,
            error_cost=ERROR_COST,
            edge_cost=SOFT_COST_EDGE,
        )
        if peak_utilization >= 0.0
        else ERROR_COST,
    )


def calculate_cost(
    sample_rawdata: Sequence[RawDataItem],
    raw_variables: RawVariables | None = None,
) -> tuple[float, ...]:
    return calculate_rawdata_cost(
        sample_rawdata,
        raw_variables,
        objective_names=OBJECTIVE_NAMES,
        calculate_loaded_cost=_calculate_loaded_cost,
        error_cost=ERROR_COST,
    )


def get_objective_names() -> tuple[str, ...]:
    return OBJECTIVE_NAMES
