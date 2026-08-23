"""Real-evaluation-only benchmark strategy."""

from yadof.optimize import (
    by_objective_count,
    pymoo_ga,
    pymoo_nsga3,
    real_search,
)


def build_optimization():
    return real_search(
        search=by_objective_count(
            single=pymoo_ga(),
            multi=pymoo_nsga3(),
        )
    )

