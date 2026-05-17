"""Default task parameters for the harder synthetic test workflow."""

from __future__ import annotations

try:
    from .parameters_constraints_class import Parameter
except ImportError:  # Allows copied job folders to run workflow.py directly.
    from parameters_constraints_class import Parameter


PARAMETERS = tuple(Parameter(f"x{index}", ((0.0, 1.0),), unit="") for index in range(20))


def get_parameters() -> tuple[Parameter, ...]:
    return tuple(PARAMETERS)
