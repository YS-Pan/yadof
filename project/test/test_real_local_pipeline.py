from __future__ import annotations

from pathlib import Path

import pytest


def test_real_local_pipeline_records_rawdata_without_cost_files(tmp_path, monkeypatch):
    from project.evaluate_manager.api import evaluate_population
    from project.recorded_data import api as recorded_api

    record_root = tmp_path / "recorded_data"
    monkeypatch.setattr(recorded_api, "MODULE_DIR", record_root)
    monkeypatch.setattr(recorded_api, "MANIFEST_PATH", record_root / "manifest.json")
    monkeypatch.setattr(recorded_api, "RAWDATA_ROOT", record_root / "rawData")

    jobs_dir = tmp_path / "jobs"
    population = ((0.25, 0.5, 0.75) + (0.5,) * 17,)
    costs = evaluate_population(population, jobs_dir=jobs_dir, timeout_sec=30)

    assert len(costs) == 1
    assert len(costs[0]) == 3
    assert all(0.0 <= value <= 1.0 for value in costs[0])

    job_dirs = [path for path in jobs_dir.iterdir() if path.is_dir()]
    assert len(job_dirs) == 1
    job_dir = job_dirs[0]
    assert not (job_dir / "cost.json").exists()
    assert not (job_dir / "calc_cost.py").exists()
    assert not (job_dir / "hfss_com.py").exists()
    assert len(tuple((job_dir / "rawData").glob("*.npz"))) == 3

    records = recorded_api.list_records()
    assert len(records) == 1
    assert "cost" not in records[0]
    assert len(records[0]["raw_variables"]) == 20
    assert records[0]["raw_variables"][:3] == pytest.approx([0.25, 0.5, 0.75])
    assert "job_static_hash" in records[0]["job_metadata"]

    history = recorded_api.get_optimization_history()
    assert len(history) == 1
    _job_name, normalized_variables, history_costs = history[0]
    assert normalized_variables == pytest.approx(population[0])
    assert history_costs == pytest.approx(costs[0])
