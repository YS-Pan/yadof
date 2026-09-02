"""Full real NSGA-III reference; settings live in the installed experiment program."""
from yadof_benchmark.perfect_program import run_program

YADOF_OPTIMIZATION_PROGRAM = {
    "api": "yadof.optimize.program/v1", "entry": "optimization_program", "helpers": (),
    "identity": {"program": "top10-real-nsga3", "metric": "formal-cumulative-top10",
                 "search": {"crossover_probability": 0.85, "mutation_probability": 0.35,
                            "crossover_eta": 10.0, "mutation_eta": 10.0,
                            "mutated_dimensions_per_individual": 7, "refill_attempts": 8,
                            "reference_direction_method": "das-dennis", "reference_direction_partitions": None}},
    "capabilities": ("real-evaluation", "benchmark-top10"),
}


def optimization_program(context):
    run_program(context, perfect=False)
