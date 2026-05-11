"""Default task parameters for the test workflow."""

from __future__ import annotations

try:
    from .parameters_constraints_class import Parameter
except ImportError:  # Allows copied job folders to run workflow.py directly.
    from parameters_constraints_class import Parameter


PARAMETERS = (
    Parameter("x0", ((-2.0, 2.0),), unit=""),
    Parameter("x1", ((-2.0, 2.0),), unit=""),
    Parameter("x2", ((0.0, 1.0),), unit=""),
    Parameter("x3", ((-2.0, 2.0),), unit=""),
    Parameter("x4", ((-2.0, 2.0),), unit=""),
    Parameter("x5", ((-2.0, 2.0),), unit=""),
    Parameter("x6", ((-2.0, 2.0),), unit=""),
    Parameter("x7", ((-2.0, 2.0),), unit=""),
    Parameter("x8", ((-2.0, 2.0),), unit=""),
    Parameter("x9", ((-2.0, 2.0),), unit=""),
)


def get_parameters() -> tuple[Parameter, ...]:
    return tuple(PARAMETERS)
