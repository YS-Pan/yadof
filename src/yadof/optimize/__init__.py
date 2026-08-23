from . import gpsaf as _gpsaf_package
from . import pymoo as _pymoo_package
from .api import (
    AllInfiniteGenerationError,
    run_generations,
    run_one_generation,
)
from .components import (
    GPSAFStrategy,
    ObjectiveCountSearch,
    PymooSearch,
    RealSearchStrategy,
    by_objective_count,
    gpsaf,
    pymoo_ga,
    pymoo_nsga3,
    real_search,
)
from .strategy import OptimizationResult, OptimizationStrategy

# The private ``gpsaf`` package is loaded above before this public factory name is
# rebound. Later private-module imports therefore cannot replace the public callable
# on ``yadof.optimize``.

__all__ = [
    "AllInfiniteGenerationError",
    "GPSAFStrategy",
    "ObjectiveCountSearch",
    "OptimizationResult",
    "OptimizationStrategy",
    "PymooSearch",
    "RealSearchStrategy",
    "by_objective_count",
    "gpsaf",
    "pymoo_ga",
    "pymoo_nsga3",
    "real_search",
    "run_generations",
    "run_one_generation",
]
