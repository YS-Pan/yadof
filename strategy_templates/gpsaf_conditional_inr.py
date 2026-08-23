"""GPSAF benchmark strategy with conditional-INR rawData prediction."""

from yadof.optimize import by_objective_count, gpsaf, pymoo_ga, pymoo_nsga3
from yadof.surrogate import conditional_inr


def build_optimization():
    return gpsaf(
        search=by_objective_count(
            single=pymoo_ga(),
            multi=pymoo_nsga3(),
        ),
        surrogate=conditional_inr(),
    )

