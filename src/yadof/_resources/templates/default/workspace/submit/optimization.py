"""Explicit optimization program for the generic starter workspace."""

from yadof.evaluate_manager import start_evaluation
from yadof.optimize import (
    by_objective_count,
    finish_explicit_surrogate_training,
    gpsaf_settings,
    pymoo_ga,
    pymoo_nsga3,
    select_gpsaf_generation,
    start_explicit_surrogate_training,
)
from yadof.surrogate import conditional_inr


YADOF_OPTIMIZATION_PROGRAM = {
    "api": "yadof.optimize.program/v1",
    "entry": "optimization_program",
    "helpers": (),
    "identity": {
        "program": "starter-conditional-inr-gpsaf",
        "version": 1,
        "alpha": 3,
        "beta": 3,
        "gamma": 0.5,
        "exploration_fraction": 0.10,
    },
    "capabilities": ("real-evaluation", "conditional-inr", "gpsaf"),
}


def optimization_program(context):
    search = by_objective_count(single=pymoo_ga(), multi=pymoo_nsga3())
    surrogate = conditional_inr()
    settings = gpsaf_settings()
    training_enabled = settings.alpha > 1 or settings.beta > 0
    with context.run_scope() as run:
        for generation_index in run.generations():
            with run.generation(generation_index) as step:
                training = surrogate.training_data(
                    step.evidence_dataset(),
                    step.cost_table(),
                )
                selected = select_gpsaf_generation(
                    step.context,
                    search=search,
                    surrogate=surrogate,
                    settings=settings,
                    training_data=training,
                )
                handle = start_evaluation(
                    step.prepare_evaluation(selected.population)
                )
                diagnostics = dict(selected.diagnostics)
                diagnostics.update(
                    start_explicit_surrogate_training(
                        surrogate,
                        step.context,
                        training,
                        enabled=training_enabled,
                    )
                )
                try:
                    evaluation = handle.wait()
                finally:
                    try:
                        handle.close()
                    finally:
                        diagnostics.update(
                            finish_explicit_surrogate_training(
                                surrogate,
                                step.context,
                                enabled=training_enabled,
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
