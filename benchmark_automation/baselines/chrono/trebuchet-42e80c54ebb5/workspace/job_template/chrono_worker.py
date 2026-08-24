"""Isolated Project Chrono mechanics for the King Arthur trebuchet task."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from collections.abc import Mapping

import numpy as np

from chrono_com import worker_main
from task_spec import (
    COUNTERWEIGHT_BLOCK_SIZE_M,
    GRAVITY_MPS2,
    HANGER_BEARING_DAMPING_NMS_RAD,
    MAIN_BEARING_DAMPING_NMS_RAD,
    MODEL_NAME,
    RELEASE_KINEMATICS_CHANNEL_NAMES,
    RELEASE_KINEMATICS_RAWDATA_FIELDS,
    RELEASE_PHASE_SAMPLE_COUNT,
    RELEASE_SUMMARY_NAMES,
    RELEASE_SUMMARY_RAWDATA_FIELDS,
    SIMULATION_DURATION_S,
    STRESS_HISTORY_CHANNEL_NAMES,
    STRESS_HISTORY_RAWDATA_FIELDS,
    TENNIS_BALL_MASS_KG,
    TENNIS_BALL_RADIUS_M,
    TIME_STEP_S,
    TOTAL_TIME_RAWDATA_FIELD,
    TRAJECTORY_CHANNEL_NAMES,
    TRAJECTORY_CHANNEL_UNITS,
    ballistic_flight_from_release,
    box_inertia,
    hanger_composite,
    initial_geometry,
    launch_runway_should_reattach,
    launch_runway_should_release,
    model_spec,
    release_phase_axis,
    sling_arm_directed_angle_deg,
    sling_release_should_trigger,
    structural_strength_state,
    trajectory_time_axis,
    unwrap_angle_deg,
)


GROUND_COLLISION_FAMILY = 0
MOVING_COLLISION_FAMILY = 1


def _vector(chrono, x: float, z: float, y: float = 0.0):
    return chrono.ChVector3d(float(x), float(y), float(z))


def _xz(point) -> tuple[float, float]:
    return float(point.x), float(point.z)


def _length_xz(vector) -> float:
    return math.hypot(float(vector.x), float(vector.z))


def _elevation_deg(vector) -> float:
    return math.degrees(math.atan2(float(vector.z), float(vector.x)))


def _unit_xz(vector) -> tuple[float, float]:
    length = _length_xz(vector)
    if length <= 1e-12:
        raise RuntimeError("zero-length model direction")
    return float(vector.x) / length, float(vector.z) / length


def _drop_angle_deg(initial: tuple[float, float], current: tuple[float, float]) -> float:
    cosine = max(-1.0, min(1.0, initial[0] * current[0] + initial[1] * current[1]))
    return math.degrees(math.acos(cosine))


def _save_npz(rawdata_dir: Path, filename: str, **payload: object) -> None:
    target = rawdata_dir / filename
    partial = target.with_name(target.name + ".part")
    with partial.open("wb") as stream:
        np.savez_compressed(stream, **payload)
    os.replace(partial, target)


def _reaction_magnitude(link) -> float:
    try:
        return float(link.GetReaction2().force.Length())
    except Exception:
        return 0.0


def _set_ball_mass(chrono, ball, mass_kg: float) -> None:
    ball.SetMass(float(mass_kg))
    inertia = 0.4 * float(mass_kg) * TENNIS_BALL_RADIUS_M**2
    ball.SetInertiaXX(chrono.ChVector3d(inertia, inertia, inertia))


def _enable_ground_contact_only(body) -> None:
    """Enable body/ground contact while suppressing mechanism self-contact."""

    collision_model = body.GetCollisionModel()
    collision_model.SetFamily(MOVING_COLLISION_FAMILY)
    collision_model.AllowCollisionsWith(GROUND_COLLISION_FAMILY)
    collision_model.DisallowCollisionsWith(MOVING_COLLISION_FAMILY)
    body.EnableCollision(True)


def _resample_phase_history(
    times_s: np.ndarray,
    values: np.ndarray,
    *,
    total_time_s: float,
    preserve_channel_maxima: bool = False,
) -> np.ndarray:
    """Project one variable-duration history onto the immutable phase grid."""

    times = np.asarray(times_s, dtype=np.float64).reshape(-1)
    matrix = np.asarray(values, dtype=np.float64)
    duration = float(total_time_s)
    if matrix.ndim != 2 or matrix.shape[0] != times.size:
        raise RuntimeError("history times and values have incompatible shapes")
    if times.size == 0 or not np.all(np.isfinite(times)):
        raise RuntimeError("history times must be nonempty and finite")
    if not np.all(np.isfinite(matrix)):
        raise RuntimeError("history values must be finite")
    if duration <= 0.0 or not math.isfinite(duration):
        raise RuntimeError("normalized history duration must be finite and positive")
    if np.any(np.diff(times) < 0.0):
        raise RuntimeError("history times must be nondecreasing")

    phase = np.asarray(release_phase_axis(), dtype=np.float64)
    if phase.shape != (RELEASE_PHASE_SAMPLE_COUNT,):
        raise RuntimeError("release phase axis has an unexpected shape")
    targets = phase * duration
    result = np.empty((phase.size, matrix.shape[1]), dtype=np.float64)
    for channel in range(matrix.shape[1]):
        result[:, channel] = np.interp(targets, times, matrix[:, channel])
        if preserve_channel_maxima:
            peak_source = int(np.argmax(matrix[:, channel]))
            peak_phase = min(1.0, max(0.0, float(times[peak_source]) / duration))
            peak_target = int(round(peak_phase * (phase.size - 1)))
            result[peak_target, channel] = max(
                result[peak_target, channel],
                float(matrix[peak_source, channel]),
            )
    return result


def run_task_model(
    chrono,
    assigned: Mapping[str, object],
    *,
    continue_mechanism_after_release: bool = False,
) -> dict[str, object]:
    """Build and integrate one fully assigned King Arthur trebuchet.

    Normal optimization evaluation stops Chrono at sling release.  It returns
    fixed-phase pre-release kinematics and stress histories plus a scalar total
    time.  Post-release ball flight belongs to the cost interpreter.  Animation
    export may explicitly continue the mechanism and request a physical-time
    replay without changing optimization rawData.
    """

    spec = model_spec(assigned)
    geometry = initial_geometry(spec)
    loaded_clearances = {
        "arm": float(geometry["loaded_arm_ground_clearance_m"]),
        "hanger": float(geometry["loaded_hanger_ground_clearance_m"]),
        "counterweight": float(
            geometry["loaded_counterweight_ground_clearance_m"]
        ),
    }
    if min(loaded_clearances.values()) < -1.0e-9:
        details = ", ".join(
            f"{name}={clearance:.6g} m"
            for name, clearance in loaded_clearances.items()
        )
        raise ValueError(
            "loaded mechanism intersects the ground before contact integration: "
            + details
        )
    composite = hanger_composite(spec)
    progress_enabled = os.environ.get("YADOF_CHRONO_PROGRESS", "").strip() == "1"

    # Rigid NSC contact is deliberate here: the mechanism/ground boundary is a
    # non-penetration constraint, not a compliant material model.  The former SMC
    # setup allowed fast constrained members to travel visibly below the plane.
    system = chrono.ChSystemNSC()
    system.SetCollisionSystemType(chrono.ChCollisionSystem.Type_BULLET)
    system.SetGravitationalAcceleration(chrono.ChVector3d(0.0, 0.0, -GRAVITY_MPS2))

    ground_material = chrono.ChContactMaterialNSC()
    ground_material.SetFriction(0.60)
    ground_material.SetRestitution(0.05)

    ball_material = chrono.ChContactMaterialNSC()
    ball_material.SetFriction(0.45)
    ball_material.SetRestitution(0.72)

    ground = chrono.ChBodyEasyBox(
        2000.0,
        2.0,
        0.20,
        1000.0,
        False,
        True,
        ground_material,
    )
    ground.SetPos(chrono.ChVector3d(0.0, 0.0, -0.10))
    ground.SetFixed(True)
    ground.GetCollisionModel().SetFamily(GROUND_COLLISION_FAMILY)
    ground.GetCollisionModel().AllowCollisionsWith(MOVING_COLLISION_FAMILY)
    system.AddBody(ground)

    arm_angle = math.radians(spec.loaded_arm_angle_deg)
    arm_rotation = chrono.QuatFromAngleY(-arm_angle)
    arm_length = spec.arm_total_length_m
    arm_mass = spec.arm_mass_kg
    arm = chrono.ChBody()
    arm.SetMass(arm_mass)
    arm_inertia = box_inertia(
        arm_mass,
        arm_length,
        spec.arm_width_m,
        spec.arm_height_m,
    )
    arm.SetInertiaXX(chrono.ChVector3d(*arm_inertia))
    arm_com_from_pivot = 0.5 * (spec.long_arm_length_m - spec.short_arm_length_m)
    pivot_x, pivot_z = geometry["pivot"]
    arm_unit_x = math.cos(arm_angle)
    arm_unit_z = math.sin(arm_angle)
    arm.SetPos(
        _vector(
            chrono,
            pivot_x + arm_com_from_pivot * arm_unit_x,
            pivot_z + arm_com_from_pivot * arm_unit_z,
        )
    )
    arm.SetRot(arm_rotation)
    arm.AddCollisionShape(
        chrono.ChCollisionShapeBox(
            ground_material,
            arm_length,
            spec.arm_width_m,
            spec.arm_height_m,
        )
    )
    _enable_ground_contact_only(arm)
    arm.SetFixed(True)
    system.AddBody(arm)

    hanger_angle = math.radians(spec.loaded_hanger_angle_deg)
    hanger_rotation = chrono.QuatFromAngleY(-hanger_angle)
    hanger_mass_total = float(composite["mass_kg"])
    hanger_com_from_hinge = float(composite["com_from_hinge_m"])
    cw_center_from_com = float(composite["counterweight_center_from_com_m"])
    hanger_inertia = composite["inertia_kg_m2"]
    hinge_x, hinge_z = geometry["hanger_hinge"]
    hanger = chrono.ChBody()
    hanger.SetMass(hanger_mass_total)
    hanger.SetInertiaXX(chrono.ChVector3d(*hanger_inertia))
    hanger.SetPos(
        _vector(
            chrono,
            hinge_x + hanger_com_from_hinge * math.cos(hanger_angle),
            hinge_z + hanger_com_from_hinge * math.sin(hanger_angle),
        )
    )
    hanger.SetRot(hanger_rotation)
    rod_center_from_com = 0.5 * spec.hanger_length_m - hanger_com_from_hinge
    hanger.AddCollisionShape(
        chrono.ChCollisionShapeBox(
            ground_material,
            spec.hanger_length_m,
            spec.hanger_width_m,
            spec.hanger_height_m,
        ),
        chrono.ChFramed(chrono.ChVector3d(rod_center_from_com, 0.0, 0.0)),
    )
    counterweight_shape = chrono.ChCollisionShapeBox(
        ground_material,
        COUNTERWEIGHT_BLOCK_SIZE_M,
        COUNTERWEIGHT_BLOCK_SIZE_M,
        COUNTERWEIGHT_BLOCK_SIZE_M,
    )
    hanger.AddCollisionShape(
        counterweight_shape,
        chrono.ChFramed(chrono.ChVector3d(cw_center_from_com, 0.0, 0.0)),
    )
    _enable_ground_contact_only(hanger)
    system.AddBody(hanger)

    joint_rotation = chrono.QuatFromAngleX(-0.5 * math.pi)
    hanger_joint_frame = chrono.ChFramed(_vector(chrono, hinge_x, hinge_z), joint_rotation)
    hanger_joint = chrono.ChLinkLockRevolute()
    hanger_joint.Initialize(hanger, arm, hanger_joint_frame)
    system.AddLink(hanger_joint)
    hanger_damper = chrono.ChLinkRSDA()
    hanger_damper.Initialize(hanger, arm, hanger_joint_frame)
    hanger_damper.SetDampingCoefficient(HANGER_BEARING_DAMPING_NMS_RAD)
    system.AddLink(hanger_damper)

    ball_x, ball_z = geometry["ball_center"]
    ball = chrono.ChBodyEasySphere(
        TENNIS_BALL_RADIUS_M,
        1.0,
        False,
        True,
        ball_material,
    )
    effective_launch_mass = TENNIS_BALL_MASS_KG + spec.sling_pouch_mass_kg
    _set_ball_mass(chrono, ball, effective_launch_mass)
    ball.SetPos(_vector(chrono, ball_x, ball_z))
    _enable_ground_contact_only(ball)
    system.AddBody(ball)

    # The real projectile rests on a horizontal launch trough until the sling
    # tension lifts it.  A contact-only model can chatter under the exact distance
    # constraint and does not represent a flat guiding trough precisely.
    # This prismatic support supplies an exact unilateral-equivalent runway: it
    # permits downrange translation and is disabled as soon as its solved normal
    # reaction would have to become tensile.
    ball_starts_on_runway = abs(float(ball_z) - TENNIS_BALL_RADIUS_M) <= 1.0e-9
    runway = None
    if ball_starts_on_runway:
        runway = chrono.ChLinkLockPrismatic()
        runway.Initialize(
            ball,
            ground,
            chrono.ChFramed(
                _vector(chrono, ball_x, ball_z),
                chrono.Q_ROTATE_Z_TO_X,
            ),
        )
        system.AddLink(runway)

    arm_tip_x, arm_tip_z = geometry["arm_tip"]
    sling = chrono.ChLinkDistance()
    initialized = sling.Initialize(
        arm,
        ball,
        False,
        _vector(chrono, arm_tip_x, arm_tip_z),
        _vector(chrono, ball_x, ball_z),
        False,
        spec.sling_length_m,
    )
    if initialized == 0:
        raise RuntimeError("Project Chrono rejected the sling distance constraint")
    system.AddLink(sling)
    if progress_enabled:
        print("chrono model built", flush=True)

    arm_tip_local = chrono.ChVector3d(0.5 * arm_length, 0.0, 0.0)
    arm_pivot_local = chrono.ChVector3d(
        0.5 * arm_length - spec.long_arm_length_m,
        0.0,
        0.0,
    )
    hanger_hinge_local = chrono.ChVector3d(-hanger_com_from_hinge, 0.0, 0.0)
    cw_center_local = chrono.ChVector3d(cw_center_from_com, 0.0, 0.0)

    def current_directions():
        current_arm_tip = arm.TransformPointLocalToParent(arm_tip_local)
        current_pivot = arm.TransformPointLocalToParent(arm_pivot_local)
        current_hinge = hanger.TransformPointLocalToParent(hanger_hinge_local)
        current_cw = hanger.TransformPointLocalToParent(cw_center_local)
        return (
            current_arm_tip,
            current_pivot,
            current_hinge,
            current_cw,
            current_arm_tip - current_pivot,
            current_cw - current_hinge,
        )

    def current_ground_clearances() -> tuple[float, float, float]:
        """Return signed clearance below each moving solid in the x-z view."""

        (
            current_arm_tip,
            current_pivot,
            current_hinge,
            current_cw,
            arm_direction,
            hanger_direction,
        ) = current_directions()
        arm_x, arm_z = _unit_xz(arm_direction)
        hanger_x, hanger_z = _unit_xz(hanger_direction)
        arm_short_z = float(current_pivot.z) - spec.short_arm_length_m * arm_z
        arm_clearance = (
            min(float(current_arm_tip.z), arm_short_z)
            - 0.5 * spec.arm_height_m * abs(arm_x)
        )
        hanger_clearance = (
            min(float(current_hinge.z), float(current_cw.z))
            - 0.5 * spec.hanger_height_m * abs(hanger_x)
        )
        counterweight_clearance = float(current_cw.z) - 0.5 * (
            COUNTERWEIGHT_BLOCK_SIZE_M * (abs(hanger_x) + abs(hanger_z))
        )
        return arm_clearance, hanger_clearance, counterweight_clearance

    initial_hanger_direction = _unit_xz(current_directions()[5])
    initial_arm_tip, _, _, _, initial_arm_direction, _ = current_directions()
    initial_ball_position = ball.GetPos()
    initial_sling_arm_angle = sling_arm_directed_angle_deg(
        arm_x=float(initial_arm_direction.x),
        arm_z=float(initial_arm_direction.z),
        sling_x=float(initial_ball_position.x - initial_arm_tip.x),
        sling_z=float(initial_ball_position.z - initial_arm_tip.z),
    )
    previous_sling_arm_unwrapped_angle = initial_sling_arm_angle
    previous_sling_arm_rotation = 0.0
    animation_time_axis = (
        np.asarray(trajectory_time_axis(), dtype=np.float64)
        if continue_mechanism_after_release
        else None
    )
    animation_trajectory = (
        np.zeros(
            (animation_time_axis.size, len(TRAJECTORY_CHANNEL_NAMES)),
            dtype=np.float64,
        )
        if animation_time_axis is not None
        else None
    )

    def sampled_state(arm_locked: bool, sling_attached: bool) -> np.ndarray:
        _, _, _, current_cw, arm_direction, hanger_direction = current_directions()
        position = ball.GetPos()
        velocity = ball.GetPosDt()
        return np.asarray(
            [
                float(position.x),
                float(position.z),
                float(velocity.x),
                float(velocity.z),
                _elevation_deg(arm_direction),
                _elevation_deg(hanger_direction),
                float(current_cw.z),
                1.0 if arm_locked else 0.0,
                1.0 if sling_attached else 0.0,
            ],
            dtype=np.float64,
        )

    arm_locked = True
    sling_attached = True
    runway_attached = ball_starts_on_runway
    released = False
    trigger_time = SIMULATION_DURATION_S
    release_time = SIMULATION_DURATION_S
    release_ball_x = float(ball_x)
    release_ball_z = float(ball_z)
    release_velocity_x = 0.0
    release_velocity_z = 0.0
    release_sling_arm_rotation = 0.0
    runway_release_time = SIMULATION_DURATION_S if runway_attached else 0.0
    minimum_ball_center_z = float(ball_z)
    (
        minimum_arm_ground_clearance,
        minimum_hanger_ground_clearance,
        minimum_counterweight_ground_clearance,
    ) = current_ground_clearances()
    minimum_runway_support_reaction = math.inf
    runway_reattach_count = 0
    max_pivot_reaction = 0.0
    max_hanger_reaction = 0.0
    max_sling_tension = 0.0
    max_contact_count = 0
    contact_step_count = 0
    main_joint = None
    next_sample = 1
    initial_state = sampled_state(arm_locked, sling_attached)
    if animation_trajectory is not None:
        animation_trajectory[0] = initial_state
    release_history_times = [0.0]
    release_kinematics_history = [initial_state[:4].copy()]
    stress_history = [np.zeros(len(STRESS_HISTORY_CHANNEL_NAMES), dtype=np.float64)]
    step_count = 0

    while float(system.GetChTime()) < SIMULATION_DURATION_S - 0.5 * TIME_STEP_S:
        system.DoStepDynamics(TIME_STEP_S)
        step_count += 1
        current_contact_count = int(system.GetNumContacts())
        max_contact_count = max(max_contact_count, current_contact_count)
        if current_contact_count > 0:
            contact_step_count += 1
        if progress_enabled and step_count % 1000 == 0:
            print(
                f"chrono step={step_count} time={float(system.GetChTime()):.6f}",
                flush=True,
            )
        time_s = float(system.GetChTime())
        record_release_history = not released
        (
            current_arm_tip,
            _,
            current_hinge,
            current_cw,
            arm_direction,
            hanger_direction,
        ) = current_directions()
        arm_clearance, hanger_clearance, counterweight_clearance = (
            current_ground_clearances()
        )
        minimum_arm_ground_clearance = min(
            minimum_arm_ground_clearance,
            arm_clearance,
        )
        minimum_hanger_ground_clearance = min(
            minimum_hanger_ground_clearance,
            hanger_clearance,
        )
        minimum_counterweight_ground_clearance = min(
            minimum_counterweight_ground_clearance,
            counterweight_clearance,
        )
        ball_position = ball.GetPos()
        ball_velocity = ball.GetPosDt()
        runway_reattached_this_step = False
        if (
            runway is not None
            and launch_runway_should_reattach(
                runway_attached=runway_attached,
                sling_attached=sling_attached,
                ball_center_z_m=float(ball_position.z),
                ball_vertical_velocity_mps=float(ball_velocity.z),
            )
        ):
            # Resolve this sampled ground crossing as an inelastic trough contact
            # before restoring the exact horizontal constraint.  This prevents a
            # one-step contact crossing from becoming part of the launch state.
            ball.SetPos(
                _vector(
                    chrono,
                    float(ball_position.x),
                    TENNIS_BALL_RADIUS_M,
                    y=float(ball_position.y),
                )
            )
            ball.SetPosDt(
                _vector(
                    chrono,
                    float(ball_velocity.x),
                    0.0,
                    y=float(ball_velocity.y),
                )
            )
            runway.SetDisabled(False)
            runway_attached = True
            runway_reattached_this_step = True
            runway_reattach_count += 1
            ball_position = ball.GetPos()
            ball_velocity = ball.GetPosDt()
        if record_release_history:
            minimum_ball_center_z = min(
                minimum_ball_center_z,
                float(ball_position.z),
            )
        hanger_reaction = _reaction_magnitude(hanger_joint)
        sling_tension = _reaction_magnitude(sling) if sling_attached else 0.0
        pivot_reaction = 0.0
        max_hanger_reaction = max(max_hanger_reaction, hanger_reaction)
        max_sling_tension = max(max_sling_tension, sling_tension)
        if main_joint is not None:
            pivot_reaction = _reaction_magnitude(main_joint)
            max_pivot_reaction = max(max_pivot_reaction, pivot_reaction)
        stress_sample = None
        if record_release_history:
            strength = structural_strength_state(
                spec,
                pivot_reaction_n=pivot_reaction,
                hanger_reaction_n=hanger_reaction,
                sling_tension_n=sling_tension,
            )
            stress_sample = np.asarray(
                [
                    strength["arm_combined_normal_stress_mpa"],
                    strength["hanger_combined_normal_stress_mpa"],
                    strength["peak_strength_utilization"],
                ],
                dtype=np.float64,
            )

        if arm_locked:
            drop_angle = _drop_angle_deg(
                initial_hanger_direction,
                _unit_xz(hanger_direction),
            )
            if drop_angle >= spec.cw_trigger_drop_angle_deg:
                arm.SetFixed(False)
                pivot_frame = chrono.ChFramed(
                    _vector(chrono, pivot_x, pivot_z),
                    joint_rotation,
                )
                main_joint = chrono.ChLinkLockRevolute()
                main_joint.Initialize(arm, ground, pivot_frame)
                system.AddLink(main_joint)
                main_damper = chrono.ChLinkRSDA()
                main_damper.Initialize(arm, ground, pivot_frame)
                main_damper.SetDampingCoefficient(MAIN_BEARING_DAMPING_NMS_RAD)
                system.AddLink(main_damper)
                arm_locked = False
                trigger_time = time_s

        if runway_attached and not runway_reattached_this_step:
            if runway is None:
                raise RuntimeError("launch runway state is inconsistent")
            support_reaction = float(runway.GetReaction2().force.x)
            minimum_runway_support_reaction = min(
                minimum_runway_support_reaction,
                support_reaction,
            )
            if launch_runway_should_release(
                arm_locked=arm_locked,
                sling_attached=sling_attached,
                support_reaction_n=support_reaction,
            ):
                runway.SetDisabled(True)
                runway_attached = False
                runway_release_time = time_s

        if not arm_locked and sling_attached:
            current_sling_arm_wrapped_angle = sling_arm_directed_angle_deg(
                arm_x=float(arm_direction.x),
                arm_z=float(arm_direction.z),
                sling_x=float(ball_position.x - current_arm_tip.x),
                sling_z=float(ball_position.z - current_arm_tip.z),
            )
            current_sling_arm_unwrapped_angle = unwrap_angle_deg(
                previous_sling_arm_unwrapped_angle,
                current_sling_arm_wrapped_angle,
            )
            current_sling_arm_rotation = (
                current_sling_arm_unwrapped_angle - initial_sling_arm_angle
            )
            if sling_release_should_trigger(
                previous_sling_arm_rotation_deg=previous_sling_arm_rotation,
                current_sling_arm_rotation_deg=current_sling_arm_rotation,
                target_sling_arm_rotation_deg=spec.release_sling_arm_rotation_deg,
            ):
                if runway_attached:
                    if runway is None:
                        raise RuntimeError("launch runway state is inconsistent")
                    runway.SetDisabled(True)
                    runway_attached = False
                    runway_release_time = time_s
                sling.SetDisabled(True)
                # Animation-only continuation uses the separately integrated ball
                # flight, so the released Chrono ball must no longer contact and
                # perturb the mechanism.
                ball.EnableCollision(False)
                _set_ball_mass(chrono, ball, TENNIS_BALL_MASS_KG)
                sling_attached = False
                released = True
                release_time = time_s
                release_ball_x = float(ball_position.x)
                release_ball_z = float(ball_position.z)
                release_velocity_x = float(ball_velocity.x)
                release_velocity_z = float(ball_velocity.z)
                release_sling_arm_rotation = current_sling_arm_rotation
            previous_sling_arm_unwrapped_angle = current_sling_arm_unwrapped_angle
            previous_sling_arm_rotation = current_sling_arm_rotation

        if record_release_history:
            if stress_sample is None:
                raise RuntimeError("pre-release stress state was not sampled")
            release_history_times.append(time_s)
            release_kinematics_history.append(
                np.asarray(
                    [
                        float(ball_position.x),
                        float(ball_position.z),
                        float(ball_velocity.x),
                        float(ball_velocity.z),
                    ],
                    dtype=np.float64,
                )
            )
            stress_history.append(stress_sample)

        if animation_time_axis is not None and animation_trajectory is not None:
            while (
                next_sample < animation_time_axis.size
                and time_s + 0.5 * TIME_STEP_S
                >= animation_time_axis[next_sample]
            ):
                animation_trajectory[next_sample] = sampled_state(
                    arm_locked,
                    sling_attached,
                )
                next_sample += 1

        if released and not continue_mechanism_after_release:
            break

    final_state = sampled_state(arm_locked, sling_attached)
    total_time = release_time if released else float(system.GetChTime())
    history_times = np.asarray(release_history_times, dtype=np.float64)
    release_kinematics = _resample_phase_history(
        history_times,
        np.asarray(release_kinematics_history, dtype=np.float64),
        total_time_s=total_time,
    )
    stress = _resample_phase_history(
        history_times,
        np.asarray(stress_history, dtype=np.float64),
        total_time_s=total_time,
        preserve_channel_maxima=True,
    )
    summary = np.asarray(
        [
            float(geometry["loaded_max_height_m"]),
            minimum_ball_center_z,
            trigger_time,
            1.0 if released else 0.0,
            release_sling_arm_rotation,
            minimum_arm_ground_clearance,
            minimum_hanger_ground_clearance,
            minimum_counterweight_ground_clearance,
        ],
        dtype=np.float64,
    )

    if release_kinematics.shape != (
        RELEASE_PHASE_SAMPLE_COUNT,
        len(RELEASE_KINEMATICS_CHANNEL_NAMES),
    ) or not np.all(np.isfinite(release_kinematics)):
        raise RuntimeError("simulation produced invalid release kinematics")
    if stress.shape != (
        RELEASE_PHASE_SAMPLE_COUNT,
        len(STRESS_HISTORY_CHANNEL_NAMES),
    ) or not np.all(np.isfinite(stress)):
        raise RuntimeError("simulation produced invalid stress history")
    if summary.shape != (len(RELEASE_SUMMARY_NAMES),) or not np.all(
        np.isfinite(summary)
    ):
        raise RuntimeError("simulation produced invalid release summary")

    if animation_trajectory is not None and animation_time_axis is not None:
        if next_sample < animation_time_axis.size:
            animation_trajectory[next_sample:] = final_state
        if released:
            flight_start = int(
                np.searchsorted(animation_time_axis, release_time, side="left")
            )
            relative_times = tuple(
                float(value - release_time)
                for value in animation_time_axis[flight_start:]
            )
            flight = ballistic_flight_from_release(
                release_x_m=release_ball_x,
                release_z_m=release_ball_z,
                release_vx_mps=release_velocity_x,
                release_vz_mps=release_velocity_z,
                sample_times_s=relative_times,
            )
            animation_trajectory[flight_start:, :4] = np.asarray(
                flight.samples,
                dtype=np.float64,
            )
        if not np.all(np.isfinite(animation_trajectory)):
            raise RuntimeError("simulation produced invalid animation trajectory")

    diagnostics = {
        "model": MODEL_NAME,
        "steps": step_count,
        "simulated_time_s": float(system.GetChTime()),
        "total_time_s": total_time,
        "total_time_endpoint": "release" if released else "simulation_cutoff",
        "triggered": not arm_locked,
        "released": released,
        "moving_mass_kg": spec.moving_mass_kg,
        "initial_ball_x_offset_m": spec.initial_ball_x_offset_m,
        "release_sling_arm_rotation_deg": release_sling_arm_rotation,
        "release_ball_x_m": release_ball_x,
        "release_ball_z_m": release_ball_z,
        "release_velocity_x_mps": release_velocity_x,
        "release_velocity_z_mps": release_velocity_z,
        "launch_runway_release_time_s": runway_release_time,
        "launch_runway_reattach_count": runway_reattach_count,
        "minimum_ball_center_z_m": minimum_ball_center_z,
        "minimum_arm_ground_clearance_m": minimum_arm_ground_clearance,
        "minimum_hanger_ground_clearance_m": minimum_hanger_ground_clearance,
        "minimum_counterweight_ground_clearance_m": (
            minimum_counterweight_ground_clearance
        ),
        "max_pivot_reaction_n": max_pivot_reaction,
        "max_hanger_reaction_n": max_hanger_reaction,
        "max_sling_tension_n": max_sling_tension,
        "max_contact_count": max_contact_count,
        "contact_step_count": contact_step_count,
        "minimum_runway_support_reaction_n": (
            minimum_runway_support_reaction
            if math.isfinite(minimum_runway_support_reaction)
            else 0.0
        ),
        "continued_mechanism_after_release": bool(
            continue_mechanism_after_release
        ),
        "contacts_at_end": int(system.GetNumContacts()),
    }
    return {
        "total_time_s": float(total_time),
        "summary": summary,
        "release_kinematics": release_kinematics,
        "stress_history": stress,
        "animation_trajectory": animation_trajectory,
        "diagnostics": diagnostics,
    }


def _save_scalar_rawdata(
    rawdata_dir: Path,
    field: tuple[str, str, str],
    value: float,
    **extra_metadata: object,
) -> tuple[str, list[int]]:
    rawdata_name, quantity_name, unit = field
    values = np.asarray(float(value), dtype=np.float64)
    metadata = {
        "schema_version": 1,
        "rawdata_name": rawdata_name,
        "shape": list(values.shape),
        "quantity_name": quantity_name,
        "unit": unit,
        "model": MODEL_NAME,
        **extra_metadata,
    }
    _save_npz(
        rawdata_dir,
        f"{rawdata_name}.npz",
        values=values,
        metadata=np.asarray(json.dumps(metadata, separators=(",", ":"))),
    )
    return rawdata_name, list(values.shape)


def _save_phase_curve_rawdata(
    rawdata_dir: Path,
    field: tuple[str, str, str],
    values: np.ndarray,
    phase_axis: np.ndarray,
    **extra_metadata: object,
) -> tuple[str, list[int]]:
    rawdata_name, quantity_name, unit = field
    curve = np.asarray(values, dtype=np.float64).reshape(-1)
    if curve.shape != phase_axis.shape or not np.all(np.isfinite(curve)):
        raise RuntimeError(f"{rawdata_name} must match the finite release-phase axis")
    metadata = {
        "schema_version": 1,
        "rawdata_name": rawdata_name,
        "shape": list(curve.shape),
        "quantity_name": quantity_name,
        "unit": unit,
        "axis_names": ["release_phase"],
        "axes": [
            {
                "index": 0,
                "size": int(curve.shape[0]),
                "name": "release_phase",
                "values_key": "axis_release_phase",
            }
        ],
        "time_parameterization": "physical_time_s = release_phase * total_time_s",
        "model": MODEL_NAME,
        **extra_metadata,
    }
    _save_npz(
        rawdata_dir,
        f"{rawdata_name}.npz",
        values=curve,
        axis_release_phase=phase_axis,
        metadata=np.asarray(json.dumps(metadata, separators=(",", ":"))),
    )
    return rawdata_name, list(curve.shape)


def simulate(request: Mapping[str, object], rawdata_dir: Path) -> Mapping[str, object]:
    # The external runtime boundary is deliberate: yadof is not installed here.
    import pychrono as chrono

    assigned = request["parameters"]["assigned"]
    result = run_task_model(chrono, assigned)
    summary = np.asarray(result["summary"], dtype=np.float64)
    release_kinematics = np.asarray(result["release_kinematics"], dtype=np.float64)
    stress = np.asarray(result["stress_history"], dtype=np.float64)
    phase_axis = np.asarray(release_phase_axis(), dtype=np.float64)
    if summary.shape != (len(RELEASE_SUMMARY_NAMES),):
        raise RuntimeError("release summary does not match its semantic fields")

    rawdata_shapes: dict[str, list[int]] = {}
    name, shape = _save_scalar_rawdata(
        rawdata_dir,
        TOTAL_TIME_RAWDATA_FIELD,
        float(result["total_time_s"]),
        endpoint="release_or_simulation_cutoff",
    )
    rawdata_shapes[name] = shape

    summary_values = dict(zip(RELEASE_SUMMARY_NAMES, summary, strict=True))
    for field in RELEASE_SUMMARY_RAWDATA_FIELDS:
        name, shape = _save_scalar_rawdata(
            rawdata_dir,
            field,
            float(summary_values[field[1]]),
        )
        rawdata_shapes[name] = shape

    for index, field in enumerate(RELEASE_KINEMATICS_RAWDATA_FIELDS):
        name, shape = _save_phase_curve_rawdata(
            rawdata_dir,
            field,
            release_kinematics[:, index],
            phase_axis,
        )
        rawdata_shapes[name] = shape

    for index, field in enumerate(STRESS_HISTORY_RAWDATA_FIELDS):
        name, shape = _save_phase_curve_rawdata(
            rawdata_dir,
            field,
            stress[:, index],
            phase_axis,
            peak_preserving_resample=True,
        )
        rawdata_shapes[name] = shape

    diagnostics = dict(result["diagnostics"])
    diagnostics.update(
        {
            "pychrono_module": str(Path(chrono.__file__).resolve()),
            "rawdata_shapes": rawdata_shapes,
        }
    )
    return diagnostics


if __name__ == "__main__":
    raise SystemExit(worker_main(simulate))
