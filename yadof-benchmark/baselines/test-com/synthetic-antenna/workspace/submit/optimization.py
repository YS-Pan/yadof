"""Explicit conditional-INR GPSAF program for the synthetic baseline."""

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
        "program": "test-com-synthetic-antenna-conditional-inr-gpsaf",
        "version": 1,
        "alpha": 3,
        "beta": 3,
        "gamma": 0.5,
        "exploration_fraction": 0.15,
        "device": "cuda",
        "epochs": 32,
        "ensemble_size": 3,
    },
    "capabilities": ("real-evaluation", "conditional-inr", "gpsaf"),
}


def optimization_program(context):
    search = by_objective_count(single=pymoo_ga(), multi=pymoo_nsga3())
    surrogate = conditional_inr(
        device="cuda",
        epochs=32,
        ensemble_size=3,
        train_query_sample_count=8192,
        bootstrap_members=True,
        bootstrap_fraction=1.0,
    )
    settings = gpsaf_settings(
        alpha=3,
        beta=3,
        exploration_fraction=0.15,
    )
    with context.run_scope() as run:
        for generation_index in run.generations():
            with run.generation(generation_index) as step:
                training = surrogate.training_data(
                    step.evidence_dataset(), step.cost_table()
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
                step.commit(
                    step.result(
                        population=selected.population,
                        costs=evaluation.costs,
                        source=selected.source,
                        surrogate_used=selected.surrogate_used,
                        diagnostics=diagnostics,
                    )
                )
