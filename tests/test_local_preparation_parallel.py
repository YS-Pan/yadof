from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import math
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

from yadof.config import load_config
from yadof.evaluate_manager import evaluate_population, prepare_job, prepared_job_static_hash
from yadof.job_template import freeze_job_parameters, task_cost_interpreter
from yadof.recorded_data import api as recorded_api
from yadof.workspace.init import init_workspace


def test_frozen_parameter_jobs_match_fresh_assignments_and_hashes(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    init_workspace(root)
    parameter_file = root / "job_template/parameters_constraints.py"
    parameter_file.write_text(
        "from yadof.job_template import Parameter\n"
        "PARAMETERS = (Parameter('continuous', ((-2, 3),), unit='m'),\n"
        "              Parameter('discrete', (1, 4, 8)),\n"
        "              Parameter('mixed', ((-5, -1), 2, (5, 7))))\n"
        "CONSTRAINTS = ('continuous + mixed',)\n",
        encoding="utf-8",
    )
    config = load_config(root)
    rows = ((0.0, 0.0, 0.0), (0.25, 0.5, 0.5), (1.0, 1.0, 1.0), (-0.1, 1.2, 0.8))
    fresh = [prepare_job(root, row, config=config, timeout_sec=1.0) for row in rows]
    template = freeze_job_parameters(root)
    template.parameters()[0].value = 999.0
    assert math.isnan(template.parameters()[0].value)

    # Hold the cost interpreter's task namespace while actual worker threads prepare.
    # Exit the interpreter before executor shutdown even if a regression times out.
    with ThreadPoolExecutor(max_workers=4) as executor:
        with task_cost_interpreter(root):
            futures = [
                executor.submit(
                    prepare_job, root, row, config=config, timeout_sec=1.0,
                    _parameter_template=template,
                )
                for row in rows
            ]
            frozen = [future.result(timeout=10.0) for future in futures]
    for expected, actual in zip(fresh, frozen):
        assert actual.unnormalized_variables == expected.unnormalized_variables
        assert (actual.directory / "parameters_constraints.py").read_bytes() == (
            expected.directory / "parameters_constraints.py"
        ).read_bytes()
        metadata = json.loads((actual.directory / "metadata.json").read_text(encoding="utf-8"))
        assert metadata["job_static_hash"] == prepared_job_static_hash(actual.directory)
        assert prepared_job_static_hash(actual.directory) == prepared_job_static_hash(expected.directory)

    parameter_file.write_text(
        parameter_file.read_text(encoding="utf-8").replace("(-2, 3)", "(-4, 6)"),
        encoding="utf-8",
    )
    changed = freeze_job_parameters(root)
    assert template.definition_signature() != changed.definition_signature()
    job = prepare_job(root, rows[1], config=config, timeout_sec=1.0, _parameter_template=changed)
    assert job.unnormalized_variables[0] == -1.5


_PARALLEL_CHILD = r'''
import json
import math
from pathlib import Path
import sys
import time
import numpy as np
from yadof.config import load_config
from yadof.evaluate_manager import api, prepared_job_static_hash
from yadof.evaluate_manager.types import JobResult
from yadof.job_template import NamedRawDataItem, RAWDATA_SCHEMA_VERSION
from yadof.recorded_data import api as recorded_api
from yadof.workspace.init import init_workspace

root = Path(sys.argv[1])
init_workspace(root)
marker = root / 'cost-entered'
(root / 'submit/calc_cost.py').write_text(
    "from pathlib import Path\n"
    "def get_objective_names(): return ('response',)\n"
    "def calculate_cost(sample_rawdata, raw_variables=None):\n"
    f"    Path({str(marker)!r}).write_text('entered', encoding='utf-8')\n"
    "    return (float(raw_variables[0]) ** 2,)\n",
    encoding='utf-8',
)
config_file = root / 'config.py'
with config_file.open('a', encoding='utf-8') as stream:
    stream.write('\nHISTORY_SEGMENT_MAX_CANDIDATES = 1\n')
prepare = api.prepare_job

def delayed_prepare(*args, **kwargs):
    if kwargs['population_index'] >= 2:
        deadline = time.monotonic() + 10.0
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.005)
        assert marker.exists(), 'cost did not start before later preparation'
    return prepare(*args, **kwargs)

def execute(job, **kwargs):
    index = job.population_index
    failed = index in (1, 5)
    raw = () if failed else (NamedRawDataItem('response.npz', {
        'values': np.asarray(job.unnormalized_variables[0] ** 2),
        'metadata': {'schema_version': RAWDATA_SCHEMA_VERSION,
                     'shape': [], 'rawdata_name': 'response'},
    }),)
    return JobResult(
        job_name=job.name, job_dir=job.directory,
        status='error' if failed else 'done',
        unnormalized_variables=job.unnormalized_variables,
        normalized_variables=job.normalized_variables,
        raw_data_items=raw,
        metadata={'population_index': index, 'generation_index': 0, 'run_id': 'parallel'},
    )

api.prepare_job = delayed_prepare
api.run_local_job = execute
rows = tuple((index / 7.0,) for index in range(8))
costs = api.evaluate_population(
    root, rows, mode='local', local_max_workers=4, timeout_sec=5.0,
    run_id='parallel', generation_index=0,
)
assert marker.exists()
assert len(costs) == 8
for index, cost in enumerate(costs):
    if index in (1, 5):
        assert math.isinf(cost[0])
    else:
        assert cost == ((2.0 * rows[index][0] - 1.0) ** 2,)
records = recorded_api.list_records(root)
assert len(records) == 8 and len({r['job_name'] for r in records}) == 8
assert sorted(r['status'] for r in records) == ['completed'] * 6 + ['error'] * 2
for job in (root / 'jobs').iterdir():
    metadata = json.loads((job / 'metadata.json').read_text(encoding='utf-8'))
    assert metadata['job_static_hash'] == prepared_job_static_hash(job)
print('parallel mixed batch completed with eight durable results')
'''


def test_local_finalization_overlaps_later_job_preparation_without_deadlock(tmp_path: Path) -> None:
    # A regression must terminate rather than hang pytest's worker threads.
    completed = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(_PARALLEL_CHILD), str(tmp_path / "workspace")],
        capture_output=True, text=True, timeout=40.0,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "eight durable results" in completed.stdout


def test_parameter_template_failure_remains_one_durable_error_per_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from yadof.evaluate_manager import api

    root = tmp_path / "workspace"
    init_workspace(root)

    def fail_template(_workspace):
        raise ValueError("injected parameter preparation failure")

    monkeypatch.setattr(api, "freeze_job_parameters", fail_template)
    costs = evaluate_population(root, ((0.1,), (0.5,), (0.9,)), mode="local", local_max_workers=2)
    assert costs == ((math.inf,),) * 3
    records = recorded_api.list_records(root)
    assert len(records) == 3
    assert len({record["job_name"] for record in records}) == 3
    for record in records:
        assert record["status"] == "error"
        assert record["job_metadata"]["failure_stage"] == "prepare"
        assert record["job_metadata"]["error_type"] == "ValueError"
