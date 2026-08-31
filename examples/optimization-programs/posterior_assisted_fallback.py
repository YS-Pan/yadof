"""Blocked posterior-assisted selection with explicit full-real fallback."""

import math

from yadof.evaluate_manager import start_evaluation
from yadof.optimize import (
    finish_explicit_surrogate_training,
    posterior_assisted_selector,
    pymoo_nsga3,
    qnehvi,
    start_explicit_surrogate_training,
)
from yadof.surrogate import conditional_inr_posterior


YADOF_OPTIMIZATION_PROGRAM = {
    "api": "yadof.optimize.program/v1",
    "entry": "optimization_program",
    "helpers": (),
    "identity": {
        "program": "example-posterior-assisted-blocked-fallback",
        "version": 1,
        "exploration_fraction": 0.25,
        "posterior_draws": 3,
        "candidate_pool_multiplier": 4,
        "readiness_policy": "typed-fail-closed-v1",
    },
    "capabilities": (
        "real-evaluation",
        "conditional-inr-posterior",
        "qnehvi-blocked",
        "full-real-fallback",
    ),
}


def optimization_program(context):
    search = pymoo_nsga3()
    surrogate = conditional_inr_posterior()
    exploration_fraction = 0.25
    with context.run_scope() as run:
        for generation_index in run.generations():
            with run.generation(generation_index) as step:
                population_size = step.context.population_size
                exploration_count = min(
                    population_size - 1,
                    max(1, int(math.ceil(population_size * exploration_fraction))),
                )
                selector = posterior_assisted_selector(
                    search=search,
                    surrogate=surrogate,
                    acquisition=qnehvi(
                        batch_size=population_size - exploration_count,
                        greedy_restarts=2,
                    ),
                    candidate_pool_size=max(population_size, population_size * 4),
                    posterior_draws=3,
                    candidate_chunk_size=64,
                    exploration_fraction=exploration_fraction,
                )
                training = surrogate.training_data(
                    step.evidence_dataset(),
                    step.cost_table(),
                )
                selected = selector.select_generation(
                    step.context,
                    training_data=training,
                )
                evaluation_handle = start_evaluation(
                    step.prepare_evaluation(selected.population)
                )
                diagnostics = dict(selected.diagnostics)
                diagnostics.update(
                    start_explicit_surrogate_training(
                        surrogate.component,
                        step.context,
                        training,
                    )
                )
                try:
                    evaluation = evaluation_handle.wait()
                finally:
                    try:
                        evaluation_handle.close()
                    finally:
                        diagnostics.update(
                            finish_explicit_surrogate_training(
                                surrogate.component,
                                step.context,
                            )
                        )
                step.commit(
                    step.result(
                        population=selected.population,
                        costs=evaluation.costs,
                        source=selected.source,
                        surrogate_used=selected.surrogate_used,
                        diagnostics=diagnostics,
                    )
                )
