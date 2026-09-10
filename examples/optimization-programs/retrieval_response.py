"""Own-prior fitting before each GPSAF selection; all outcomes use real evaluation."""
from yadof.evaluate_manager import start_evaluation
from yadof.optimize import (GPSAFErrorState, by_objective_count, gpsaf_settings,
                           initialize_gpsaf_error, pymoo_ga, pymoo_nsga3, select_gpsaf_generation)
from yadof.surrogate import retrieval_response

YADOF_OPTIMIZATION_PROGRAM = {
    "api": "yadof.optimize.program/v1", "entry": "optimization_program", "helpers": (),
    "identity": {"program": "retrieval-response-prior-fit-gpsaf", "version": 1,
                 "schedule": "all-own-prior-before-selection", "model": "retrieval_response",
                 "alpha": 3, "beta": 3, "gamma": 0.5, "exploration_fraction": 0.1},
    "capabilities": ("real-evaluation", "typed-deterministic-surrogate", "gpsaf"),
}

def optimization_program(context):
    search = by_objective_count(single=pymoo_ga(), multi=pymoo_nsga3())
    surrogate = retrieval_response()
    settings = gpsaf_settings(alpha=3, beta=3, gamma=0.5, exploration_fraction=0.1,
                              infill_selection="hypervolume")
    errors = GPSAFErrorState()
    training = None
    with context.run_scope() as run:
        for generation in run.generations():
            with run.generation(generation) as step:
                # Retain the previous immutable view until materialization finishes,
                # allowing the campaign's weak rawData index to reuse live arrays.
                training = surrogate.training_data(step.evidence_dataset(), step.cost_table())
                if training.sample_count >= surrogate.settings.minimum_training_samples:
                    surrogate.fit(context.workspace, training, generation_index=generation,
                                  session=step.context.session, snapshot=step.context.snapshot)
                initialize_gpsaf_error(surrogate, step.context, training, errors)
                selected = select_gpsaf_generation(step.context, search=search, surrogate=surrogate,
                    settings=settings, training_data=training, error_state=errors)
                with start_evaluation(step.prepare_evaluation(selected.population)) as handle:
                    evaluation = handle.wait()
                errors.observe(selected, evaluation.costs)
                step.commit(step.result(population=selected.population, costs=evaluation.costs,
                    source=selected.source, surrogate_used=selected.surrogate_used,
                    diagnostics={**selected.diagnostics, **errors.diagnostics()}))
