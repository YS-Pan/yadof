"""Symmetry-reduced BVD parameters for a 5-series/4-shunt SAW ladder."""

from __future__ import annotations

from yadof.job_template import Parameter


# Frequencies are series-resonance frequencies (fs), not anti-resonances.
# Capacitances are the BVD static capacitances C0.  Mirror-related resonators
# share one variable so the reciprocal two-port remains geometrically symmetric.
PARAMETERS = (
    Parameter("fs_s_outer", ((990.0, 1012.0),), unit="Meg"),
    Parameter("fs_s_inner", ((990.0, 1012.0),), unit="Meg"),
    Parameter("fs_s_center", ((990.0, 1012.0),), unit="Meg"),
    Parameter("fs_p_outer", ((948.0, 976.0),), unit="Meg"),
    Parameter("fs_p_inner", ((948.0, 976.0),), unit="Meg"),
    Parameter("c0_s_outer", ((0.10, 8.0),), unit="p"),
    Parameter("c0_s_inner", ((0.10, 8.0),), unit="p"),
    Parameter("c0_s_center", ((0.10, 8.0),), unit="p"),
    Parameter("c0_p_outer", ((0.10, 8.0),), unit="p"),
    Parameter("c0_p_inner", ((0.10, 8.0),), unit="p"),
)

CONSTRAINTS = ()


def get_parameters() -> tuple[Parameter, ...]:
    return tuple(PARAMETERS)

