from __future__ import annotations

from pathlib import Path
import random

from project.optimize.gpsaf_misc import CandidateRecord, HistoryRecord
from project.optimize.problem_info import ProblemInfo


def _context(*, population_size: int = 5, objective_count: int = 1):
    from project.optimize.gpsaf_pymoo import make_context

    return make_context(
        ProblemInfo(
            variable_count=2,
            objective_count=int(objective_count),
            objective_names=tuple(f"cost_{idx}" for idx in range(int(objective_count))),
        ),
        population_size=int(population_size),
        seed=123,
        generation_index=2,
    )


def _history(count: int = 20) -> tuple[HistoryRecord, ...]:
    return tuple(
        HistoryRecord(
            job_name=f"job_{idx:03d}",
            x=(float(idx) / float(max(1, count - 1)), 1.0 - float(idx) / float(max(1, count - 1))),
            costs=(float(idx),),
        )
        for idx in range(int(count))
    )


def test_survivor_state_from_history_trims_active_population_to_configured_size():
    from project.optimize.gpsaf_pymoo import survivor_state_from_history

    state = survivor_state_from_history(_context(population_size=5), _history(20), 5)

    assert len(state.pop) == 5
    assert tuple(float(row[0]) for row in state.pop.get("F")) == (0.0, 1.0, 2.0, 3.0, 4.0)


def test_baseline_offspring_generation_uses_survivors_as_active_population(monkeypatch):
    from project.optimize import gpsaf_pymoo

    observed_active_sizes = []

    def fake_generate_candidate_pool(context, state, need, _used_keys, _rng, *, origin):
        observed_active_sizes.append((origin, len(state.pop)))
        return tuple(
            CandidateRecord(x=(0.01 * float(idx), 0.02 * float(idx)), origin=origin)
            for idx in range(int(need))
        )

    monkeypatch.setattr(gpsaf_pymoo, "generate_candidate_pool", fake_generate_candidate_pool)

    records, source = gpsaf_pymoo.baseline_records(
        context=_context(population_size=5),
        history=_history(20),
        size=5,
        generation_index=2,
        rng=random.Random(9),
    )

    assert source == "gpsaf_offspring"
    assert len(records) == 5
    assert observed_active_sizes == [("gpsaf_offspring", 5)]


def test_multi_objective_context_uses_nsga3_reference_directions():
    from project.optimize import gpsaf_pymoo

    context = _context(population_size=5, objective_count=3)
    diagnostics = gpsaf_pymoo.diagnostics(context)
    source = Path(gpsaf_pymoo.__file__).read_text(encoding="utf-8").lower()

    assert context.baseline_optimizer == "pymoo.NSGA3"
    assert diagnostics["reference_direction_count"] <= 5
    assert diagnostics["reference_direction_partitions"] >= 1
    assert "nsga2" not in source


def test_single_objective_context_skips_nsga3_reference_directions():
    context = _context(population_size=5, objective_count=1)

    assert context.baseline_optimizer == "pymoo.GA"
    assert context.reference_directions is None


def test_surrogate_generation_uses_survivors_as_active_population(monkeypatch):
    from project import config
    from project.optimize import gpsaf_phases

    observed_active_sizes = []

    def fake_generate_candidate_pool(context, state, need, _used_keys, _rng, *, origin):
        observed_active_sizes.append((origin, len(state.pop)))
        return tuple(
            CandidateRecord(x=(0.03 * float(idx), 0.04 * float(idx)), origin=origin)
            for idx in range(int(need))
        )

    def fake_predict_records(records):
        return [
            CandidateRecord(
                x=record.x,
                origin=record.origin,
                individual=record.individual,
                pred_costs=(sum(record.x),),
                intervals=((sum(record.x) - 0.1, sum(record.x) + 0.1),),
            )
            for record in records
        ]

    monkeypatch.setattr(config, "OPTIMIZE_SURROGATE_ALPHA", 1)
    monkeypatch.setattr(config, "OPTIMIZE_SURROGATE_BETA", 0)
    monkeypatch.setattr(config, "OPTIMIZE_SURROGATE_EXPLORATION_FRACTION", 0.0)
    monkeypatch.setattr(gpsaf_phases, "try_train_surrogate", lambda _generation_index: (object(), None))
    monkeypatch.setattr(gpsaf_phases, "generate_candidate_pool", fake_generate_candidate_pool)
    monkeypatch.setattr(gpsaf_phases, "predict_records", fake_predict_records)
    monkeypatch.setattr(gpsaf_phases, "historical_surrogate_errors", lambda: ())

    population, diagnostics = gpsaf_phases.surrogate_population(
        _history(20),
        context=_context(population_size=5),
        generation_index=2,
        population_size=5,
        seed=123,
    )

    assert population is not None
    assert len(population) == 5
    assert diagnostics["alpha_batches"] == 1
    assert diagnostics["alpha_selection"] == "nsga3_pooled_survival"
    assert observed_active_sizes == [("gpsaf_alpha_1", 5)]


def test_surrogate_generation_reserves_exploration_quota(monkeypatch):
    from project import config
    from project.optimize import gpsaf_phases

    def fake_generate_candidate_pool(context, state, need, _used_keys, _rng, *, origin):
        if origin == "gpsaf_exploration":
            return tuple(CandidateRecord(x=(0.90 + 0.01 * idx, 0.10), origin=origin) for idx in range(int(need)))
        return tuple(CandidateRecord(x=(0.10 + 0.01 * idx, 0.20), origin=origin) for idx in range(int(need)))

    def fake_predict_records(records):
        return [
            CandidateRecord(
                x=record.x,
                origin=record.origin,
                individual=record.individual,
                pred_costs=(sum(record.x), sum(record.x), sum(record.x)),
                intervals=((0.0, 1.0), (0.0, 1.0), (0.0, 1.0)),
            )
            for record in records
        ]

    monkeypatch.setattr(config, "OPTIMIZE_SURROGATE_ALPHA", 2)
    monkeypatch.setattr(config, "OPTIMIZE_SURROGATE_BETA", 0)
    monkeypatch.setattr(config, "OPTIMIZE_SURROGATE_EXPLORATION_FRACTION", 0.4)
    monkeypatch.setattr(gpsaf_phases, "try_train_surrogate", lambda _generation_index: (object(), None))
    monkeypatch.setattr(gpsaf_phases, "generate_candidate_pool", fake_generate_candidate_pool)
    monkeypatch.setattr(gpsaf_phases, "predict_records", fake_predict_records)
    monkeypatch.setattr(gpsaf_phases, "historical_surrogate_errors", lambda: ())

    population, diagnostics = gpsaf_phases.surrogate_population(
        _history(20),
        context=_context(population_size=5, objective_count=3),
        generation_index=2,
        population_size=5,
        seed=123,
    )

    assert population is not None
    assert len(population) == 5
    assert diagnostics["exploration_count"] == 2
    assert any(row[0] >= 0.90 for row in population)
