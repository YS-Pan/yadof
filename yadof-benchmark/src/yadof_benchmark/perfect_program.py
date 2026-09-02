"""Explicit programs shared by the two packaged perfect-experiment strategies."""
from yadof.evaluate_manager import start_evaluation
from yadof.surrogate import SurrogateContractError
from yadof.optimize import GPSAFErrorState, full_real_search, gpsaf_settings, pymoo_nsga3, select_gpsaf_generation, initialize_gpsaf_error
from .perfect_oracle import PerfectSimulationOracle
from .perfect_protocol import record_generation
from .runtime_freeze import verify_runtime


def run_program(context, *, perfect):
    search = pymoo_nsga3(crossover_probability=0.85, mutation_probability=0.35,
                        crossover_eta=10.0, mutation_eta=10.0,
                        mutated_dimensions_per_individual=7, refill_attempts=8,
                        reference_direction_method="das-dennis", reference_direction_partitions=None)
    surrogate = PerfectSimulationOracle() if perfect else None
    errors = GPSAFErrorState()
    settings = gpsaf_settings(alpha=3, beta=3, gamma=0.5, exploration_fraction=0.1)
    with context.run_scope() as run:
        for generation in run.generations():
            with run.generation(generation) as step:
                verify_runtime(step.context.config.workspace.root)
                if perfect:
                    training = surrogate.training_data(step.evidence_dataset(), step.cost_table())
                    initialize_gpsaf_error(surrogate, step.context, training, errors)
                    selected = select_gpsaf_generation(step.context, search=search, surrogate=surrogate,
                        settings=settings, training_data=training, error_state=errors)
                    if step.context.history and not selected.surrogate_used:
                        raise SurrogateContractError(
                            "perfect oracle did not enter GPSAF selection: " +
                            str(selected.diagnostics.get("surrogate_error", "unknown readiness failure")))
                else:
                    selected = full_real_search(step.context, search)
                verify_runtime(step.context.config.workspace.root)
                with start_evaluation(step.prepare_evaluation(selected.population)) as handle:
                    evaluated = handle.wait()
                verify_runtime(step.context.config.workspace.root)
                diagnostics = dict(selected.diagnostics)
                if perfect:
                    surrogate.verify_selected(step.context, selected, evaluated.costs)
                    errors.observe(selected, evaluated.costs)
                    diagnostics.update({**errors.diagnostics(), **surrogate.diagnostics()})
                step.commit(step.result(population=selected.population, costs=evaluated.costs,
                    source=selected.source, surrogate_used=bool(perfect and selected.surrogate_used),
                    diagnostics=diagnostics))
                stop = record_generation(step.context, evaluated.costs,
                                         diagnostics=surrogate.diagnostics() if perfect else None)
                if stop:
                    break
