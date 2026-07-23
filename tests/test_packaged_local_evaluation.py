from __future__ import annotations

import json
import math
import os
from pathlib import Path

import pytest

import yadof
from yadof.config import load_config
from yadof.recorded_data import api as recorded_api
from yadof.evaluate_manager import (
    JobPreparationError,
    evaluate_population,
    prepare_job,
    prepared_job_static_hash,
    run_smoke_test,
)
from yadof.workspace import WorkspaceContext
from yadof.workspace.init import init_workspace


def _workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    init_workspace(root)
    return root


def _source_environment() -> dict[str, str]:
    package_parent = Path(yadof.__file__).resolve().parents[1]
    inherited = os.environ.get("PYTHONPATH", "")
    pythonpath = str(package_parent)
    if inherited:
        pythonpath += os.pathsep + inherited
    return {"PYTHONPATH": pythonpath}


def _metadata(job_dir: Path) -> dict[str, object]:
    return json.loads((job_dir / "metadata.json").read_text(encoding="utf-8"))


def test_prepare_job_composes_package_support_and_full_task_payload(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    task = root / "job_template"
    (task / "first_com.py").write_text("NAME = 'first'\n", encoding="utf-8")
    (task / "second_com.py").write_text("NAME = 'second'\n", encoding="utf-8")
    resources = task / "assets" / "nested"
    resources.mkdir(parents=True)
    (resources / "lookup.bin").write_bytes(b"arbitrary task bytes")
    (resources / "metadata.json").write_text('{"task": true}\n', encoding="utf-8")
    (resources / "rawData").mkdir()
    (resources / "rawData" / "seed.bin").write_bytes(b"nested task resource")

    config = load_config(root)
    first = prepare_job(
        config.workspace,
        (0.25,),
        config=config,
        mode="local",
        timeout_sec=12.0,
        run_id="run-a",
        optimization_index=4,
        generation_index=2,
        population_index=0,
    )
    second = prepare_job(
        config.workspace,
        (0.75,),
        config=config,
        mode="local",
        timeout_sec=12.0,
        population_index=1,
    )

    for name in (
        "workflow.py",
        "first_com.py",
        "second_com.py",
        "worker_misc.py",
    ):
        assert (first.directory / name).is_file()
    assert (first.directory / "assets/nested/lookup.bin").read_bytes() == b"arbitrary task bytes"
    assert (first.directory / "assets/nested/metadata.json").is_file()
    assert (first.directory / "assets/nested/rawData/seed.bin").read_bytes() == b"nested task resource"
    assert not (first.directory / "calc_cost.py").exists()
    assert not (first.directory / "cost.json").exists()
    assert not (first.directory / "config.py").exists()
    assert not (first.directory / "config").exists()

    assigned = (first.directory / "parameters_constraints.py").read_text(encoding="utf-8")
    assert "normalized_value=0.25" in assigned
    assert "value=-0.5" in assigned
    assert "class Parameter:" in assigned
    assert "import yadof" not in assigned
    first_metadata = _metadata(first.directory)
    second_metadata = _metadata(second.directory)
    assert first_metadata["job_static_hash"] == second_metadata["job_static_hash"]
    assert first_metadata["job_static_hash"] == prepared_job_static_hash(first.directory)
    assert first_metadata["yadof_version"] == yadof.__version__
    assert first_metadata["workspace_identity"]["root"] == str(root.resolve())
    assert first_metadata["workspace_identity"]["marker"]["template_name"] == "default"
    assert first_metadata["run_id"] == "run-a"
    assert first_metadata["optimization_index"] == 4
    assert first_metadata["generation_index"] == 2
    summary = first_metadata["effective_config_summary"]
    assert set(summary) == {
        "EVALUATION_MODE",
        "EVALUATION_TIMEOUT_SEC",
        "LOCAL_EVALUATION_MAX_WORKERS",
    }
    assert summary["EVALUATION_TIMEOUT_SEC"]["value"] == 12.0
    assert "OPTIMIZE_POPULATION_SIZE" not in json.dumps(first_metadata)


def test_prepare_job_reloads_task_and_hashes_definitions_not_assignments(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    config = load_config(root)
    first = prepare_job(
        root,
        (0.25,),
        config=config,
        mode="local",
        timeout_sec=1.0,
    )
    second = prepare_job(
        root,
        (0.75,),
        config=config,
        mode="local",
        timeout_sec=1.0,
    )
    assert _metadata(first.directory)["job_static_hash"] == _metadata(second.directory)["job_static_hash"]

    parameter_file = root / "job_template/parameters_constraints.py"
    source = parameter_file.read_text(encoding="utf-8")
    parameter_file.write_text(source.replace("(-1.0, 1.0)", "(-2.0, 2.0)"), encoding="utf-8")
    third = prepare_job(
        root,
        (0.75,),
        config=config,
        mode="local",
        timeout_sec=1.0,
    )
    third_assigned = (third.directory / "parameters_constraints.py").read_text(encoding="utf-8")
    assert "value=1.0" in third_assigned
    assert _metadata(third.directory)["job_static_hash"] != _metadata(first.directory)["job_static_hash"]


@pytest.mark.parametrize(
    "reserved_name",
    ("worker_misc.py", "WORKER_MISC.PY"),
)
def test_prepare_job_rejects_reserved_filename_collisions(
    tmp_path: Path, reserved_name: str
) -> None:
    root = _workspace(tmp_path)
    (root / "job_template" / reserved_name).write_text("task owned\n", encoding="utf-8")

    with pytest.raises(JobPreparationError, match="collides with package worker support"):
        prepare_job(root, (0.5,), mode="local", timeout_sec=1.0)

    assert not (root / "jobs").exists()


def test_packaged_local_evaluation_success_and_smoke_contract(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    costs = run_smoke_test(root, env=_source_environment())

    assert costs == ((0.0,),)
    jobs = tuple((root / "jobs").iterdir())
    assert len(jobs) == 1
    metadata = _metadata(jobs[0])
    assert metadata["status"] == "done"
    assert metadata["timed_out"] is False
    assert metadata["effective_config_summary"]["EVALUATION_TIMEOUT_SEC"] == {
        "value": None,
        "source": "no-timeout smoke-test override",
    }
    assert not (jobs[0] / "calc_cost.py").exists()
    assert not (jobs[0] / "cost.json").exists()
    records = recorded_api.list_records(root)
    assert len(records) == 1
    assert records[0]["status"] == "completed"
    assert records[0]["started_at"]
    assert records[0]["ended_at"]
    assert (root / "recorded_data/rawData.npz").is_file()


def test_packaged_local_failures_are_isolated_and_return_inf(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    workflow = root / "job_template/workflow.py"
    workflow.write_text(
        """from __future__ import annotations
import json
from pathlib import Path
import numpy as np
from parameters_constraints import get_parameters

root = Path(__file__).resolve().parent
value = float(get_parameters()[0].value)
if value < 0:
    raise RuntimeError('negative candidate failed')
raw = root / 'rawData'
raw.mkdir(exist_ok=True)
data = np.asarray(value * value, dtype=float)
np.savez(raw / 'response.npz', values=data, metadata=json.dumps({
    'schema_version': 1, 'shape': [], 'rawdata_name': 'response'
}))
""",
        encoding="utf-8",
    )

    costs = evaluate_population(
        root,
        ((0.0,), (1.0,)),
        mode="local",
        timeout_sec=5.0,
        env=_source_environment(),
    )

    assert costs == ((math.inf,), (1.0,))
    statuses = sorted(_metadata(path)["status"] for path in (root / "jobs").iterdir())
    assert statuses == ["done", "error"]
    assert sorted(record["status"] for record in recorded_api.list_records(root)) == [
        "completed",
        "error",
    ]


def test_packaged_prepare_failure_does_not_write_metadata_at_jobs_root(tmp_path: Path) -> None:
    root = _workspace(tmp_path)

    costs = evaluate_population(
        root,
        ((0.1, 0.2), (0.5,)),
        mode="local",
        timeout_sec=5.0,
        env=_source_environment(),
    )

    assert costs == ((math.inf,), (0.0,))
    assert not (root / "jobs/metadata.json").exists()
    assert sorted(record["status"] for record in recorded_api.list_records(root)) == [
        "completed",
        "error",
    ]


def test_packaged_local_timeout_is_per_individual_failure(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    (root / "job_template/workflow.py").write_text(
        "import time\ntime.sleep(5)\n",
        encoding="utf-8",
    )

    costs = evaluate_population(
        root,
        ((0.5,),),
        mode="local",
        timeout_sec=0.1,
        env=_source_environment(),
    )

    assert costs == ((math.inf,),)
    job = next((root / "jobs").iterdir())
    metadata = _metadata(job)
    assert metadata["status"] == "timeout"
    assert metadata["timed_out"] is True
    assert recorded_api.list_records(root)[0]["status"] == "timeout"


def test_packaged_record_failure_is_isolated_per_individual(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from yadof.evaluate_manager import api as evaluate_api

    root = _workspace(tmp_path)
    real_record_result = evaluate_api.record_result

    def force_individual_fallback(workspace, results):
        del workspace, results
        raise OSError("simulated batch record failure")

    def flaky_record_result(workspace, result):
        if result.unnormalized_variables[0] < 0:
            raise OSError("simulated individual record failure")
        return real_record_result(workspace, result)

    monkeypatch.setattr(evaluate_api, "record_results", force_individual_fallback)
    monkeypatch.setattr(evaluate_api, "record_result", flaky_record_result)
    costs = evaluate_population(
        root,
        ((0.0,), (1.0,)),
        mode="local",
        timeout_sec=5.0,
        env=_source_environment(),
    )

    assert costs == ((math.inf,), (1.0,))
    records = recorded_api.list_records(root)
    assert len(records) == 1
    assert records[0]["status"] == "completed"
    assert records[0]["raw_variables"] == [1.0]


def test_packaged_evaluation_uses_effective_recorded_data_path(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    config_path = root / "config.py"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + "\nRECORDED_DATA_DIR = 'state/history'\n",
        encoding="utf-8",
        newline="\n",
    )

    costs = evaluate_population(
        root,
        ((0.5,),),
        mode="local",
        timeout_sec=5.0,
        env=_source_environment(),
    )

    assert costs == ((0.0,),)
    effective_workspace = load_config(root).workspace
    assert recorded_api.get_job_names(effective_workspace)
    assert (root / "state/history/indMeta.jsonl").is_file()
    assert not (root / "recorded_data").exists()


def test_smoke_cli_requires_explicit_real_task_and_runs_exactly_one(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from yadof import cli

    root = _workspace(tmp_path)
    monkeypatch.setenv("PYTHONPATH", str(Path(yadof.__file__).resolve().parents[1]))
    assert cli.main(["smoke-test", "--workspace", str(root)]) == 0
    output = capsys.readouterr()
    assert "exactly one individual" in output.out
    assert output.err == ""
    assert len(tuple((root / "jobs").iterdir())) == 1

    workflow = root / "job_template/workflow.py"
    workflow.write_text(workflow.read_text(encoding="utf-8") + "\n# user edit\n", encoding="utf-8")
    assert cli.main(["smoke-test", "--workspace", str(root)]) == 1
    output = capsys.readouterr()
    assert "--real-task" in output.err
    assert "may launch expensive external software" in output.err
    assert len(tuple((root / "jobs").iterdir())) == 1

    assert cli.main(
        ["smoke-test", "--workspace", str(root), "--real-task"]
    ) == 0
    output = capsys.readouterr()
    assert "Smoke test succeeded" in output.out
    assert len(tuple((root / "jobs").iterdir())) == 2


def test_smoke_help_distinguishes_execution_from_package_self_tests() -> None:
    parser = __import__("yadof.cli", fromlist=["build_parser"]).build_parser()
    smoke_parser = parser._subparsers._group_actions[0].choices["smoke-test"]
    help_text = smoke_parser.format_help()

    assert "exactly one" in help_text
    assert "no timeout" in help_text
    assert "launch simulator or custom software" in help_text
    assert "package self-tests" in help_text
