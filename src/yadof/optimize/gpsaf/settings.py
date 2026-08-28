"""Immutable GPSAF settings owned by the strategy component."""

from __future__ import annotations

from dataclasses import dataclass

from ..._component_settings import integer, real


@dataclass(frozen=True, slots=True)
class GPSAFSettings:
    alpha: int
    beta: int
    gamma: float
    exploration_fraction: float


def create_settings(
    *,
    alpha: int,
    beta: int,
    gamma: float,
    exploration_fraction: float,
) -> GPSAFSettings:
    factory = "gpsaf"
    return GPSAFSettings(
        alpha=integer(factory, "alpha", alpha, minimum=0),
        beta=integer(factory, "beta", beta, minimum=0),
        gamma=real(factory, "gamma", gamma, minimum=0.0, maximum=1.0),
        exploration_fraction=real(
            factory,
            "exploration_fraction",
            exploration_fraction,
            minimum=0.0,
            maximum=1.0,
        ),
    )


__all__ = ["GPSAFSettings", "create_settings"]
