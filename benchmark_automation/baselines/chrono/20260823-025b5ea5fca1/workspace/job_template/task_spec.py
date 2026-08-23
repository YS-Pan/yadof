"""Task-owned constants and pure geometry for the King Arthur trebuchet."""

from __future__ import annotations

from dataclasses import dataclass
import math
from collections.abc import Mapping, Sequence


MODEL_NAME = "king-arthur-flexible-propped-counterweight-trebuchet"

GRAVITY_MPS2 = 9.80665
AIR_DENSITY_KG_M3 = 1.225
TENNIS_BALL_MASS_KG = 0.057
TENNIS_BALL_RADIUS_M = 0.0335
TENNIS_BALL_DRAG_COEFFICIENT = 0.65
COUNTERWEIGHT_MASS_KG = 20.0
IRON_DENSITY_KG_M3 = 7870.0
COUNTERWEIGHT_BLOCK_SIZE_M = (COUNTERWEIGHT_MASS_KG / IRON_DENSITY_KG_M3) ** (1.0 / 3.0)

# Solid Douglas-fir is a reproducible first-order throwing-arm model.  The
# optimizer changes section dimensions, so its mass and inertia change together.
WOOD_DENSITY_KG_M3 = 530.0
# Conservative green Coast Douglas-fir clear-wood properties from USDA
# FPL-GTR-282 table 5-3a.  The safety-factor cost below accounts for natural
# variability and defects not represented by the rectangular beam recovery.
WOOD_YOUNG_MODULUS_PA = 10.8e9
WOOD_BENDING_STRENGTH_PA = 53.0e6
WOOD_COMPRESSION_PARALLEL_STRENGTH_PA = 26.1e6
WOOD_SHEAR_PARALLEL_STRENGTH_PA = 6.2e6
SLING_LINEAR_DENSITY_KG_M = 0.010
POUCH_MASS_KG = 0.020

FRAME_BEARING_TOP_OFFSET_M = 0.08

SIMULATION_DURATION_S = 6.0
TIME_STEP_S = 0.001
# Optimization rawData uses an event-aligned, fixed phase grid.  A successful
# sample maps physical time [0, release_time] to phase [0, 1].  A non-releasing
# sample maps [0, SIMULATION_DURATION_S] to the same grid and carries an explicit
# released flag.
RELEASE_PHASE_SAMPLE_COUNT = 513
TRAJECTORY_SAMPLE_INTERVAL_S = 0.005
MAIN_BEARING_DAMPING_NMS_RAD = 0.08
HANGER_BEARING_DAMPING_NMS_RAD = 0.05
LAUNCH_RUNWAY_RELEASE_REACTION_N = 0.0

TOTAL_TIME_RAWDATA_NAME = "trebuchet_total_time"
RELEASE_SUMMARY_RAWDATA_NAME = "trebuchet_release_summary"
RELEASE_KINEMATICS_RAWDATA_NAME = "trebuchet_release_kinematics"
STRESS_HISTORY_RAWDATA_NAME = "trebuchet_stress_history"

RELEASE_SUMMARY_NAMES = (
    "loaded_max_height_m",
    "minimum_ball_center_z_m",
    "trigger_time_s",
    "released_flag",
    "release_sling_arm_rotation_deg",
)

RELEASE_SUMMARY_UNITS = (
    "m",
    "m",
    "s",
    "1",
    "deg",
)

RELEASE_KINEMATICS_CHANNEL_NAMES = (
    "ball_x_m",
    "ball_z_m",
    "ball_vx_mps",
    "ball_vz_mps",
)

RELEASE_KINEMATICS_CHANNEL_UNITS = (
    "m",
    "m",
    "m/s",
    "m/s",
)

STRESS_HISTORY_CHANNEL_NAMES = (
    "arm_combined_normal_stress_mpa",
    "hanger_combined_normal_stress_mpa",
    "peak_strength_utilization",
)

