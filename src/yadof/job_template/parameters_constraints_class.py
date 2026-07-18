"""Parameter definitions and normalization helpers."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable


RangeElement = float | tuple[float, float]


def _coerce_range_element(value: object) -> RangeElement:
    if isinstance(value, (tuple, list)):
        if len(value) != 2:
            raise ValueError(f"range tuple must have length 2, got {value!r}")
        item = (float(value[0]), float(value[1]))
        if not all(math.isfinite(number) for number in item):
            raise ValueError(f"range values must be finite, got {value!r}")
        return item
    item = float(value)
    if not math.isfinite(item):
        raise ValueError(f"range value must be finite, got {value!r}")
    return item


@dataclass(init=False)
class Parameter:
    """One continuous, discrete, or mixed optimization parameter."""

    name: str
    ranges: tuple[RangeElement, ...]
    value: float
    normalized_value: float
    unit: str = ""

    def __init__(
        self,
        name: str,
        ranges: Iterable[object],
        *,
        value: float = float("nan"),
        normalized_value: float = float("nan"),
        unit: str = "",
    ) -> None:
        coerced = tuple(_coerce_range_element(item) for item in ranges)
        if not coerced:
            raise ValueError(f"parameter {name!r} must define at least one range")
        assigned_value = float(value)
        assigned_normalized_value = float(normalized_value)
        if math.isinf(assigned_value):
            raise ValueError(f"parameter {name!r} value must be finite or NaN")
        if math.isinf(assigned_normalized_value):
            raise ValueError(f"parameter {name!r} normalized_value must be finite or NaN")
        self.name = str(name)
        self.ranges = coerced
        self.value = assigned_value
        self.normalized_value = assigned_normalized_value
        self.unit = str(unit)

    def denormalize(
        self,
        normalized_value: float | None = None,
        *,
        clip: bool = True,
        update: bool = True,
    ) -> float:
        x = self.normalized_value if normalized_value is None else float(normalized_value)
        if not math.isfinite(x):
            raise ValueError(f"parameter {self.name!r} normalized_value must be finite")
        if clip:
            x = min(1.0, max(0.0, x))

        count = len(self.ranges)
        scaled = x * count
        index = min(count - 1, int(scaled))
        position = 1.0 if scaled >= count else scaled - index
        range_item = self.ranges[index]
        if isinstance(range_item, tuple):
            lo, hi = range_item
            raw_value = float(lo + (hi - lo) * position)
        else:
            raw_value = float(range_item)
        if update:
            self.normalized_value = x
            self.value = raw_value
        return raw_value

    def normalize(self, raw_value: float, *, clip: bool = True) -> float:
        value = float(raw_value)
        if not math.isfinite(value):
            raise ValueError(f"parameter {self.name!r} value must be finite")
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
                    clamped = min(1.0, max(0.0, position))
                    nearest = lo + (hi - lo) * clamped
                    distance = abs(value - nearest)
                    position = clamped if clip else position
                candidates.append((distance, segment_start + segment_width * position))
            else:
                candidates.append(
                    (abs(value - range_item), segment_start + 0.5 * segment_width)
                )
        _distance, normalized = min(candidates, key=lambda item: item[0])
        if clip:
            normalized = min(1.0, max(0.0, normalized))
        return float(normalized)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "ranges": [
                list(item) if isinstance(item, tuple) else item for item in self.ranges
            ],
            "unit": self.unit,
        }


def normalize_values(
    parameters: Iterable[Parameter], raw_values: Iterable[float]
) -> tuple[float, ...]:
    params = tuple(parameters)
    values = tuple(float(value) for value in raw_values)
    if len(params) != len(values):
        raise ValueError(f"expected {len(params)} values, got {len(values)}")
    return tuple(param.normalize(value) for param, value in zip(params, values))


def denormalize_values(
    parameters: Iterable[Parameter], normalized_values: Iterable[float]
) -> tuple[float, ...]:
    params = tuple(parameters)
    values = tuple(float(value) for value in normalized_values)
    if len(params) != len(values):
        raise ValueError(f"expected {len(params)} values, got {len(values)}")
    return tuple(
        param.denormalize(value, update=False) for param, value in zip(params, values)
    )


__all__ = ["Parameter", "RangeElement", "denormalize_values", "normalize_values"]
