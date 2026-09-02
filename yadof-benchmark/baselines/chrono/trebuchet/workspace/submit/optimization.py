"""Explicit conditional-INR GPSAF program for the Chrono baseline."""

from yadof.evaluate_manager import start_evaluation
from yadof.optimize import (
    by_objective_count,
    finish_explicit_surrogate_training,
    gpsaf_settings,
    pymoo_ga,
    pymoo_nsga3,
    select_gpsaf_generation,
    GPSAFErrorState,
    initialize_gpsaf_error,
    start_explicit_surrogate_training,
)
from yadof.surrogate import conditional_inr


YADOF_OPTIMIZATION_PROGRAM = {
    "api": "yadof.optimize.program/v1",
    "entry": "optimization_program",
    "helpers": (),
    "identity": {
        "program": "chrono-trebuchet-conditional-inr-gpsaf",
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
    settings = gpsaf_settings(alpha=3, beta=3)
    error_state = GPSAFErrorState()
    with context.run_scope() as run:
        for generation_index in run.generations():
            with run.generation(generation_index) as step:
                training = surrogate.training_data(
                    step.evidence_dataset(), step.cost_table()
                )
                initialize_gpsaf_error(surrogate, step.context, training, error_state)
                selected = select_gpsaf_generation(
                    step.context,
                    search=search,
                    surrogate=surrogate,
                    settings=settings,
                    training_data=training,
                    error_state=error_state,
                )
                handle = start_evaluation(
                    step.prepare_evaluation(selected.population)
                )
                diagnostics = dict(selected.diagnostics)
                diagnostics.update(
                    start_explicit_surrogate_training(
                        surrogate, step.context, training
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
                                surrogate, step.context
                            )
                        )
                error_state.observe(selected, evaluation.costs)
                diagnostics.update(error_state.diagnostics())
                step.commit(
                    step.result(
                        population=selected.population,
                        costs=evaluation.costs,
                        source=selected.source,
                        surrogate_used=selected.surrogate_used,
                        diagnostics=diagnostics,
                    )
                )
