from __future__ import annotations

from datetime import datetime
import json
import math
from pathlib import Path
import sys
import time

import psutil
import pytest

from yadof import cli
from yadof.evaluate_manager import evaluate_population
from yadof.recorded_data import api as recorded_api
from yadof.workspace.check import check_workspace
from yadof.workspace.init import init_workspace


def _workspace(tmp_path: Path, name: str = "workspace") -> Path:
    root = tmp_path / name
    init_workspace(root)
    (root / "job_template/parameters_constraints.py").write_text(
        "from yadof.job_template import Parameter\n"
        "PARAMETERS = (Parameter('input_value', ((0.0, 1.0),)),)\n"
        "CONSTRAINTS = ()\n"
        "def get_parameters():\n"
        "    return tuple(PARAMETERS)\n",
        encoding="utf-8",
    )
    return root


def _write_evaluation(root: Path, body: str) -> None:
    (root / "job_template/evaluation.py").write_text(
        "from __future__ import annotations\n"
        "import json\n"
        "import numpy as np\n"
        f"{body}\n",
        encoding="utf-8",
    )


def _rawdata_result_expression(value_expression: str = "value") -> str:
    return (
        f"response = np.asarray(float({value_expression}), dtype=float)\n"
        "    payload = {\n"
        "        'values': response,\n"
        "        'metadata': json.dumps({\n"
        "            'schema_version': 1,\n"
        "            'rawdata_name': 'response',\n"
        "            'shape': [],\n"
        "        }),\n"
        "    }\n"
        "    return {'response.npz': payload}"
    )


def _scratch_is_clean(root: Path) -> bool:
    scratch = root / ".yadof/fast_scratch"
    return not scratch.exists() or not tuple(scratch.iterdir())


