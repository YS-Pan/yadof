"""
HFSS optimization parameters generated from an AEDT project.
"""

from __future__ import annotations

from yadof.job_template import Parameter

PARAMETERS = (
    Parameter('dipole_gap', ((1.6, 4),), unit='mm'),
    Parameter('dipole_l', ((26, 32),), unit='mm'),
    Parameter('dipole_post_xposi', ((1, 3),), unit='mm'),
    Parameter('dipole_w', ((4, 9),), unit='mm'),
    Parameter('feedline2_yposi', ((7, 15),), unit='mm'),
    Parameter('gnd_cut_a', ((0, 2),), unit='mm'),
    Parameter('slot_l', ((34, 45),), unit='mm'),
    Parameter('slot_w', ((0.8, 3),), unit='mm'),
    Parameter('strip_l', ((17, 23),), unit='mm'),
    Parameter('strip_w', ((1, 3),), unit='mm'),
    Parameter('top_sub_zposi', ((28, 40),), unit='mm'),
    Parameter('yagi_l1', ((46, 56),), unit='mm'),
    Parameter('yagi_l2', ((12, 16),), unit='mm'),
    Parameter('yagi_w', ((0.5, 2),), unit='mm'),
    Parameter('yagi_w2', ((0.5, 1.5),), unit='mm'),
    Parameter('yagi_xmove', ((-9, 9),), unit='mm'),
    Parameter('yagi_yposi', ((15, 25),), unit='mm'),
)

CONSTRAINTS = (
    #"-(L1+L2+L3+L4+L5+D1+D2+D3+D4+D5-80)",
)


def get_parameters() -> tuple[Parameter, ...]:
    return tuple(PARAMETERS)
