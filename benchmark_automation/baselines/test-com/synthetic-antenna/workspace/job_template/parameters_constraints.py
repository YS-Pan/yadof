"""Twenty normalized synthetic design variables used by ``test_com``."""

from __future__ import annotations

from yadof.job_template import Parameter


PARAMETERS = tuple(
    Parameter(f"x{index}", ((0.0, 1.0),), unit="")
    for index in range(20)
)
CONSTRAINTS = ()


def get_parameters() -> tuple[Parameter, ...]:
    return tuple(PARAMETERS)

