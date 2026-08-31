"""Conservative real-only GA/NSGA-III workspace program."""

from yadof.evaluate_manager import start_evaluation
from yadof.optimize import (
    by_objective_count,
    full_real_search,
    pymoo_ga,
    pymoo_nsga3,
)


YADOF_OPTIMIZATION_PROGRAM = {
    "api": "yadof.optimize.program/v1",
    "entry": "optimization_program",
    "helpers": (),
    "identity": {"program": "example-real-only", "version": 1},
    "capabilities": ("real-evaluation", "ga", "nsga3"),
}


def optimization_program(context):
    search = by_objective_count(single=pymoo_ga(), multi=pymoo_nsga3())
    with context.run_scope() as run:
        for generation_index in run.generations():
            with run.generation(generation_index) as step:
                selected = full_real_search(
                    step.context,
                    search,
                    origin_prefix="example_real_only",
                )
                handle = start_evaluation(
                    step.prepare_evaluation(selected.population)
                )
                try:
                    evaluation = handle.wait()
                finally:
                    handle.close()
                diagnostics = dict(selected.state.diagnostics)
                diagnostics.update(dict(selected.diagnostics))
                step.commit(
                    step.result(
                        population=selected.population,
                        costs=evaluation.costs,
                        source=selected.source,
                        diagnostics=diagnostics,
                    )
                )
