"""Audited real-simulation oracle with positional alpha and cluster PKT beta."""
from yadof_benchmark.perfect_program import run_program

YADOF_OPTIMIZATION_PROGRAM = {
    "api": "yadof.optimize.program/v1", "entry": "optimization_program", "helpers": (),
    "identity": {"program": "top10-perfect-gpsaf", "metric": "formal-cumulative-top10",
                 "oracle": "real-kernel-cost-items-explicit-failures",
                 "gpsaf": {"alpha": 3, "beta": 3, "gamma": 0.5, "exploration_fraction": 0.1},
                 "search": {"crossover_probability": 0.85, "mutation_probability": 0.35,
                            "crossover_eta": 10.0, "mutation_eta": 10.0,
                            "mutated_dimensions_per_individual": 7, "refill_attempts": 8,
                            "reference_direction_method": "das-dennis", "reference_direction_partitions": None}},
    "capabilities": ("real-evaluation", "benchmark-top10", "gpsaf", "perfect-simulation-oracle"),
}


def optimization_program(context):
    run_program(context, perfect=True)
