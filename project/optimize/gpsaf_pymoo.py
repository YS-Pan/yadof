from __future__ import annotations

import copy
from dataclasses import dataclass
import random
from typing import Sequence

import numpy as np
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.algorithms.soo.nonconvex.ga import GA
from pymoo.core.individual import Individual
from pymoo.core.population import Population
from pymoo.core.problem import Problem
from pymoo.operators.crossover.sbx import SBX
from pymoo.operators.mutation.pm import PM
from pymoo.operators.sampling.rnd import FloatRandomSampling

from project import config

from .gpsaf_misc import (
    CandidateRecord,
    HistoryRecord,
    Population as OptimizerPopulation,
    clip01,
    history_keys,
    history_variable_count,
    key,
    resolve_variable_count,
)
from .problem_info import ProblemInfo, from_job_template


@dataclass(frozen=True)
class PymooContext:
    problem: ProblemInfo
    population_size: int
    seed: int
    generation_index: int
    baseline_optimizer: str
    problem_adapter: Problem


class UnitBoxProblem(Problem):
    def __init__(self, problem: ProblemInfo):
        super().__init__(
            n_var=int(problem.variable_count),
            n_obj=int(problem.objective_count),
            xl=0.0,
            xu=1.0,
        )

    def _evaluate(self, _x, _out, *_args, **_kwargs):
        raise RuntimeError("GPSAF supplies evaluations through pymoo ask/tell")


def _fitness_matrix(costs: Sequence[Sequence[float]], objective_count: int) -> np.ndarray:
    rows = []
    for row in costs:
        values = [float(value) for value in row]
        if len(values) < int(objective_count):
            values.extend([float("inf")] * (int(objective_count) - len(values)))
        rows.append(values[: int(objective_count)])
    return np.asarray(rows, dtype=float)


def _x_matrix(values: Sequence[Sequence[float]], variable_count: int) -> np.ndarray:
    rows = []
    for row in values:
        values_ = [clip01(value) for value in tuple(row)[: int(variable_count)]]
        while len(values_) < int(variable_count):
            values_.append(0.5)
        rows.append(values_)
    return np.asarray(rows, dtype=float)


def _make_algorithm(context: PymooContext):
    dim = max(1, int(context.problem.variable_count))
    mutation_prob = float(getattr(config, "OPTIMIZE_MUTATION_PROBABILITY", 0.35))
    mutation_prob_var = min(1.0, float(getattr(config, "OPTIMIZE_DIM_MUT_PER_INDIVIDUAL", 1.0)) / float(dim))
    crossover = SBX(
        prob=float(getattr(config, "OPTIMIZE_CROSSOVER_PROBABILITY", 0.8)),
        eta=float(getattr(config, "OPTIMIZE_CROSSOVER_ETA", 20.0)),
    )
    mutation = PM(
        prob=mutation_prob,
        prob_var=mutation_prob_var,
        eta=float(getattr(config, "OPTIMIZE_MUTATION_ETA", 20.0)),
        at_least_once=True,
    )
    if int(context.problem.objective_count) <= 1:
        return GA(
            pop_size=int(context.population_size),
            n_offsprings=int(context.population_size),
            sampling=FloatRandomSampling(),
            crossover=crossover,
            mutation=mutation,
            eliminate_duplicates=True,
        )
    return NSGA2(
        pop_size=int(context.population_size),
        n_offsprings=int(context.population_size),
        sampling=FloatRandomSampling(),
        crossover=crossover,
        mutation=mutation,
        eliminate_duplicates=True,
    )


def make_context(
    problem: ProblemInfo,
    *,
    population_size: int,
    seed: int,
    generation_index: int,
) -> PymooContext:
    return PymooContext(
        problem=problem,
        population_size=int(population_size),
        seed=int(seed),
        generation_index=int(generation_index),
        baseline_optimizer="pymoo.GA" if int(problem.objective_count) <= 1 else "pymoo.NSGA2",
        problem_adapter=UnitBoxProblem(problem),
    )


def new_algorithm(context: PymooContext):
    algorithm = _make_algorithm(context)
    algorithm.setup(context.problem_adapter, seed=int(context.seed), verbose=False)
    return algorithm


def clone_algorithm(algorithm):
    return copy.deepcopy(algorithm)


def history_population(context: PymooContext, history: Sequence[HistoryRecord]):
    algorithm = new_algorithm(context)
    rows = [record for record in history if record.x]
    if rows:
        algorithm.tell(
            infills=Population.new(
                X=_x_matrix([record.x for record in rows], context.problem.variable_count),
                F=_fitness_matrix([record.costs for record in rows], context.problem.objective_count),
            )
        )
    return algorithm


def _selected_population(context: PymooContext, algorithm, size: int) -> Population:
    pop = getattr(algorithm, "pop", None)
    if pop is None or len(pop) == 0:
        return Population()
    return algorithm.survival.do(
        context.problem_adapter,
        pop,
        n_survive=min(int(size), len(pop)),
        algorithm=algorithm,
        random_state=getattr(algorithm, "random_state", None),
    )


