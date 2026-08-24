"""Real-evaluation-only NSGA-III benchmark strategy."""

from yadof.optimize import pymoo_nsga3, real_search


def build_optimization():
    return real_search(search=pymoo_nsga3())

