"""Parameter definitions and normalization helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


RangeElement = float | tuple[float, float]


def _coerce_range_element(value: object) -> RangeElement:
    if isinstance(value, (tuple, list)):
        if len(value) != 2:
            raise ValueError(f"range tuple must have length 2, got {value!r}")
        return (float(value[0]), float(value[1]))
    return float(value)


@dataclass(frozen=True)
class Parameter:
    """One optimization parameter.

    ``ranges`` may contain continuous intervals ``(lo, hi)`` or discrete
    allowed values. Normalization maps each range element to an equal-width
    segment of ``[0, 1]``.
    """

    name: str
    ranges: tuple[RangeElement, ...]
    unit: str = ""

    def __init__(self, name: str, ranges: Iterable[object], unit: str = "") -> None:
        coerced = tuple(_coerce_range_element(item) for item in ranges)
        if not coerced:
            raise ValueError(f"parameter {name!r} must define at least one range")
        object.__setattr__(self, "name", str(name))
        object.__setattr__(self, "ranges", coerced)
        object.__setattr__(self, "unit", str(unit))

    def denormalize(self, normalized_value: float, *, clip: bool = True) -> float:
        x = float(normalized_value)
        if clip:
            x = min(1.0, max(0.0, x))

        count = len(self.ranges)
        scaled = x * count
        index = min(count - 1, int(scaled))
        position = 1.0 if scaled >= count else scaled - index

        range_item = self.ranges[index]
        if isinstance(range_item, tuple):
            lo, hi = range_item
            return float(lo + (hi - lo) * position)
        return float(range_item)

    def normalize(self, raw_value: float, *, clip: bool = True) -> float:
        value = float(raw_value)
        count = len(self.ranges)
        candidates: list[tuple[float, float]] = []

        for index, range_item in enumerate(self.ranges):
            segment_start = index / count
            segment_width = 1.0 / count
            if isinstance(range_item, tuple):
                lo, hi = range_item
                if hi == lo:
                    position = 0.0
                    distance = abs(value - lo)
                else:
                    position = (value - lo) / (hi - lo)
                    clamped_position = min(1.0, max(0.0, position))
                    nearest = lo + (hi - lo) * clamped_position
                    distance = abs(value - nearest)
                    position = clamped_position if clip else position
                candidates.append((distance, segment_start + segment_width * position))
            else:
                candidates.append((abs(value - range_item), segment_start + 0.5 * segment_width))

        _distance, normalized = min(candidates, key=lambda item: item[0])
        if clip:
            normalized = min(1.0, max(0.0, normalized))
        return float(normalized)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "ranges": [list(item) if isinstance(item, tuple) else item for item in self.ranges],
            "unit": self.unit,
        }


def normalize_values(parameters: Iterable[Parameter], raw_values: Iterable[float]) -> tuple[float, ...]:
    params = tuple(parameters)
    values = tuple(float(value) for value in raw_values)
    if len(params) != len(values):
        raise ValueError(f"expected {len(params)} values, got {len(values)}")
    return tuple(param.normalize(value) for param, value in zip(params, values))


def denormalize_values(parameters: Iterable[Parameter], normalized_values: Iterable[float]) -> tuple[float, ...]:
    params = tuple(parameters)
    values = tuple(float(value) for value in normalized_values)
    if len(params) != len(values):
        raise ValueError(f"expected {len(params)} values, got {len(values)}")
    return tuple(param.denormalize(value) for param, value in zip(params, values))

