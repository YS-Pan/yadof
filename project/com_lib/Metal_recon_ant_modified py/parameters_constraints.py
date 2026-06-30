"""
Parameter and constraint definitions for an optimization program.

- PARAMETERS: tuple of `para` objects
- CONSTRAINTS: tuple of strings; each string is an expression that must be > 0

Notes:
- Constraints are intentionally kept as strings.
- Constraint evaluation should provide needed names such as `math`, `abs`, etc.
"""

from __future__ import annotations

from parameters_constraints_class import para

PARAMETERS = (
    para('Ah1', ((0, 9.5),), value=9.4322099999999995, normValue=float("nan"), unit='mm'),
    para('Ah2', ((0, 9.5),), value=1.83968, normValue=float("nan"), unit='mm'),
    para('Ah3', ((0, 9.5),), value=8.5048499999999994, normValue=float("nan"), unit='mm'),
    para('Ah4', ((0, 9.5),), value=9.1623400000000004, normValue=float("nan"), unit='mm'),
    para('Ah5', ((0, 9.5),), value=1.5263800000000001, normValue=float("nan"), unit='mm'),
    para('Al1', ((0, 9.5),), value=5.3214600000000001, normValue=float("nan"), unit='mm'),
    para('Al2', ((0, 9.5),), value=2.5078800000000001, normValue=float("nan"), unit='mm'),
    para('Al3', ((0, 9.5),), value=0.44845800000000002, normValue=float("nan"), unit='mm'),
    para('Al4', ((0, 9.5),), value=5.1543400000000004, normValue=float("nan"), unit='mm'),
    para('Al5', ((0, 9.5),), value=1.7719100000000001, normValue=float("nan"), unit='mm'),
    para('Angle', ((-60, 15),), value=-45.6798, normValue=float("nan"), unit=''),
    para('chokeZshift', ((0, 20),), value=3.8307099999999998, normValue=float("nan"), unit='mm'),
    para('cornerH', ((0, 30),), value=3.1390400000000001, normValue=float("nan"), unit='mm'),
    para('cornerLen', ((4, 24),), value=21.558700000000002, normValue=float("nan"), unit='mm'),
    para('cornerLen1', ((4, 32),), value=25.5383, normValue=float("nan"), unit='mm'),
    para('cornerWidth', ((4, 25),), value=19.870699999999999, normValue=float("nan"), unit='mm'),
    para('cornerWidth1', ((4, 25),), value=20.2484, normValue=float("nan"), unit='mm'),
    para('D1', ((0, 15),), value=14.3408, normValue=float("nan"), unit='mm'),
    para('D2', ((0, 15),), value=2.91845, normValue=float("nan"), unit='mm'),
    para('D3', ((0, 15),), value=0.22573099999999999, normValue=float("nan"), unit='mm'),
    para('D4', ((0, 15),), value=2.04508, normValue=float("nan"), unit='mm'),
    para('D5', ((0, 15),), value=7.4178699999999997, normValue=float("nan"), unit='mm'),
    para('L1', ((0, 15),), value=10.582000000000001, normValue=float("nan"), unit='mm'),
    para('L2', ((0, 15),), value=1.7001900000000001, normValue=float("nan"), unit='mm'),
    para('L3', ((0, 15),), value=5.4836, normValue=float("nan"), unit='mm'),
    para('L4', ((0, 15),), value=7.6635999999999997, normValue=float("nan"), unit='mm'),
    para('L5', ((0, 15),), value=3.1341899999999998, normValue=float("nan"), unit='mm'),
    para('N', (1, 2, 3, 4, 5), value=5, normValue=float("nan"), unit=''),
    para('rearPlasticLen', ((15, 35),), value=15.4186, normValue=float("nan"), unit='mm'),
    para('trump0Len', ((4, 15),), value=13.845800000000001, normValue=float("nan"), unit='mm'),
    para('trump0Width', ((4, 15),), value=5.8853799999999996, normValue=float("nan"), unit='mm'),
    para('trumpH', ((10, 45),), value=35.490000000000002, normValue=float("nan"), unit='mm'),
)

CONSTRAINTS = (
)
