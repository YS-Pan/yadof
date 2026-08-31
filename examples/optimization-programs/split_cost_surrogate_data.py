"""GPSAF program with full cost history and a deliberate surrogate subset."""

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
from yadof.surrogate import materialize_training_data, pca_svd


YADOF_OPTIMIZATION_PROGRAM = {
    "api": "yadof.optimize.program/v1",
    "entry": "optimization_program",
    "helpers": (),
    "identity": {
        "program": "example-split-cost-surrogate-data",
        "version": 1,
        "surrogate_transform": "alternating-successful-rows-v1",
        "alpha": 3,
        "beta": 3,
        "gamma": 0.5,
        "exploration_fraction": 0.10,
    },
    "capabilities": (
        "real-evaluation",
        "pca-svd",
        "gpsaf",
        "explicit-training-data-view",
    ),
}


def surrogate_training_view(step):
    dataset = step.evidence_dataset()
    costs = step.cost_table()
    all_successful = materialize_training_data(dataset, costs)
    return materialize_training_data(
        dataset,
        costs,
        row_ids=all_successful.row_ids[::2],
        transform_id="alternating-successful-rows-v1",
    )


def optimization_program(context):
    search = by_objective_count(single=pymoo_ga(), multi=pymoo_nsga3())
    surrogate = pca_svd(rank=8, device="cpu", seed=101)
    settings = gpsaf_settings()
    training_enabled = settings.alpha > 1 or settings.beta > 0
    with context.run_scope() as run:
        for generation_index in run.generations():
            with run.generation(generation_index) as step:
                training = surrogate_training_view(step)
                selected = select_gpsaf_generation(
                    step.context,
                    search=search,
                    surrogate=surrogate,
                    settings=settings,
                    training_data=training,
                )
                evaluation_handle = start_evaluation(
                    step.prepare_evaluation(selected.population)
                )
                diagnostics = dict(selected.diagnostics)
                diagnostics.update(
                    {
                        "optimizer_history_count": len(step.context.history),
                        "surrogate_training_row_count": training.sample_count,
                        "surrogate_training_transform_id": training.transform_id,
                    }
                )
                diagnostics.update(
                    start_explicit_surrogate_training(
                        surrogate,
                        step.context,
                        training,
                        enabled=training_enabled,
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
