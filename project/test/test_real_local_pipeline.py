from __future__ import annotations

import os

import pytest


def test_real_local_pipeline_records_rawdata_without_cost_files(tmp_path, monkeypatch):
    if os.environ.get("YADOT_RUN_HFSS_TESTS") != "1":
        pytest.skip("requires PyAEDT/AEDT; set YADOT_RUN_HFSS_TESTS=1 for a real HFSS smoke test")

    from project.evaluate_manager.api import evaluate_population
    from project.job_template import api as job_template_api
    from project.recorded_data import api as recorded_api

    record_root = tmp_path / "recorded_data"
    monkeypatch.setattr(recorded_api, "MODULE_DIR", record_root)
    monkeypatch.setattr(recorded_api, "IND_META_PATH", record_root / "indMeta.jsonl")
    monkeypatch.setattr(recorded_api, "RAWDATA_ARCHIVE_PATH", record_root / "rawData.npz")
    monkeypatch.setattr(recorded_api, "OPT_META_DIR", record_root / "optMeta")
    monkeypatch.setattr(recorded_api, "OPT_META_PATH", record_root / "optMeta" / "optMeta.jsonl")

    jobs_dir = tmp_path / "jobs"
    population = ((0.25, 0.5, 0.75) + (0.5,) * (job_template_api.get_variable_count() - 3),)
    costs = evaluate_population(
        population,
        jobs_dir=jobs_dir,
        timeout_sec=float(os.environ.get("YADOT_HFSS_SMOKE_TIMEOUT_SEC", "1800")),
        run_id="pytest_run",
        optimization_index=4,
        generation_index=5,
    )

    assert len(costs) == 1
    assert len(costs[0]) == 4
    assert all(0.0 <= value <= 1.0 for value in costs[0])

    job_dirs = [path for path in jobs_dir.iterdir() if path.is_dir()]
    assert len(job_dirs) == 1
    job_dir = job_dirs[0]
    assert not (job_dir / "cost.json").exists()
    assert not (job_dir / "calc_cost.py").exists()
    assert (job_dir / "hfss_com.py").is_file()
    assert (job_dir / "individual_metadata.json").is_file()
    assert len(tuple((job_dir / "rawData").glob("*.npz"))) == 8

    records = recorded_api.list_records()
    assert len(records) == 1
    assert "cost" not in records[0]
    assert "created_at" not in records[0]
    assert isinstance(records[0]["started_at"], str)
    assert isinstance(records[0]["ended_at"], str)
    assert records[0]["run_id"] == "pytest_run"
    assert records[0]["optimization_index"] == 4
    assert records[0]["generation_index"] == 5
    assert records[0]["population_index"] == 0
    assert len(records[0]["raw_variables"]) == job_template_api.get_variable_count()
    assert records[0]["raw_variables"][:3] == pytest.approx(job_template_api.denormalize_variables(population[0])[:3])
    assert "variables" not in records[0]["rawdata_metadata"][records[0]["rawdata_files"][0]]
    assert "unnormalized_variables" not in records[0]["job_metadata"]
    assert (record_root / "rawData.npz").is_file()
    assert not (record_root / "rawData").exists()
    assert "job_static_hash" in records[0]["job_metadata"]

    history = recorded_api.get_optimization_history()
    assert len(history) == 1
    _job_name, normalized_variables, history_costs = history[0]
    assert normalized_variables == pytest.approx(population[0])
    assert history_costs == pytest.approx(costs[0])
