"""Small standard-library validators for component-owned immutable settings."""

from __future__ import annotations

import math


def integer(factory: str, field: str, value: object, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(
            f"{factory}(): {field}={value!r} must be an integer >= {minimum}"
        )
    if value < minimum:
        raise ValueError(
            f"{factory}(): {field}={value!r} must be >= {minimum}"
        )
    return value


def real(
    factory: str,
    field: str,
    value: object,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    minimum_open: bool = False,
    maximum_open: bool = False,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{factory}(): {field}={value!r} must be a real number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{factory}(): {field}={value!r} must be finite")
    if minimum is not None and (
        result < minimum or (minimum_open and result == minimum)
    ):
        relation = ">" if minimum_open else ">="
        raise ValueError(
            f"{factory}(): {field}={value!r} must be {relation} {minimum}"
        )
    if maximum is not None and (
        result > maximum or (maximum_open and result == maximum)
    ):
        relation = "<" if maximum_open else "<="
        raise ValueError(
            f"{factory}(): {field}={value!r} must be {relation} {maximum}"
        )
    return result


def boolean(factory: str, field: str, value: object) -> bool:
    if type(value) is not bool:
        raise TypeError(f"{factory}(): {field}={value!r} must be bool")
    return value


def text(
    factory: str,
    field: str,
    value: object,
    *,
    choices: tuple[str, ...] = (),
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{factory}(): {field}={value!r} must be a non-empty string")
    result = value.strip().lower()
    if choices and result not in choices:
        rendered = ", ".join(repr(choice) for choice in choices)
        raise ValueError(
            f"{factory}(): {field}={value!r} must be one of {rendered}"
        )
    return result


__all__ = ["boolean", "integer", "real", "text"]