def survivor_state_from_history(context: PymooContext, history: Sequence[HistoryRecord], size: int):
    algorithm = history_population(context, history)
    selected = _selected_population(context, algorithm, size)
    if len(selected) > 0:
        algorithm.pop = selected
        set_optimum = getattr(algorithm, "_set_optimum", None)
        if callable(set_optimum):
            set_optimum()
    return algorithm


def _record_from_individual(context: PymooContext, individual, origin: str) -> CandidateRecord:
    x = tuple(float(value) for value in _x_matrix([individual.get("X")], context.problem.variable_count)[0])
    individual.set("X", np.asarray(x, dtype=float))
    return CandidateRecord(individual=individual, x=x, origin=str(origin))


def records_from_population(context: PymooContext, pop: Population, origin: str) -> list[CandidateRecord]:
    return [_record_from_individual(context, individual, origin) for individual in pop]


def population_from_records(records: Sequence[CandidateRecord]) -> OptimizerPopulation:
    return tuple(tuple(float(value) for value in record.x) for record in records)


def generate_candidate_pool(
    context: PymooContext,
    state,
    need: int,
    used_keys: set[tuple[float, ...]],
    rng: random.Random,
    *,
    origin: str,
) -> list[CandidateRecord]:
    accepted: list[CandidateRecord] = []
    if int(need) <= 0:
        return accepted

    attempts = max(1, int(getattr(config, "OPTIMIZE_REFILL_ATTEMPTS", 8)))
    for _attempt in range(attempts):
        infills = state.ask()
        for record in records_from_population(context, infills, origin):
            candidate_key = key(record.x)
            if candidate_key in used_keys:
                continue
            used_keys.add(candidate_key)
            accepted.append(record)
            if len(accepted) >= int(need):
                return accepted

    while len(accepted) < int(need):
        x = tuple(rng.random() for _ in range(int(context.problem.variable_count)))
        candidate_key = key(x)
        if candidate_key in used_keys:
            continue
        used_keys.add(candidate_key)
        accepted.append(CandidateRecord(individual=Individual(X=np.asarray(x, dtype=float)), x=x, origin=f"{origin}_random_refill"))
    return accepted


def advance_population_with_records(
    context: PymooContext,
    state,
    records: Sequence[CandidateRecord],
    _target_size: int,
):
    individuals = []
    for record in records:
        if not record.pred_costs:
            continue
        individual = record.individual or Individual(X=np.asarray(record.x, dtype=float))
        individual.set("X", np.asarray(record.x, dtype=float))
        individual.set("F", _fitness_matrix([record.pred_costs], context.problem.objective_count)[0])
        individuals.append(individual)
    if individuals:
        state.tell(infills=Population.create(*individuals))
    return state


def baseline_records(
    *,
    context: PymooContext,
    history: Sequence[HistoryRecord],
    size: int,
    generation_index: int,
    rng: random.Random,
) -> tuple[list[CandidateRecord], str]:
    state = history_population(context, history)
    if not history:
        return (
            generate_candidate_pool(context, state, size, set(), rng, origin="gpsaf_random"),
            "gpsaf_random",
        )

    if int(generation_index) <= 0:
        selected = records_from_population(context, _selected_population(context, state, size), "gpsaf_warm_start")
        if len(selected) < int(size):
            selected.extend(
                generate_candidate_pool(
                    context,
                    state,
                    int(size) - len(selected),
                    history_keys(tuple(history)),
                    rng,
                    origin="gpsaf_random_refill",
                )
            )
            return selected[: int(size)], "gpsaf_random_refill"
        return selected, "gpsaf_warm_start"

    state = survivor_state_from_history(context, history, size)
    records = generate_candidate_pool(
        context,
        state,
        int(size),
        history_keys(tuple(history)),
        rng,
        origin="gpsaf_offspring",
    )
    if records:
        return records, "gpsaf_offspring"
    return (
        generate_candidate_pool(context, new_algorithm(context), size, set(), rng, origin="gpsaf_random_refill"),
        "gpsaf_random_refill",
    )


def _history_objective_count(history: Sequence[HistoryRecord]) -> int:
    for record in history:
        if record.costs:
            return len(record.costs)
    return 1


def resolve_problem_info(variable_count: int | None, history: Sequence[HistoryRecord]) -> ProblemInfo:
    count_hint = history_variable_count(history) if variable_count is None else int(variable_count)
    try:
        return from_job_template(count_hint)
    except Exception:
        if count_hint is None:
            count_hint = resolve_variable_count(variable_count, history)
        objective_count = _history_objective_count(history)
        return ProblemInfo(
            variable_count=int(count_hint),
            objective_count=int(objective_count),
            objective_names=tuple(f"cost_{idx}" for idx in range(int(objective_count))),
        )


def diagnostics(context: PymooContext) -> dict[str, object]:
    return {
        "optimizer": "gpsaf",
        "baseline_optimizer": context.baseline_optimizer,
        "objective_count": int(context.problem.objective_count),
        "objective_names": tuple(context.problem.objective_names),
        "variable_count": int(context.problem.variable_count),
    }