STRESS_HISTORY_CHANNEL_UNITS = (
    "MPa",
    "MPa",
    "1",
)

# These physical-time channels are visualization-only.  Optimization rawData
# deliberately excludes them and stores only the release-aligned fields above.
TRAJECTORY_CHANNEL_NAMES = (
    "ball_x_m",
    "ball_z_m",
    "ball_vx_mps",
    "ball_vz_mps",
    "arm_elevation_deg",
    "hanger_elevation_deg",
    "counterweight_center_z_m",
    "arm_locked_flag",
    "sling_attached_flag",
)

TRAJECTORY_CHANNEL_UNITS = (
    "m",
    "m",
    "m/s",
    "m/s",
    "deg",
    "deg",
    "m",
    "1",
    "1",
)

# Released flight is interpreted after simulation from the release endpoint.
# The constants are fixed task physics, not optimization variables.
BALLISTIC_TIME_STEP_S = 0.005
BALLISTIC_MAX_FLIGHT_TIME_S = 30.0


@dataclass(frozen=True)
class ModelSpec:
    pivot_height_m: float
    long_arm_length_m: float
    short_arm_length_m: float
    hanger_length_m: float
    arm_width_m: float
    arm_height_m: float
    hanger_width_m: float
    hanger_height_m: float
    loaded_arm_angle_deg: float
    loaded_hanger_angle_deg: float
    initial_ball_x_offset_m: float
    cw_trigger_drop_angle_deg: float
    release_sling_arm_rotation_deg: float

    @property
    def sling_length_m(self) -> float:
        """Return the taut sling length implied by the grounded ball position."""

        arm_angle = math.radians(self.loaded_arm_angle_deg)
        arm_tip_z = self.pivot_height_m + self.long_arm_length_m * math.sin(arm_angle)
        return math.hypot(
            self.initial_ball_x_offset_m,
            TENNIS_BALL_RADIUS_M - arm_tip_z,
        )

    @property
    def arm_total_length_m(self) -> float:
        return self.long_arm_length_m + self.short_arm_length_m

    @property
    def arm_mass_kg(self) -> float:
        return (
            WOOD_DENSITY_KG_M3
            * self.arm_total_length_m
            * self.arm_width_m
            * self.arm_height_m
        )

    @property
    def hanger_mass_kg(self) -> float:
        return (
            WOOD_DENSITY_KG_M3
            * self.hanger_length_m
            * self.hanger_width_m
            * self.hanger_height_m
        )

    @property
    def sling_pouch_mass_kg(self) -> float:
        return POUCH_MASS_KG + SLING_LINEAR_DENSITY_KG_M * self.sling_length_m

    @property
    def moving_mass_kg(self) -> float:
        """Moving machine mass excluding counterweight and tennis-ball payload."""

        return self.arm_mass_kg + self.hanger_mass_kg + self.sling_pouch_mass_kg


def model_spec(assigned: Mapping[str, object]) -> ModelSpec:
    """Validate the bounded JSON parameter mapping and return typed task inputs."""

    names = tuple(ModelSpec.__dataclass_fields__)
    missing = [name for name in names if name not in assigned]
    extra = sorted(set(assigned).difference(names))
    if missing or extra:
        raise ValueError(f"parameter mismatch: missing={missing}, extra={extra}")
    values: dict[str, float] = {}
    for name in names:
        value = float(assigned[name])
        if not math.isfinite(value):
            raise ValueError(f"{name} must be finite")
        values[name] = value
    spec = ModelSpec(**values)
    positive_names = (
        "pivot_height_m",
        "long_arm_length_m",
        "short_arm_length_m",
        "hanger_length_m",
        "arm_width_m",
        "arm_height_m",
        "hanger_width_m",
        "hanger_height_m",
    )
    if any(getattr(spec, name) <= 0.0 for name in positive_names):
        raise ValueError("all physical dimensions must be positive")
    if abs(spec.initial_ball_x_offset_m) <= 1.0e-12:
        raise ValueError("initial ball x offset must be nonzero")
    if not -180.0 < spec.loaded_arm_angle_deg < 180.0:
        raise ValueError("loaded arm angle must be between -180 and 180 degrees")
    if not -180.0 < spec.loaded_hanger_angle_deg < 180.0:
        raise ValueError("loaded hanger angle must be between -180 and 180 degrees")
    if not 0.0 < spec.cw_trigger_drop_angle_deg < 180.0:
        raise ValueError("counterweight trigger angle must be between 0 and 180 degrees")
    if abs(spec.release_sling_arm_rotation_deg) <= 1.0e-12:
        raise ValueError("sling-to-arm release rotation must be nonzero")
    return spec


