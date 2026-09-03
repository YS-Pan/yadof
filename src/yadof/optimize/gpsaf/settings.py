"""Immutable GPSAF selection settings owned by the workspace program."""

from __future__ import annotations

from dataclasses import dataclass

from ..._component_settings import integer, real, text


@dataclass(frozen=True, slots=True)
class GPSAFSettings:
    alpha: int
    beta: int
    gamma: float
    exploration_fraction: float
    infill_selection: str = "cluster"


def create_settings(
    *,
    alpha: int,
    beta: int,
    gamma: float,
    exploration_fraction: float,
    infill_selection: str = "cluster",
) -> GPSAFSettings:
    factory = "gpsaf_settings"
    return GPSAFSettings(
        alpha=integer(factory, "alpha", alpha, minimum=0),
        beta=integer(factory, "beta", beta, minimum=0),
        gamma=real(factory, "gamma", gamma, minimum=0.0),
        exploration_fraction=real(
            factory,
            "exploration_fraction",
            exploration_fraction,
            minimum=0.0,
            maximum=1.0,
        ),
        infill_selection=text(
            factory, "infill_selection", infill_selection,
            choices=("cluster", "hypervolume"),
        ),
    )


__all__ = ["GPSAFSettings", "create_settings"]
