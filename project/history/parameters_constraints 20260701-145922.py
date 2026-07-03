"""
HFSS optimization parameters generated from an AEDT project.
"""

from __future__ import annotations

try:
    from .parameters_constraints_class import Parameter
except ImportError:
    from parameters_constraints_class import Parameter

PARAMETERS = (
    Parameter('dc_line_w', ((0.10000000000000001, 0.29999999999999999),), unit='mm'),
    Parameter('dc_pad', ((1, 3),), unit='mm'),
    Parameter('dipole_gap', ((1.5, 4.5),), unit='mm'),
    Parameter('dipole_l', ((14.5, 43.5),), unit='mm'),
    Parameter('dipole_post_r', ((0.5, 1.5),), unit='mm'),
    Parameter('dipole_post_xposi', ((1, 3),), unit='mm'),
    Parameter('dipole_w', ((3, 9),), unit='mm'),
    Parameter('feedline1_l', ((15, 45),), unit='mm'),
    Parameter('feedline1_w', ((1.79, 5.3700000000000001),), unit='mm'),
    Parameter('feedline2_w', ((0.745, 2.2349999999999999),), unit='mm'),
    Parameter('feedline2_xposi', ((3, 9),), unit='mm'),
    Parameter('feedline2_yposi', ((4.5, 13.5),), unit='mm'),
    Parameter('gnd_subx', ((50, 150),), unit='mm'),
    Parameter('gnd_suby', ((50, 150),), unit='mm'),
    Parameter('gnd_subz', ((0.25, 0.75),), unit='mm'),
    Parameter('para_deg', ((20, 60),), unit='deg'),
    Parameter('para_dipole_gap', ((0.5, 1.5),), unit='mm'),
    Parameter('para_roatate', ((22.5, 67.5),), unit='deg'),
    Parameter('para_w', ((1.5, 4.5),), unit='mm'),
    Parameter('pin_cap', ((0.085000000000000006, 0.255),), unit='pF'),
    Parameter('pin_ind', ((0.29999999999999999, 0.90000000000000002),), unit='nH'),
    Parameter('pin_res', ((4000, 12000),), unit='ohm'),
    Parameter('rlc', ((0.25, 0.75),), unit='mm'),
    Parameter('slot_l', ((18.5, 55.5),), unit='mm'),
    Parameter('slot_w', ((1, 3),), unit='mm'),
    Parameter('strip_l', ((10, 30),), unit='mm'),
    Parameter('strip_w', ((1, 3),), unit='mm'),
    Parameter('thickness_metal', ((0.0089999999999999993, 0.027),), unit='mm'),
    Parameter('top_sub_zposi', ((15, 45),), unit='mm'),
    Parameter('top_subx', ((40, 120),), unit='mm'),
    Parameter('top_suby', ((60, 180),), unit='mm'),
    Parameter('yagi2_l1', ((24.5, 73.5),), unit='mm'),
    Parameter('yagi2_rotate_deg', ((22.5, 67.5),), unit='deg'),
    Parameter('yagi2_w', ((0.5, 1.5),), unit='mm'),
    Parameter('yagi2_xmove', ((-1, 1),), unit='mm'),
    Parameter('yagi2_xposi', ((-1, 1),), unit='mm'),
    Parameter('yagi2_yposi', ((8.75, 26.25),), unit='mm'),
    Parameter('yagi3_l1', ((24.5, 73.5),), unit='mm'),
    Parameter('yagi3_l2', ((8.75, 26.25),), unit='mm'),
    Parameter('yagi3_w', ((0.5, 1.5),), unit='mm'),
    Parameter('yagi3_w2', ((0.5, 1.5),), unit='mm'),
    Parameter('yagi3_xmove', ((3.75, 11.25),), unit='mm'),
    Parameter('yagi3_yposi', ((8.75, 26.25),), unit='mm'),
    Parameter('yagi_cut_l', ((1, 3),), unit='mm'),
    Parameter('yagi_cut_w', ((0.29999999999999999, 0.90000000000000002),), unit='mm'),
    Parameter('yagi_l1', ((24.5, 73.5),), unit='mm'),
    Parameter('yagi_l2', ((7.25, 21.75),), unit='mm'),
    Parameter('yagi_w', ((0.5, 1.5),), unit='mm'),
    Parameter('yagi_w2', ((0.5, 1.5),), unit='mm'),
    Parameter('yagi_xmove', ((3.5, 10.5),), unit='mm'),
    Parameter('yagi_yposi', ((8.75, 26.25),), unit='mm'),
)

CONSTRAINTS = (
    #"-(L1+L2+L3+L4+L5+D1+D2+D3+D4+D5-80)",
)


def get_parameters() -> tuple[Parameter, ...]:
    return tuple(PARAMETERS)
