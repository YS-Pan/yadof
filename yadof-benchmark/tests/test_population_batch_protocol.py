from pathlib import Path
from threading import Barrier
from types import SimpleNamespace

import pytest

from yadof_benchmark import plan_workspace
from yadof_benchmark.benchmark_runtime import execution
from yadof_benchmark.benchmark_runtime.storage import initialize_workspace
from yadof_benchmark.benchmark_runtime.storage import atomic_write_json, read_json
from yadof_benchmark.perfect_protocol import collect_top10, crossing_summary, record_generation
from test_benchmark import _baseline, _workspace, _cell_result, _successful_command


def test_mixed_budgets_plan_smoke_and_reference_pairing(tmp_path):
    _baseline(tmp_path)
    root = _workspace(tmp_path / "matrix", population=200, generations=50)
    source = root / "benchmark.py"
    text = source.read_text(encoding="utf-8").replace('slow_surrogate=False)',
        'slow_surrogate=False, population=50, batch_size=20, generations=491)', 1)
    text = text.replace('reference="alpha"', 'reference="alpha", initial_population=200')
    source.write_text(text, encoding="utf-8")
    planned = plan_workspace(root, baselines_root=tmp_path / "baselines").to_dict()
    first, second = planned["cells"]
    assert (first["population"], first["batch_size"], first["initial_population"]) == (50, 20, 200)
    assert first["planned_evaluations"] == second["planned_evaluations"] == 10000
    smoke = plan_workspace(root, baselines_root=tmp_path / "baselines", budget_profile="smoke").to_dict()
    assert all(c["generations"] == 1 and c["planned_evaluations"] == 200 for c in smoke["cells"])


@pytest.mark.parametrize("failed_seed,failure_kind", [(None, "budget"), (7, "budget"), (7, "contract")])
def test_parallel_references_publish_before_dependents(tmp_path, monkeypatch, failed_seed, failure_kind):
    _baseline(tmp_path)
    root = _workspace(tmp_path / "dependencies", strategies=("beta", "alpha"),
                      seeds=(7, 8), cell_concurrency=2)
    source = root / "benchmark.py"
    source.write_text(source.read_text(encoding="utf-8").replace(
        'reference="alpha"', 'reference="alpha", stop_on_top10_reference=True'), encoding="utf-8")
    plan = plan_workspace(root, baselines_root=tmp_path / "baselines")
    initialize_workspace(plan)
    published = set()
    real_publish = execution.publish_results
    def publish(root, spec, state):
        result = real_publish(root, spec, state)
        published.update(cell_id for cell_id, value in state["cells"].items() if value["status"] == "collected")
        return result
    monkeypatch.setattr(execution, "publish_results", publish)
    barrier = Barrier(2)
    by_id = {cell.id: cell.to_dict() for cell in plan.cells}
    candidates_ran = []
    def command(args, **kwargs):
        if kwargs["label"] == "run":
            cell = by_id[Path(kwargs["cwd"]).parent.name]
            if cell["strategy"] == "alpha":
                barrier.wait(timeout=5)  # Both references must occupy workers concurrently.
            else:
                reference = next(c for c in by_id.values() if c["strategy"] == "alpha" and c["seed"] == cell["seed"])
                assert reference["id"] in published
                assert cell["seed"] != failed_seed
                candidates_ran.append(cell["seed"])
        return _successful_command(args, **kwargs)
    def collect(workspace, cell):
        result = _cell_result(cell, 0.2)
        result["top10_protocol"] = {"budget_satisfied": cell["seed"] != failed_seed or failure_kind == "contract",
                                    "final_top10": 0.5, "reference": cell["strategy"] == "alpha"}
        if cell["seed"] == failed_seed:
            result["issues"].append("invalid reference")
            if failure_kind == "contract":
                result["contract"]["rawdata_shapes"]["matches"] = False
        return result
    state = execution.execute_workspace(root, command_runner=command, collector=collect)
    assert state["status"] == ("completed" if failed_seed is None else "failed")
    assert sorted(candidates_ran) == ([7, 8] if failed_seed is None else [8])


def test_unequal_batch_receipt_counts_and_tamper_detection(tmp_path):
    atomic_write_json(tmp_path / "benchmark_control.json", {"reference": False, "threshold": 0.5})
    context = SimpleNamespace(config=SimpleNamespace(workspace=SimpleNamespace(root=tmp_path)),
        generation_index=0, initial_population_size=20, batch_size=3, population_size=8, history=())
    assert not record_generation(context, ((0.5,),) * 20)
    context.generation_index = 1
    context.history = tuple(SimpleNamespace(costs=(0.5,)) for _ in range(20))
    assert record_generation(context, ((0.1,),) * 3)
    records = [{"generation_index": g} for g, count in ((0, 20), (1, 3)) for _ in range(count)]
    rows = [{**record, "costs": (0.5 if record["generation_index"] == 0 else 0.1,)} for record in records]
    cell = {"population": 8, "initial_population": 20, "batch_size": 3, "generations": 5}
    result = collect_top10(tmp_path, cell, records, rows)
    assert result["budget_satisfied"] and result["first_strictly_better_evaluations"] == 23
    path = tmp_path / "experiment_metrics/g0002.json"
    value = read_json(path)
    value["formal_evaluations"] = 16
    atomic_write_json(path, value)
    with pytest.raises(RuntimeError, match="disagree"):
        collect_top10(tmp_path, cell, records, rows)


def test_censored_and_failed_runs_are_not_dropped_from_medians():
    rows = [dict(baseline="case", strategy="gpsaf", population=200, batch_size=20,
        initial_population=200, planned_evaluations=10000, seed=i, status="collected",
        budget_satisfied=True, reference=False, first_strictly_better_evaluations=value)
        for i, value in enumerate([2000, 3000, None])]
    assert crossing_summary(rows)[0]["median_evaluations"] == 3000
    rows[1]["first_strictly_better_evaluations"] = None
    assert crossing_summary(rows)[0]["median_status"] == "right-censored"
    rows[2]["status"] = "failed"
    assert crossing_summary(rows)[0]["median_status"] == "unavailable"
    rows[2]["status"] = "collected"
    rows[2]["evidence_valid"] = False
    assert crossing_summary(rows)[0]["median_status"] == "unavailable"
