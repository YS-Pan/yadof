"""Complete optimization strategy for the generic starter workspace."""

from yadof.optimize import by_objective_count, gpsaf, pymoo_ga, pymoo_nsga3
from yadof.surrogate import conditional_inr


def build_optimization():
    search = by_objective_count(
        single=pymoo_ga(),
        multi=pymoo_nsga3(),
    )
    return gpsaf(search=search, surrogate=conditional_inr())

