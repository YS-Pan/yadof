"""Deterministic finite-ensemble draw selection."""

from __future__ import annotations

import numpy as np


def seeded_member_indices(member_count: int, draw_count: int, seed: int) -> tuple[int, ...]:
    if int(member_count) <= 0:
        raise ValueError("member_count must be positive")
    if int(draw_count) <= 0:
        raise ValueError("draw_count must be positive")
    rng = np.random.default_rng(int(seed) % (2**64))
    selected: list[int] = []
    while len(selected) < int(draw_count):
        selected.extend(int(value) for value in rng.permutation(int(member_count)))
    return tuple(selected[: int(draw_count)])
