"""HFSS optimization parameters for ``Metal_recon_ant.aedt``."""

from __future__ import annotations

try:
    from .parameters_constraints_class import Parameter
except ImportError:  # Allows copied job folders to run workflow.py directly.
    from parameters_constraints_class import Parameter


PARAMETERS = (
    Parameter("feed_inner_yposi", ((8.0, 19.0),), unit="mm"),
    Parameter("feedline1_w", ((1.2, 1.6000000000000001),), unit="mm"),
    Parameter("feedline2_l", ((4.0, 14.0),), unit="mm"),
    Parameter("feedline2_w", ((2.0, 3.0),), unit="mm"),
    Parameter("gnd_metal_match1_l", ((8.0, 12.0),), unit="mm"),
    Parameter("gnd_metal_match1_w", ((4.0, 8.0),), unit="mm"),
    Parameter("gnd_metal_match_gap", ((0.4, 1.2),), unit="mm"),
    Parameter("iso_slot_l", ((90.0, 100.0),), unit="mm"),
    Parameter("iso_slot_w", ((2.0, 4.0),), unit="mm"),
    Parameter("iso_slot_xposi", ((1.0, 4.0),), unit="mm"),
    Parameter("metal_match_w", ((0.5, 1.5),), unit="mm"),
    Parameter("metal_patch_x", ((20.0, 40.0),), unit="mm"),
    Parameter("metal_patch_y", ((40.0, 60.0),), unit="mm"),
    Parameter("metal_patch_zposi", ((6.0, 14.0),), unit="mm"),
    Parameter("phase_l2", ((8.0, 12.0),), unit="mm"),
    Parameter("phase_xposi", ((-2.0, 2.0),), unit="mm"),
)

CONSTRAINTS: tuple[str, ...] = ()


def get_parameters() -> tuple[Parameter, ...]:
    return tuple(PARAMETERS)
