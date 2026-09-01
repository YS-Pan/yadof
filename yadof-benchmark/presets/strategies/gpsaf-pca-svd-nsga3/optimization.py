"""Stage 8 explicit PCA/SVD + GPSAF cutover acceptance program."""

from yadof.evaluate_manager import start_evaluation
from yadof.optimize import (
    finish_explicit_surrogate_training,
    gpsaf_settings,
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
        "program": "stage8-explicit-pca-svd-gpsaf-nsga3",
        "version": 1,
        "search": {
            "algorithm": "pymoo-nsga3",
            "crossover_probability": 0.85,
            "mutation_probability": 0.35,
            "crossover_eta": 10.0,
            "mutation_eta": 10.0,
            "mutated_dimensions_per_individual": 7,
            "refill_attempts": 8,
            "reference_direction_method": "das-dennis",
            "reference_direction_partitions": None,
        },
        "surrogate": {
            "model": "pca-svd",
            "decomposition": "pca",
            "rank": 16,
            "predictor": "ridge",
            "ridge_alpha": 1e-6,
            "field_mode": "per-field",
            "rank_policy": "clamp",
            "solver": "torch-lowrank",
            "dtype": "float32",
            "device": "cpu",
            "power_iterations": 3,
            "seed": 20260828,
            "fit_intercept": True,
            "constant_atol": 1e-12,
        },
        "gpsaf": {
            "alpha": 3,
            "beta": 3,
            "gamma": 0.5,
            "exploration_fraction": 0.1,
        },
        "ordering": "start-evaluation-start-training-wait-close-commit-v1",
    },
    "capabilities": (
        "real-evaluation",
        "pca-svd",
        "gpsaf",
        "typed-deterministic-surrogate",
    ),
}


def optimization_program(context):
    search = pymoo_nsga3(
        crossover_probability=0.85,
        mutation_probability=0.35,
        crossover_eta=10.0,
        mutation_eta=10.0,
        mutated_dimensions_per_individual=7,
        refill_attempts=8,
        reference_direction_method="das-dennis",
        reference_direction_partitions=None,
    )
    surrogate = pca_svd(
        decomposition="pca",
        rank=16,
        predictor="ridge",
        ridge_alpha=1e-6,
        field_mode="per-field",
        rank_policy="clamp",
        solver="torch-lowrank",
        dtype="float32",
        device="cpu",
        power_iterations=3,
        seed=20260828,
        fit_intercept=True,
        constant_atol=1e-12,
    )
    settings = gpsaf_settings(
        alpha=3,
        beta=3,
        gamma=0.5,
        exploration_fraction=0.1,
    )
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
                evaluation_handle = start_evaluation(
                    step.prepare_evaluation(selected.population)
                )
                diagnostics = dict(selected.diagnostics)
                diagnostics.update(
                    start_explicit_surrogate_training(
                        surrogate,
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
                                surrogate,
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
