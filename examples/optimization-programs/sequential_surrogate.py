"""Sequential PCA/SVD + GPSAF program with current-generation training."""

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
from yadof.surrogate import pca_svd


YADOF_OPTIMIZATION_PROGRAM = {
    "api": "yadof.optimize.program/v1",
    "entry": "optimization_program",
    "helpers": (),
    "identity": {
        "program": "example-sequential-pca-svd-gpsaf",
        "version": 1,
        "alpha": 3,
        "beta": 3,
        "gamma": 0.5,
        "exploration_fraction": 0.10,
    },
    "capabilities": ("real-evaluation", "pca-svd", "gpsaf"),
}


def optimization_program(context):
    search = by_objective_count(single=pymoo_ga(), multi=pymoo_nsga3())
    surrogate = pca_svd(rank=8, device="cpu", seed=101)
    settings = gpsaf_settings()
    training_enabled = settings.alpha > 1 or settings.beta > 0
    with context.run_scope() as run:
        for generation_index in run.generations():
            with run.generation(generation_index) as step:
                prior_training = surrogate.training_data(
                    step.evidence_dataset(),
                    step.cost_table(),
                )
                selected = select_gpsaf_generation(
                    step.context,
                    search=search,
                    surrogate=surrogate,
                    settings=settings,
                    training_data=prior_training,
                )
                handle = start_evaluation(
                    step.prepare_evaluation(selected.population)
                )
                try:
                    evaluation = handle.wait()
                finally:
                    handle.close()
                current_training = surrogate.training_data(
                    step.evidence_dataset(),
                    step.cost_table(),
                )
                diagnostics = dict(selected.diagnostics)
                diagnostics.update(
                    start_explicit_surrogate_training(
                        surrogate,
                        step.context,
                        current_training,
                        enabled=training_enabled,
                    )
                )
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
