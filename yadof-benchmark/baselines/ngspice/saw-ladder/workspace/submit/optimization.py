"""Explicit conditional-INR GPSAF program for the ngspice baseline."""

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
        "program": "ngspice-saw-ladder-conditional-inr-gpsaf",
        "version": 1,
        "alpha": 1,
        "beta": 0,
        "gamma": 0.5,
        "exploration_fraction": 0.10,
        "epochs": 64,
        "ensemble_size": 3,
    },
    "capabilities": ("real-evaluation", "conditional-inr", "gpsaf"),
}


def optimization_program(context):
    search = by_objective_count(single=pymoo_ga(), multi=pymoo_nsga3())
    surrogate = conditional_inr(
        epochs=64,
        ensemble_size=3,
        train_query_sample_count=8192,
        bootstrap_members=True,
        bootstrap_fraction=1.0,
    )
    settings = gpsaf_settings(alpha=1, beta=0)
    training_enabled = settings.alpha > 1 or settings.beta > 0
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
