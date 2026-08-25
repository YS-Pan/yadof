"""Optimization dimensions for the flexible King Arthur trebuchet."""

from __future__ import annotations

from yadof.job_template import Parameter


PARAMETERS = (
    Parameter("pivot_height_m", ((0.50, 3.00),), unit="m"),
    Parameter("long_arm_length_m", ((0.40, 3.00),), unit="m"),
    Parameter("short_arm_length_m", ((0.08, 1.00),), unit="m"),
    Parameter("hanger_length_m", ((0.20, 2.00),), unit="m"),
    Parameter("arm_width_m", ((0.020, 0.150),), unit="m"),
    Parameter("arm_height_m", ((0.030, 0.300),), unit="m"),
    Parameter("hanger_width_m", ((0.015, 0.120),), unit="m"),
    Parameter("hanger_height_m", ((0.025, 0.200),), unit="m"),
    # Global cocked angles.  The arm may start on either side of vertical down;
    # the small gap avoids the degenerate exactly-down configuration.
    Parameter("loaded_arm_angle_deg", ((-179.0, -95.0), (-85.0, -1.0)), unit="deg"),
    Parameter("loaded_hanger_angle_deg", ((1.0, 179.0),), unit="deg"),
    # Signed initial ball position relative to the arm tip.  The ball stays on
    # the runway and the taut sling length is derived from the resulting geometry.
    Parameter(
        "initial_ball_x_offset_m",
        ((-4.00, -0.10), (0.10, 4.00)),
        unit="m",
    ),
    Parameter("cw_trigger_drop_angle_deg", ((5.0, 170.0),), unit="deg"),
    # Signed, continuously unwrapped sling rotation relative to the arm.  Two
    # turns in either direction are available; a small zero band avoids an
    # immediate release at initialization.
    Parameter(
        "release_sling_arm_rotation_deg",
        ((-720.0, -5.0), (5.0, 720.0)),
        unit="deg",
    ),
)

CONSTRAINTS = ()


def get_parameters() -> tuple[Parameter, ...]:
    return tuple(PARAMETERS)

