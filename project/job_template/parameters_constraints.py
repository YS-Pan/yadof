"""HFSS optimization parameters for ``Metal_recon_ant.aedt``."""

from __future__ import annotations

try:
    from .parameters_constraints_class import Parameter
except ImportError:  # Allows copied job folders to run workflow.py directly.
    from parameters_constraints_class import Parameter


PARAMETERS = (
    Parameter('feed_pad_r', ((1, 2),), unit='mm'),
    Parameter('feed_strip_patch_gap', ((0.20000000000000001, 0.80000000000000004),), unit='mm'),
    Parameter('feed_strip_w', ((0.5, 1.5),), unit='mm'),
    Parameter('feedline1_w', ((1.2, 1.6000000000000001),), unit='mm'),
    Parameter('feedline2_l', ((2, 8),), unit='mm'),
    Parameter('feedline2_w', ((1.8, 2.2000000000000002),), unit='mm'),
    Parameter('gnd_metal_match1_l', ((8, 12),), unit='mm'),
    Parameter('gnd_metal_match1_w', ((4, 8),), unit='mm'),
    Parameter('gnd_metal_match_gap', ((0.29999999999999999, 1),), unit='mm'),
    Parameter('iso_slot_l', ((86, 96),), unit='mm'),
    Parameter('iso_slot_w', ((2, 4),), unit='mm'),
    Parameter('iso_slot_xposi', ((1, 3),), unit='mm'),
    Parameter('metal_match_w', ((0.59999999999999998, 1.2),), unit='mm'),
    Parameter('metal_patch_x', ((30, 45),), unit='mm'),
    Parameter('metal_patch_y', ((50, 60),), unit='mm'),
    Parameter('metal_patch_zposi', ((7, 13),), unit='mm'),
    Parameter('patch_feed_strip_cut_l', ((6, 14),), unit='mm'),
    Parameter('phase_l2', ((7, 9),), unit='mm'),
    Parameter('phase_xposi', ((0, 3),), unit='mm'),
)

CONSTRAINTS: tuple[str, ...] = ()


def get_parameters() -> tuple[Parameter, ...]:
    return tuple(PARAMETERS)

