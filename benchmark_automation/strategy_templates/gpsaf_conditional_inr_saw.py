"""Measured GPSAF strategy for the SAW conditional-INR case."""

from yadof.optimize import by_objective_count, gpsaf, pymoo_ga, pymoo_nsga3
from yadof.surrogate import conditional_inr


def build_optimization():
    return gpsaf(
        search=by_objective_count(single=pymoo_ga(), multi=pymoo_nsga3()),
        surrogate=conditional_inr(
            epochs=64,
            ensemble_size=3,
            train_query_sample_count=8192,
            bootstrap_members=True,
            bootstrap_fraction=1.0,
        ),
        alpha=3,
        beta=3,
        exploration_fraction=0.15,
    )