def _unit(angle_deg: float) -> tuple[float, float]:
    angle = math.radians(angle_deg)
    return math.cos(angle), math.sin(angle)


def initial_geometry(spec: ModelSpec) -> dict[str, tuple[float, float] | float]:
    """Return side-view centers and the exact cocked-state height metric."""

    arm_x, arm_z = _unit(spec.loaded_arm_angle_deg)
    hanger_x, hanger_z = _unit(spec.loaded_hanger_angle_deg)
    pivot = (0.0, spec.pivot_height_m)
    arm_tip = (
        pivot[0] + spec.long_arm_length_m * arm_x,
        pivot[1] + spec.long_arm_length_m * arm_z,
    )
    hanger_hinge = (
        pivot[0] - spec.short_arm_length_m * arm_x,
        pivot[1] - spec.short_arm_length_m * arm_z,
    )
    counterweight_center = (
        hanger_hinge[0] + spec.hanger_length_m * hanger_x,
        hanger_hinge[1] + spec.hanger_length_m * hanger_z,
    )

    ball_center = (
        arm_tip[0] + spec.initial_ball_x_offset_m,
        TENNIS_BALL_RADIUS_M,
    )

    arm_section_vertical = 0.5 * spec.arm_height_m * abs(arm_x)
    arm_top = max(arm_tip[1], hanger_hinge[1]) + arm_section_vertical
    hanger_section_vertical = 0.5 * spec.hanger_height_m * abs(hanger_x)
    hanger_top = max(hanger_hinge[1], counterweight_center[1]) + hanger_section_vertical
    cw_half_vertical = 0.5 * COUNTERWEIGHT_BLOCK_SIZE_M * (
        abs(hanger_x) + abs(hanger_z)
    )
    counterweight_top = counterweight_center[1] + cw_half_vertical
    frame_top = spec.pivot_height_m + FRAME_BEARING_TOP_OFFSET_M
    ball_top = ball_center[1] + TENNIS_BALL_RADIUS_M
    loaded_max_height = max(
        0.0,
        arm_top,
        hanger_top,
        counterweight_top,
        frame_top,
        ball_top,
    )
    return {
        "pivot": pivot,
        "arm_tip": arm_tip,
        "hanger_hinge": hanger_hinge,
        "counterweight_center": counterweight_center,
        "ball_center": ball_center,
        "loaded_max_height_m": loaded_max_height,
    }


def global_elevation_deg(x: float, z: float) -> float:
    """Return the signed elevation from global +x in the x-z plane."""

    if not math.isfinite(x) or not math.isfinite(z):
        raise ValueError("direction components must be finite")
    return math.degrees(math.atan2(z, x))


def sling_arm_directed_angle_deg(
    *,
    arm_x: float,
    arm_z: float,
    sling_x: float,
    sling_z: float,
) -> float:
    """Directed wrapped angle from the long arm to the sling in the x-z plane."""

    components = (float(arm_x), float(arm_z), float(sling_x), float(sling_z))
    if any(not math.isfinite(value) for value in components):
        raise ValueError("arm and sling components must be finite")
    arm_length = math.hypot(components[0], components[1])
    sling_length = math.hypot(components[2], components[3])
    if arm_length <= 1.0e-12 or sling_length <= 1.0e-12:
        raise ValueError("arm and sling directions must be nonzero")
    dot = components[0] * components[2] + components[1] * components[3]
    cross = components[0] * components[3] - components[1] * components[2]
    return math.degrees(math.atan2(cross, dot))


