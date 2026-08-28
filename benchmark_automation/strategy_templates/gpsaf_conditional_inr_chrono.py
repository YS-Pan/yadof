"""Measured GPSAF strategy for the Chrono conditional-INR case."""

from yadof.optimize import by_objective_count, gpsaf, pymoo_ga, pymoo_nsga3
from yadof.surrogate import conditional_inr


def build_optimization():
    return gpsaf(
        search=by_objective_count(single=pymoo_ga(), multi=pymoo_nsga3()),
        surrogate=conditional_inr(),
        alpha=3,
        beta=3,
        exploration_fraction=0.15,
    )
