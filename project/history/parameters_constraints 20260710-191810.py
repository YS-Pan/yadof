"""
HFSS optimization parameters generated from an AEDT project.
"""

from __future__ import annotations

try:
    from .parameters_constraints_class import Parameter
except ImportError:
    from parameters_constraints_class import Parameter

PARAMETERS = (
    Parameter('dipole_gap', ((2, 4),), unit='mm'),
    Parameter('dipole_l', ((27, 31),), unit='mm'),
    Parameter('dipole_post_xposi', ((2, 3),), unit='mm'),
    Parameter('dipole_w', ((4, 8),), unit='mm'),
    Parameter('feedline1_l', ((26, 34),), unit='mm'),
    Parameter('feedline1_w', ((3, 4),), unit='mm'),
    Parameter('feedline2_xposi', ((3, 9),), unit='mm'),
    Parameter('feedline2_yposi', ((7, 11),), unit='mm'),
    Parameter('slot_l', ((35, 40),), unit='mm'),
    Parameter('slot_w', ((1, 3),), unit='mm'),
    Parameter('strip_l', ((16, 24),), unit='mm'),
    Parameter('strip_w', ((1, 4),), unit='mm'),
    Parameter('top_sub_zposi', ((28, 32),), unit='mm'),
    Parameter('yagi_l1', ((46, 54),), unit='mm'),
    Parameter('yagi_l2', ((12, 16),), unit='mm'),
    Parameter('yagi_w', ((0.5, 1.5),), unit='mm'),
    Parameter('yagi_w2', ((0.5, 1.5),), unit='mm'),
    Parameter('yagi_xmove', ((5, 9),), unit='mm'),
    Parameter('yagi_yposi', ((15, 19),), unit='mm'),
)

CONSTRAINTS = (
    #"-(L1+L2+L3+L4+L5+D1+D2+D3+D4+D5-80)",
)


def get_parameters() -> tuple[Parameter, ...]:
    return tuple(PARAMETERS)