def test_fast_parallel_results_are_ordered_recorded_and_jobless(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    (root / "config.py").write_text(
        "EVALUATION_MODE = 'fast'\n"
        "FAST_RESOURCE_AUTODETECT_ENABLED = False\n",
        encoding="utf-8",
    )
    _write_evaluation(
        root,
        "def evaluate_rawdata(parameters, context):\n"
        "    import os\n"
        "    import subprocess\n"
        "    import sys\n"
        "    import time\n"
        "    value = float(parameters['input_value'])\n"
        "    started = time.time()\n"
        "    time.sleep((1.0 - value) * 0.12)\n"
        "    simulator_started = time.monotonic()\n"
        "    completed = subprocess.run(\n"
        "        [sys.executable, '-c', 'import sys; print(sys.argv[1])', str(value)],\n"
        "        cwd=context['scratch_dir'],\n"
        "        env={**os.environ, **dict(context['environment'])},\n"
        "        capture_output=True,\n"
        "        text=True,\n"
        "        check=False,\n"
        "    )\n"
        "    if completed.returncode != 0:\n"
        "        raise RuntimeError(completed.stderr)\n"
        "    response = np.asarray(float(completed.stdout.strip()), dtype=float)\n"
        "    payload = {\n"
        "        'values': response,\n"
        "        'metadata': json.dumps({\n"
        "            'schema_version': 1, 'rawdata_name': 'response', 'shape': []\n"
        "        }),\n"
        "    }\n"
        "    return {'response.npz': payload}, {\n"
        "        'task_started_epoch': started,\n"
        "        'simulator_returncode': completed.returncode,\n"
        "        'simulator_stderr_tail': completed.stderr[-1000:],\n"
        "        'simulator_elapsed_sec': time.monotonic() - simulator_started,\n"
        "    }\n",
    )

    costs = evaluate_population(
        root,
        ((0.0,), (0.25,), (0.5,), (0.75,), (1.0,)),
        mode="fast",
        timeout_sec=5.0,
        fast_max_workers=2,
        env={"YADOF_FAST_TEST_ENV": "isolated"},
        run_id="fast-order",
        generation_index=3,
    )

    assert [row[0] for row in costs] == pytest.approx(
        sorted(row[0] for row in costs)
    )
    assert not (root / "jobs").exists()
    assert _scratch_is_clean(root)
    records = sorted(
        recorded_api.list_records(root), key=lambda item: item["population_index"]
    )
    assert [record["raw_variables"] for record in records] == [
        {"input_value": 0.0},
        {"input_value": 0.25},
        {"input_value": 0.5},
        {"input_value": 0.75},
        {"input_value": 1.0},
    ]
    assert all(record["status"] == "completed" for record in records)
    assert all(record["job_metadata"]["engine"] == "fast" for record in records)
    assert all(record["job_metadata"]["fast_worker_count"] == 2 for record in records)
    assert all(
        record["job_metadata"]["task_diagnostics"]["simulator_returncode"] == 0
        for record in records
    )
    first_end = datetime.fromisoformat(records[0]["ended_at"])
    second_start = datetime.fromisoformat(records[1]["started_at"])
    assert second_start < first_end
    assert len(recorded_api.get_rawdata_samples(root)) == 5
    assert len(tuple(root.glob("recorded_data/v2/segments/*/*/segment_*.zip"))) == 1


def test_fast_record_failure_is_isolated_for_jobless_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from yadof.recorded_data import session as session_module

    root = _workspace(tmp_path)
    _write_evaluation(
        root,
        "def evaluate_rawdata(parameters, context):\n"
        "    value = float(parameters['input_value'])\n"
        f"    {_rawdata_result_expression('value')}\n",
    )
    def fail_publication(*args, **kwargs):
        raise OSError("simulated fast record failure")

    monkeypatch.setattr(session_module, "publish_segment", fail_publication)
    costs = evaluate_population(
        root,
        ((0.0,), (1.0,)),
        mode="fast",
        timeout_sec=5.0,
        fast_max_workers=1,
    )

    assert math.isfinite(costs[0][0])
    assert costs[1] == pytest.approx((0.9,))
    assert _scratch_is_clean(root)
    assert recorded_api.list_records(root) == ()


def test_fast_and_local_can_share_one_task_kernel(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    _write_evaluation(
        root,
        "def evaluate_rawdata(parameters, context):\n"
        "    value = float(parameters['input_value'])\n"
        f"    {_rawdata_result_expression('value')}\n",
    )
    (root / "job_template/workflow.py").write_text(
        "from __future__ import annotations\n"
        "from types import MappingProxyType\n"
        "import numpy as np\n"
        "from evaluation import evaluate_rawdata\n"
        "from parameters_constraints import get_parameters\n"
        "def _evaluate(context):\n"
        "    values = MappingProxyType({p.name: float(p.value) for p in get_parameters()})\n"
        "    items = evaluate_rawdata(values, MappingProxyType({\n"
        "        'evaluation_name': 'prepared-job',\n"
        "        'scratch_dir': context.base_dir,\n"
        "        'environment': MappingProxyType({}),\n"
        "    }))\n"
        "    if isinstance(items, tuple):\n"
        "        items = items[0]\n"
        "    for name, payload in items.items():\n"
        "        np.savez_compressed(context.raw_data_dir / name, **payload)\n"
        "def main():\n"
        "    from worker_misc import run_workflow\n"
        "    return run_workflow(_evaluate)\n"
        "if __name__ == '__main__':\n"
        "    raise SystemExit(main())\n",
        encoding="utf-8",
    )

    fast_cost = evaluate_population(
        root, ((0.3,),), mode="fast", timeout_sec=5.0, fast_max_workers=1
    )
    assert not (root / "jobs").exists()
    local_cost = evaluate_population(
        root, ((0.3,),), mode="local", timeout_sec=5.0, local_max_workers=1
    )

    assert fast_cost[0][0] == pytest.approx(local_cost[0][0])
    samples = recorded_api.get_rawdata_samples(root)
    assert len(samples) == 2
    assert samples[0][1][0]["values"] == pytest.approx(samples[1][1][0]["values"])


def test_fast_worker_crash_isolated_and_replaced(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    _write_evaluation(
        root,
        "def evaluate_rawdata(parameters, context):\n"
        "    import os\n"
        "    value = float(parameters['input_value'])\n"
        "    if value < 0.5:\n"
        "        os._exit(23)\n"
        f"    {_rawdata_result_expression('value')}\n",
    )

    costs = evaluate_population(
        root,
        ((0.0,), (1.0,)),
        mode="fast",
        timeout_sec=5.0,
        fast_max_workers=1,
    )

    assert math.isinf(costs[0][0])
    assert math.isfinite(costs[1][0])
    records = sorted(
        recorded_api.list_records(root), key=lambda item: item["population_index"]
    )
    assert [record["status"] for record in records] == ["error", "completed"]
    assert records[0]["job_metadata"]["error_type"] == "FastWorkerExit"
    assert records[0]["job_metadata"]["fast_worker_exitcode"] == 23
    assert (
        records[0]["job_metadata"]["fast_worker_pid"]
        != records[1]["job_metadata"]["fast_worker_pid"]
    )
    assert not (root / "jobs").exists()
    assert _scratch_is_clean(root)


def test_fast_timeout_kills_simulator_tree_and_continues(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    marker = f"yadof-fast-descendant-{time.time_ns()}"
    _write_evaluation(
        root,
        "def evaluate_rawdata(parameters, context):\n"
        "    import subprocess\n"
        "    import sys\n"
        "    import time\n"
        "    value = float(parameters['input_value'])\n"
        "    if value < 0.5:\n"
        f"        subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)', {marker!r}])\n"
        "        time.sleep(30)\n"
        f"    {_rawdata_result_expression('value')}\n",
    )

    costs = evaluate_population(
        root,
        ((0.0,), (1.0,)),
        mode="fast",
        timeout_sec=0.4,
        fast_max_workers=1,
    )

    assert math.isinf(costs[0][0])
    assert math.isfinite(costs[1][0])
    records = sorted(
        recorded_api.list_records(root), key=lambda item: item["population_index"]
    )
    assert [record["status"] for record in records] == ["timeout", "completed"]
    assert records[0]["job_metadata"]["fast_peak_process_count"] >= 2
    deadline = time.monotonic() + 4.0
    while time.monotonic() < deadline and _process_with_marker(marker):
        time.sleep(0.05)
    assert not _process_with_marker(marker)
    assert _scratch_is_clean(root)


def test_fast_simulator_failure_isolated_and_success_descendants_are_reaped(
    tmp_path: Path,
) -> None:
    root = _workspace(tmp_path)
    marker = f"yadof-fast-success-descendant-{time.time_ns()}"
    _write_evaluation(
        root,
        "def evaluate_rawdata(parameters, context):\n"
        "    import subprocess\n"
        "    import sys\n"
        "    value = float(parameters['input_value'])\n"
        "    if value < 0.5:\n"
        "        completed = subprocess.run(\n"
        "            [sys.executable, '-c', "
        "'import sys; print(\\\"simulator boom\\\", file=sys.stderr); sys.exit(17)'],\n"
        "            capture_output=True, text=True, check=False,\n"
        "        )\n"
        "        raise RuntimeError(\n"
        "            f'simulator returncode={completed.returncode}; stderr={completed.stderr.strip()}'\n"
        "        )\n"
        f"    subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)', {marker!r}])\n"
        f"    {_rawdata_result_expression('value')}\n",
    )

    costs = evaluate_population(
        root,
        ((0.0,), (1.0,)),
        mode="fast",
        timeout_sec=5.0,
        fast_max_workers=1,
    )

    assert math.isinf(costs[0][0])
    assert math.isfinite(costs[1][0])
    records = sorted(
        recorded_api.list_records(root), key=lambda item: item["population_index"]
    )
    assert [record["status"] for record in records] == ["error", "completed"]
    assert records[0]["job_metadata"]["error_type"] == "RuntimeError"
    assert "returncode=17" in records[0]["job_metadata"]["error_message"]
    assert "simulator boom" in records[0]["job_metadata"]["error_message"]
    deadline = time.monotonic() + 4.0
    while time.monotonic() < deadline and _process_with_marker(marker):
        time.sleep(0.05)
    assert not _process_with_marker(marker)
    assert _scratch_is_clean(root)


def test_fast_contract_is_required_by_check_and_startup(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    (root / "config.py").write_text(
        "EVALUATION_MODE = 'fast'\n", encoding="utf-8"
    )

    report = check_workspace(root)
    assert not report.ok
    assert "fast evaluation requires task kernel" in report.format()
    with pytest.raises(FileNotFoundError, match="fast evaluation requires task kernel"):
        evaluate_population(root, ((0.5,),), mode="fast", timeout_sec=1.0)
    assert not (root / "jobs").exists()
    assert not (root / "recorded_data").exists()


def test_fast_smoke_cli_is_explicit_jobless_and_single_worker(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _workspace(tmp_path)
    _write_evaluation(
        root,
        "def evaluate_rawdata(parameters, context):\n"
        "    value = float(parameters['input_value'])\n"
        f"    {_rawdata_result_expression('value')}\n",
    )

    assert cli.main(
        [
            "smoke-test",
            "--workspace",
            str(root),
            "--mode",
            "fast",
            "--real-task",
        ]
    ) == 0
    output = capsys.readouterr()
    assert "mode=fast" in output.out
    assert "creates no durable per-job folder" in output.out
    assert "Smoke test succeeded" in output.out
    assert not (root / "jobs").exists()
    record = recorded_api.list_records(root)[0]
    assert record["job_metadata"]["fast_worker_count"] == 1


def test_fast_workspaces_remain_isolated(tmp_path: Path) -> None:
    first = _workspace(tmp_path, "first")
    second = _workspace(tmp_path, "second")
    _write_evaluation(
        first,
        "OFFSET = 0.0\n"
        "def evaluate_rawdata(parameters, context):\n"
        "    value = float(parameters['input_value']) + OFFSET\n"
        f"    {_rawdata_result_expression('value')}\n",
    )
    _write_evaluation(
        second,
        "OFFSET = 0.5\n"
        "def evaluate_rawdata(parameters, context):\n"
        "    value = float(parameters['input_value']) + OFFSET\n"
        f"    {_rawdata_result_expression('value')}\n",
    )

    first_costs = evaluate_population(first, ((0.0,),), mode="fast", timeout_sec=3.0)
    second_costs = evaluate_population(second, ((0.0,),), mode="fast", timeout_sec=3.0)

    assert first_costs[0][0] < second_costs[0][0]
    assert len(recorded_api.list_records(first)) == 1
    assert len(recorded_api.list_records(second)) == 1
    assert _scratch_is_clean(first)
    assert _scratch_is_clean(second)


def _process_with_marker(marker: str) -> bool:
    for process in psutil.process_iter(("cmdline",)):
        try:
            command = process.info.get("cmdline") or ()
        except (psutil.Error, OSError):
            continue
        if marker in command:
            return True
    return False
