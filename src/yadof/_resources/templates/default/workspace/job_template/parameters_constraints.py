"""Generic starter parameter definition."""

from __future__ import annotations

from yadof.job_template import Parameter


PARAMETERS = (
    Parameter("input_value", ((-1.0, 1.0),), unit=""),
)

CONSTRAINTS = ()


def get_parameters() -> tuple[Parameter, ...]:
    return tuple(PARAMETERS)