def unwrap_angle_deg(previous_unwrapped_deg: float, current_wrapped_deg: float) -> float:
    """Continue a wrapped angle without imposing a 180- or 360-degree limit."""

    previous = float(previous_unwrapped_deg)
    current = float(current_wrapped_deg)
    if not math.isfinite(previous) or not math.isfinite(current):
        raise ValueError("angles must be finite")
    delta = (current - previous + 180.0) % 360.0 - 180.0
    return previous + delta


def sling_release_should_trigger(
    *,
    previous_sling_arm_rotation_deg: float,
    current_sling_arm_rotation_deg: float,
    target_sling_arm_rotation_deg: float,
) -> bool:
    """Return whether signed unwrapped rotation crossed the release setting."""

    previous = float(previous_sling_arm_rotation_deg)
    current = float(current_sling_arm_rotation_deg)
    target = float(target_sling_arm_rotation_deg)
    if any(not math.isfinite(value) for value in (previous, current, target)):
        raise ValueError("release rotations must be finite")
    if target > 0.0:
        return previous < target <= current
    if target < 0.0:
        return previous > target >= current
    raise ValueError("target release rotation must be nonzero")


def horizontal_range(
    initial_x_m: float,
    impact_x_m: float,
    *,
    landed: bool,
) -> tuple[float, float]:
    """Return absolute range for scoring and signed displacement for evidence."""

    signed = float(impact_x_m) - float(initial_x_m)
    if not math.isfinite(signed):
        raise ValueError("horizontal positions must be finite")
    return (abs(signed) if landed else 0.0, signed)


@dataclass(frozen=True)
class BallisticFlight:
    """Deterministic post-release flight interpreted from the release state."""

    landed: bool
    flight_time_s: float
    impact_x_m: float
    signed_range_m: float
    range_m: float
    peak_height_m: float
    samples: tuple[tuple[float, float, float, float], ...] = ()


