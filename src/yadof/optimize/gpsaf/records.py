from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

from ..strategy import HistoryRecord


@dataclass(frozen=True)
class CandidateRecord:
    x: tuple[float, ...]
    origin: str
    individual: object | None = None
    pred_costs: tuple[float, ...] = ()


def clip01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def clean_costs(costs: Sequence[float]) -> tuple[float, ...]:
    out = []
    for value in costs:
        number = float(value)
        out.append(number if math.isfinite(number) else float("inf"))
    return tuple(out)


def total_cost(costs: Sequence[float]) -> float:
    values = clean_costs(costs)
    return float(sum(values)) if values else float("inf")


def key(x: Sequence[float], decimals: int = 10) -> tuple[float, ...]:
    return tuple(round(float(value), decimals) for value in x)


def history_keys(
    history: Sequence[HistoryRecord], decimals: int = 10
) -> set[tuple[float, ...]]:
    return {key(record.x, decimals) for record in history if record.x}
