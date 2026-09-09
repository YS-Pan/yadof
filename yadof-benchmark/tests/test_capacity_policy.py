from pathlib import Path
from threading import Barrier, Event, Lock

import pytest

from yadof_benchmark import BenchmarkError, plan_workspace
from yadof_benchmark.benchmark_runtime import concurrency, execution
from yadof_benchmark.benchmark_runtime.storage import initialize_workspace, read_json
from test_benchmark import _baseline, _workspace, _cell_result, _successful_command


def test_capacity_changes_only_new_cells_and_preserves_the_scientific_plan(tmp_path, monkeypatch):
    for baseline in ("provider/a", "provider/b"):
        _baseline(tmp_path, baseline)
    root = _workspace(tmp_path / "capacity", baselines=("provider/a", "provider/b"),
                      strategies=("alpha", "beta", "gamma", "delta", "epsilon", "zeta"),
                      cell_concurrency=3)
    plan = plan_workspace(root, baselines_root=tmp_path / "baselines")
    initialize_workspace(plan)
    frozen_spec = (root / "spec.json").read_bytes()
    monkeypatch.setattr(execution, "detect_physical_cores", lambda: 8)
    monkeypatch.setattr(concurrency, "detect_physical_cores", lambda: 8)
    first_wave = Barrier(3)
    later_wave = Barrier(3)
    lowered = Event()
    guard = Lock()
    seen = []
    later_count = 0

    def policy(context):
        completed = context["completed_cells"]
        # Mutating the policy's snapshot must never change live execution state.
        context["cells"].clear()
        if completed == 0:
            return {"cell_concurrency": 3, "baseline_physical_core_multipliers": {
                "provider/a": 1., "provider/b": 2.}, "reason": "initial"}
        if completed < 4:
            lowered.set()
            return {"cell_concurrency": 1, "baseline_physical_core_multipliers": {
                "provider/a": .5, "provider/b": .25}, "reason": "lower"}
        return {"cell_concurrency": 3, "baseline_physical_core_multipliers": {
            "provider/a": 2., "provider/b": 1.}, "reason": "raise"}

    def command(args, **kwargs):
        nonlocal later_count
        if kwargs["label"] == "run":
            workspace = Path(kwargs["cwd"])
            before = (workspace / "config.py").read_text(encoding="utf-8")
            state = read_json(root / "state.json")
            cell_id = workspace.parent.name
            item = state["cells"][cell_id]
            revision = item["capacity_revision"]
            with guard:
                seen.append((cell_id, revision, item["baseline"], item["simulation_concurrency"]["resolved_max_workers"]))
                ordinal = len(seen)
                if revision >= 3:
                    later_count += 1
                later_ordinal = later_count
            if revision == 1:
                first_wave.wait(timeout=5)
                if ordinal != 1:
                    assert lowered.wait(timeout=5)
            elif revision >= 3 and later_ordinal <= 3:
                later_wave.wait(timeout=5)
            assert (workspace / "config.py").read_text(encoding="utf-8") == before
        return _successful_command(args, **kwargs)

    state = execution.execute_workspace(root, command_runner=command,
        collector=lambda workspace, cell: _cell_result(cell, .2), capacity_policy=policy)
    assert state["status"] == "completed"
    assert len(seen) == len({item[0] for item in seen}) == 12
    assert (root / "spec.json").read_bytes() == frozen_spec
    assert [item["cell_concurrency"] for item in state["capacity_history"]] == [3, 1, 3]
    assert {item[2] for item in seen if item[1] == 1} == {"provider/a", "provider/b"}
    for cell_id, revision, baseline, workers in seen:
        multiplier = state["capacity_history"][revision - 1]["baseline_physical_core_multipliers"][baseline]
        assert workers == int(8 * multiplier)
        result = read_json(root / state["cells"][cell_id]["result"])
        assert result["capacity_revision"] == revision
        assert result["simulation_concurrency"]["resolved_max_workers"] == workers


@pytest.mark.parametrize("decision", [
    {"cell_concurrency": 0}, {"cell_concurrency": True}, {"cell_concurrency": 3},
    {"population": 999}, {"seeds": [999]},
    {"baseline_physical_core_multipliers": {"missing/case": 1}},
    {"baseline_physical_core_multipliers": {"provider/task": float("nan")}},
    {"baseline_physical_core_multipliers": {"provider/task": 0}},
])
def test_bad_capacity_decisions_fail_before_admission(tmp_path, decision):
    _baseline(tmp_path)
    root = _workspace(tmp_path / "bad", cell_concurrency=2)
    initialize_workspace(plan_workspace(root, baselines_root=tmp_path / "baselines"))
    called = []
    with pytest.raises(BenchmarkError):
        execution.execute_workspace(root, capacity_policy=lambda context: decision,
            command_runner=lambda *args, **kwargs: called.append(args))
    assert not called
    state = read_json(root / "state.json")
    assert state["status"] == "failed"
    assert all(item["created_utc"] is None for item in state["cells"].values())