def _ballistic_derivative(
    state: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    _, _, velocity_x, velocity_z = state
    speed = math.hypot(velocity_x, velocity_z)
    area = math.pi * TENNIS_BALL_RADIUS_M**2
    drag_factor = (
        0.5
        * AIR_DENSITY_KG_M3
        * TENNIS_BALL_DRAG_COEFFICIENT
        * area
        / TENNIS_BALL_MASS_KG
    )
    return (
        velocity_x,
        velocity_z,
        -drag_factor * speed * velocity_x,
        -GRAVITY_MPS2 - drag_factor * speed * velocity_z,
    )


def _ballistic_rk4_step(
    state: tuple[float, float, float, float],
    step_s: float,
) -> tuple[float, float, float, float]:
    k1 = _ballistic_derivative(state)
    s2 = tuple(state[index] + 0.5 * step_s * k1[index] for index in range(4))
    k2 = _ballistic_derivative(s2)
    s3 = tuple(state[index] + 0.5 * step_s * k2[index] for index in range(4))
    k3 = _ballistic_derivative(s3)
    s4 = tuple(state[index] + step_s * k3[index] for index in range(4))
    k4 = _ballistic_derivative(s4)
    return tuple(
        state[index]
        + (step_s / 6.0)
        * (k1[index] + 2.0 * k2[index] + 2.0 * k3[index] + k4[index])
        for index in range(4)
    )


def ballistic_flight_from_release(
    *,
    release_x_m: float,
    release_z_m: float,
    release_vx_mps: float,
    release_vz_mps: float,
    sample_times_s: Sequence[float] = (),
) -> BallisticFlight:
    """Integrate fixed tennis-ball flight outside the Chrono evaluation.

    ``sample_times_s`` are nonnegative times relative to release.  They are used
    only by visualization; normal cost calculation requests no samples.  The
    scored range is horizontal displacement from the release point and is
    therefore invariant to mirroring or translating the mechanism in global x.
    """

    state = (
        float(release_x_m),
        float(release_z_m),
        float(release_vx_mps),
        float(release_vz_mps),
    )
    if any(not math.isfinite(value) for value in state):
        raise ValueError("release state must be finite")
    if state[1] < TENNIS_BALL_RADIUS_M - 1.0e-9:
        raise ValueError("release position is below the ground plane")

    targets = tuple(float(value) for value in sample_times_s)
    if any(not math.isfinite(value) or value < 0.0 for value in targets):
        raise ValueError("ballistic sample times must be finite and nonnegative")
    if any(right < left for left, right in zip(targets, targets[1:])):
        raise ValueError("ballistic sample times must be nondecreasing")

    initial_x = state[0]
    peak_height = state[1]
    time_s = 0.0
    landed = state[1] <= TENNIS_BALL_RADIUS_M and state[3] <= 0.0
    impact_x = state[0]
    flight_time = 0.0
    samples: list[tuple[float, float, float, float]] = []

    def advance_to(target_s: float) -> None:
        nonlocal state, peak_height, time_s, landed, impact_x, flight_time
        while (
            not landed
            and time_s < target_s - 1.0e-12
            and time_s < BALLISTIC_MAX_FLIGHT_TIME_S - 1.0e-12
        ):
            step_s = min(
                BALLISTIC_TIME_STEP_S,
                target_s - time_s,
                BALLISTIC_MAX_FLIGHT_TIME_S - time_s,
            )
            previous = state
            previous_time = time_s
            candidate = _ballistic_rk4_step(state, step_s)
            time_s += step_s
            peak_height = max(peak_height, candidate[1])
            if candidate[1] <= TENNIS_BALL_RADIUS_M and candidate[3] < 0.0:
                denominator = previous[1] - candidate[1]
                fraction = (
                    1.0
                    if abs(denominator) <= 1.0e-15
                    else max(
                        0.0,
                        min(
                            1.0,
                            (previous[1] - TENNIS_BALL_RADIUS_M) / denominator,
                        ),
                    )
                )
                state = tuple(
                    previous[index]
                    + fraction * (candidate[index] - previous[index])
                    for index in range(4)
                )
                state = (state[0], TENNIS_BALL_RADIUS_M, 0.0, 0.0)
                flight_time = previous_time + fraction * step_s
                impact_x = state[0]
                landed = True
                time_s = flight_time
            else:
                state = candidate

    for target in targets:
        advance_to(min(target, BALLISTIC_MAX_FLIGHT_TIME_S))
        samples.append(state)

    if not landed:
        advance_to(BALLISTIC_MAX_FLIGHT_TIME_S)

    signed_range = impact_x - initial_x
    return BallisticFlight(
        landed=landed,
        flight_time_s=float(flight_time if landed else BALLISTIC_MAX_FLIGHT_TIME_S),
        impact_x_m=float(impact_x),
        signed_range_m=float(signed_range),
        range_m=float(abs(signed_range) if landed else 0.0),
        peak_height_m=float(peak_height),
        samples=tuple(samples),
    )


def box_inertia(mass: float, length_x: float, width_y: float, height_z: float) -> tuple[float, float, float]:
    """Principal inertia of a centered rectangular solid."""

    return (
        mass * (width_y**2 + height_z**2) / 12.0,
        mass * (length_x**2 + height_z**2) / 12.0,
        mass * (length_x**2 + width_y**2) / 12.0,
    )


def hanger_composite(spec: ModelSpec) -> dict[str, float | tuple[float, float, float]]:
    """Mass properties for the rigid hanger plus its fixed 20 kg counterweight."""

    hanger_mass = spec.hanger_mass_kg
    total_mass = hanger_mass + COUNTERWEIGHT_MASS_KG
    rod_center_from_hinge = 0.5 * spec.hanger_length_m
    cw_center_from_hinge = spec.hanger_length_m
    com_from_hinge = (
        hanger_mass * rod_center_from_hinge
        + COUNTERWEIGHT_MASS_KG * cw_center_from_hinge
    ) / total_mass
    rod_inertia = box_inertia(
        hanger_mass,
        spec.hanger_length_m,
        spec.hanger_width_m,
        spec.hanger_height_m,
    )
    cw_inertia = box_inertia(
        COUNTERWEIGHT_MASS_KG,
        COUNTERWEIGHT_BLOCK_SIZE_M,
        COUNTERWEIGHT_BLOCK_SIZE_M,
        COUNTERWEIGHT_BLOCK_SIZE_M,
    )
    rod_shift = rod_center_from_hinge - com_from_hinge
    cw_shift = cw_center_from_hinge - com_from_hinge
    inertia = (
        rod_inertia[0] + cw_inertia[0],
        rod_inertia[1]
        + hanger_mass * rod_shift**2
        + cw_inertia[1]
        + COUNTERWEIGHT_MASS_KG * cw_shift**2,
        rod_inertia[2]
        + hanger_mass * rod_shift**2
        + cw_inertia[2]
        + COUNTERWEIGHT_MASS_KG * cw_shift**2,
    )
    return {
        "mass_kg": total_mass,
        "com_from_hinge_m": com_from_hinge,
        "counterweight_center_from_com_m": cw_center_from_hinge - com_from_hinge,
        "inertia_kg_m2": inertia,
    }


def structural_strength_state(
    spec: ModelSpec,
    *,
    pivot_reaction_n: float,
    hanger_reaction_n: float,
    sling_tension_n: float,
) -> dict[str, float]:
    """Recover a conservative rectangular-beam strength state from Chrono loads.

    Chrono's rigid bodies do not contain an internal stress field.  The reaction
    magnitudes come from its solved constraints at the current dynamic step.  For
    damage screening, every magnitude is conservatively treated as both axial and
    transverse: end loads generate in-plane bending, rectangular-beam shear is
    1.5 V/A, and the hanger also receives a pinned-column buckling check.
    """

    loads = {
        "pivot_reaction_n": float(pivot_reaction_n),
        "hanger_reaction_n": float(hanger_reaction_n),
        "sling_tension_n": float(sling_tension_n),
    }
    if any(not math.isfinite(value) or value < 0.0 for value in loads.values()):
        raise ValueError("structural reaction loads must be finite and nonnegative")

    arm_area = spec.arm_width_m * spec.arm_height_m
    arm_section_modulus = spec.arm_width_m * spec.arm_height_m**2 / 6.0
    arm_end_moment = (
        loads["hanger_reaction_n"] * spec.short_arm_length_m
        + loads["sling_tension_n"] * spec.long_arm_length_m
    )
    arm_force = max(loads.values())
    arm_bending_stress = arm_end_moment / arm_section_modulus
    arm_axial_stress = arm_force / arm_area
    arm_shear_stress = 1.5 * arm_force / arm_area
    arm_normal_utilization = (
        arm_bending_stress / WOOD_BENDING_STRENGTH_PA
        + arm_axial_stress / WOOD_COMPRESSION_PARALLEL_STRENGTH_PA
    )
    arm_utilization = max(
        arm_normal_utilization,
        arm_shear_stress / WOOD_SHEAR_PARALLEL_STRENGTH_PA,
    )

    hanger_area = spec.hanger_width_m * spec.hanger_height_m
    hanger_section_modulus = (
        spec.hanger_width_m * spec.hanger_height_m**2 / 6.0
    )
    hanger_force = loads["hanger_reaction_n"]
    hanger_bending_stress = (
        hanger_force * spec.hanger_length_m / hanger_section_modulus
    )
    hanger_axial_stress = hanger_force / hanger_area
    hanger_shear_stress = 1.5 * hanger_force / hanger_area
    hanger_normal_utilization = (
        hanger_bending_stress / WOOD_BENDING_STRENGTH_PA
        + hanger_axial_stress / WOOD_COMPRESSION_PARALLEL_STRENGTH_PA
    )
    weak_axis_inertia = min(
        spec.hanger_width_m * spec.hanger_height_m**3 / 12.0,
        spec.hanger_height_m * spec.hanger_width_m**3 / 12.0,
    )
    buckling_capacity = (
        math.pi**2
        * WOOD_YOUNG_MODULUS_PA
        * weak_axis_inertia
        / spec.hanger_length_m**2
    )
    hanger_utilization = max(
        hanger_normal_utilization,
        hanger_shear_stress / WOOD_SHEAR_PARALLEL_STRENGTH_PA,
        hanger_force / buckling_capacity,
    )

    peak_utilization = max(arm_utilization, hanger_utilization)
    safety_factor = 1.0e9 if peak_utilization <= 1.0e-12 else 1.0 / peak_utilization
    return {
        "arm_combined_normal_stress_mpa": (
            arm_bending_stress + arm_axial_stress
        )
        / 1.0e6,
        "hanger_combined_normal_stress_mpa": (
            hanger_bending_stress + hanger_axial_stress
        )
        / 1.0e6,
        "arm_strength_utilization": arm_utilization,
        "hanger_strength_utilization": hanger_utilization,
        "peak_strength_utilization": peak_utilization,
        "strength_safety_factor": safety_factor,
        "structural_failure_flag": 1.0 if peak_utilization >= 1.0 else 0.0,
    }


def trajectory_time_axis() -> tuple[float, ...]:
    count = int(round(SIMULATION_DURATION_S / TRAJECTORY_SAMPLE_INTERVAL_S)) + 1
    return tuple(index * TRAJECTORY_SAMPLE_INTERVAL_S for index in range(count))


def release_phase_axis() -> tuple[float, ...]:
    """Return the task's immutable normalized pre-release coordinate grid."""

    return tuple(
        index / (RELEASE_PHASE_SAMPLE_COUNT - 1)
        for index in range(RELEASE_PHASE_SAMPLE_COUNT)
    )


def launch_runway_should_release(
    *,
    arm_locked: bool,
    sling_attached: bool,
    support_reaction_n: float,
) -> bool:
    """Return whether the horizontal launch runway should stop supporting the ball.

    The prismatic link's positive local-X reaction is the upward normal force on
    the ball for ``Q_ROTATE_Z_TO_X``.  A non-positive value means a bilateral rail
    would have to pull the ball downward, so the equivalent unilateral support has
    lost contact and must be disabled.
    """

    reaction = float(support_reaction_n)
    if not math.isfinite(reaction):
        raise ValueError("launch-runway support reaction must be finite")
    return (
        not arm_locked
        and sling_attached
        and reaction <= LAUNCH_RUNWAY_RELEASE_REACTION_N
    )


def launch_runway_should_reattach(
    *,
    runway_attached: bool,
    sling_attached: bool,
    ball_center_z_m: float,
    ball_vertical_velocity_mps: float,
) -> bool:
    """Restore exact ground support if a still-slung ball returns to the runway."""

    z = float(ball_center_z_m)
    vz = float(ball_vertical_velocity_mps)
    if not math.isfinite(z) or not math.isfinite(vz):
        raise ValueError("launch-runway ball state must be finite")
    return (
        not runway_attached
        and sling_attached
        and z <= TENNIS_BALL_RADIUS_M
        and vz < 0.0
    )
