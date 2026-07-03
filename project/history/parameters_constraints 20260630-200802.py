"""
HFSS optimization parameters generated from an AEDT project.
"""

from __future__ import annotations

try:
    from .parameters_constraints_class import Parameter
except ImportError:
    from parameters_constraints_class import Parameter

PARAMETERS = (
    Parameter('Ah1', ((0, 9.5),), unit='mm'),
    Parameter('Ah2', ((0, 9.5),), unit='mm'),
    Parameter('Ah3', ((0, 9.5),), unit='mm'),
    Parameter('Ah4', ((0, 9.5),), unit='mm'),
    Parameter('Ah5', ((0, 9.5),), unit='mm'),
    Parameter('Al1', ((0, 9.5),), unit='mm'),
    Parameter('Al2', ((0, 9.5),), unit='mm'),
    Parameter('Al3', ((0, 9.5),), unit='mm'),
    Parameter('Al4', ((0, 9.5),), unit='mm'),
    Parameter('Al5', ((0, 9.5),), unit='mm'),
    Parameter('Angle', ((-60, 15),), unit=''),
    Parameter('chokeZshift', ((0, 20),), unit='mm'),
    Parameter('cornerH', ((0, 30),), unit='mm'),
    Parameter('cornerLen', ((4, 24),), unit='mm'),
    Parameter('cornerLen1', ((4, 32),), unit='mm'),
    Parameter('cornerWidth', ((4, 25),), unit='mm'),
    Parameter('cornerWidth1', ((4, 25),), unit='mm'),
    Parameter('D1', ((0, 15),), unit='mm'),
    Parameter('D2', ((0, 15),), unit='mm'),
    Parameter('D3', ((0, 15),), unit='mm'),
    Parameter('D4', ((0, 15),), unit='mm'),
    Parameter('D5', ((0, 15),), unit='mm'),
    Parameter('L1', ((0, 15),), unit='mm'),
    Parameter('L2', ((0, 15),), unit='mm'),
    Parameter('L3', ((0, 15),), unit='mm'),
    Parameter('L4', ((0, 15),), unit='mm'),
    Parameter('L5', ((0, 15),), unit='mm'),
    Parameter('N', (1, 2, 3, 4, 5), unit=''),
    Parameter('rearPlasticLen', ((15, 35),), unit='mm'),
    Parameter('trump0Len', ((4, 15),), unit='mm'),
    Parameter('trump0Width', ((4, 15),), unit='mm'),
    Parameter('trumpH', ((10, 45),), unit='mm'),
)

CONSTRAINTS = (
    "-(L1+L2+L3+L4+L5+D1+D2+D3+D4+D5-80)",
)


def get_parameters() -> tuple[Parameter, ...]:
    return tuple(PARAMETERS)
