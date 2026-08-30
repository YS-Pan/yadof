from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import time
import zipfile

import numpy as np
import pytest

from yadof.config import load_config
from yadof.evaluate_manager.finalizer import (
    ResultFinalizationCoordinator,
    finalize_result,
)
from yadof.evaluate_manager import evaluate_population
from yadof.evaluate_manager.types import JobResult
from yadof.job_template import RAWDATA_SCHEMA_VERSION, NamedRawDataItem
from yadof.job_template import api as job_template_api
from yadof.recorded_data.paths import recorded_data_paths
from yadof.recorded_data.records import build_owned_envelope
from yadof.recorded_data.segment_store import discover_catalog
from yadof.recorded_data.session import CampaignSession, RecordingError
from yadof.workspace.init import init_workspace


def _workspace(path: Path) -> Path:
    init_workspace(path)
    return path


def _payload(value: float) -> dict[str, object]:
    values = np.asarray(value, dtype=np.float64)
    return {
        "values": values,
        "metadata": {
            "schema_version": RAWDATA_SCHEMA_VERSION,
            "shape": list(values.shape),
            "rawdata_name": "response",
        },
    }


def _result(index: int, value: float, *, status: str = "done") -> JobResult:
    return JobResult(
        job_name=f"candidate_0_{index}",
        job_dir=None,
        status=status,
        unnormalized_variables=(value,),
        normalized_variables=((value + 1.0) / 2.0,),
        raw_data_items=(
            (NamedRawDataItem("response.npz", _payload(abs(value))),)
            if status == "done"
            else ()
        ),
        metadata={
            "evaluation_engine": "test",
            "run_id": "stage1-test",
            "optimization_index": 0,
            "generation_index": 0,
            "population_index": index,
        },
    )


def _write_cost(root: Path, statement: str) -> None:
    (root / "submit/calc_cost.py").write_text(
        "def calculate_cost(sample_rawdata, raw_variables=None):\n"
        f"    {statement}\n"
        "def get_objective_names():\n"
        "    return ('response_error',)\n"
        "def get_objective_count():\n"
        "    return 1\n",
        encoding="utf-8",
        newline="\n",
    )


def test_group_commit_precedes_ordered_cost_and_result_exposure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _workspace(tmp_path / "workspace")
    config = load_config(
        root,
        overrides={
            "HISTORY_SEGMENT_MAX_CANDIDATES": 3,
            "HISTORY_UNPUBLISHED_MAX_CANDIDATES": 6,
        },
    )
    session = CampaignSession(config)
    snapshot = session.begin_generation(config)
    interpreted: list[int] = []
    exposed: list[int] = []
    real_calculate = job_template_api.CostInterpreter.calculate_costs

    def observed_calculate(self, samples, raw_variables=None):
        assert raw_variables is not None
        index = int(round((float(raw_variables[0][0]) + 0.9) / 0.9))
        records = {str(row["job_name"]): row for row in session.records()}
        record = records[f"candidate_0_{index}"]
        assert record["evidence_state"] == "committed"
        assert record["publication_receipt"]["state"] == "committed"
        interpreted.append(index)
        return real_calculate(self, samples, raw_variables)

    monkeypatch.setattr(
        job_template_api.CostInterpreter,
        "calculate_costs",
        observed_calculate,
    )
    coordinator = ResultFinalizationCoordinator(
        session,
        snapshot,
        expected_count=3,
        on_finalized=lambda index, _result: exposed.append(index),
    )
    try:
        coordinator.accept(2, _result(2, 0.9))
        coordinator.accept(0, _result(0, -0.9))
        assert interpreted == []
        coordinator.accept(1, _result(1, 0.0))
        finalized = coordinator.finish()
        assert interpreted == [0, 1, 2]
        assert exposed == [0, 1, 2]
        assert [result.job_name for result in finalized] == [
            "candidate_0_0",
            "candidate_0_1",
            "candidate_0_2",
        ]
        records = session.records()
        assert {row["publication_receipt"]["group_id"] for row in records} == {
            records[0]["publication_receipt"]["group_id"]
        }
        assert all(row["interpretation_state"] == "succeeded" for row in records)
    finally:
        session.close()

    (segment,) = root.glob("recorded_data/segments/*/*/segment_*.zip")
    with zipfile.ZipFile(segment) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["candidate_count"] == 3


@pytest.mark.parametrize(
    ("statement", "error_type"),
    [
        ("raise RuntimeError('injected cost failure')", "RuntimeError"),
        ("return (1.0, 2.0)", "CostObjectiveWidthError"),
        ("return (float('nan'),)", "CostNonFiniteError"),
        ("return (float('inf'),)", "CostNonFiniteError"),
        ("return (float('-inf'),)", "CostNonFiniteError"),
    ],
)
def test_interpretation_failure_preserves_completed_evidence_for_replay(
    tmp_path: Path,
    statement: str,
    error_type: str,
) -> None:
    root = _workspace(tmp_path / "workspace")
    _write_cost(root, statement)
    config = load_config(root)
    session = CampaignSession(config)
    first_snapshot = session.begin_generation(config)
    try:
        finalized = finalize_result(session, first_snapshot, _result(0, 0.25))
        assert finalized.status == "error"
        assert finalized.costs is None
        assert finalized.metadata["failure_stage"] == "cost_interpretation"
        assert finalized.metadata["error_type"] == error_type

        (live,) = session.records()
        assert live["status"] == "completed"
        assert live["evidence_state"] == "committed"
        assert live["interpretation_state"] == "failed"
        (durable,) = discover_catalog(
            recorded_data_paths(first_snapshot.config.workspace)
        ).references
        assert durable.record["status"] == "completed"
        assert durable.rawdata_members

        _write_cost(
            root,
            "return (float(sample_rawdata[0]['values']),)",
        )
        second_snapshot = session.begin_generation(load_config(root))
        replayed = session.historical_results(second_snapshot)
        assert len(replayed) == 1
        assert replayed[0][0] == "candidate_0_0"
        assert np.isfinite(replayed[0][2][0])
    finally:
        session.close()


def test_optimizer_adapter_returns_objective_width_inf_for_cost_failure(
    tmp_path: Path,
) -> None:
    root = _workspace(tmp_path / "workspace")
    _write_cost(root, "raise RuntimeError('adapter cost failure')")
    costs = evaluate_population(
        root,
        ((0.25,),),
        mode="local",
        timeout_sec=5.0,
        local_max_workers=1,
    )
    assert len(costs) == 1
    assert len(costs[0]) == 1
    assert np.isinf(costs[0][0])
    (reference,) = discover_catalog(recorded_data_paths(root)).references
    assert reference.record["status"] == "completed"
    assert reference.rawdata_members


def test_execution_rawdata_and_interpretation_states_are_independent(
    tmp_path: Path,
) -> None:
    root = _workspace(tmp_path / "workspace")
    config = load_config(root)
    session = CampaignSession(config)
    snapshot = session.begin_generation(config)
    invalid = _result(0, 0.1)
    invalid = JobResult(
        job_name=invalid.job_name,
        job_dir=None,
        status="done",
        unnormalized_variables=invalid.unnormalized_variables,
        normalized_variables=invalid.normalized_variables,
        raw_data_items=(
            NamedRawDataItem("response.npz", {"values": np.asarray(0.1)}),
        ),
        metadata=invalid.metadata,
    )
    coordinator = ResultFinalizationCoordinator(
        session,
        snapshot,
        expected_count=2,
    )
    try:
        coordinator.accept(1, _result(1, 0.2, status="timeout"))
        coordinator.accept(0, invalid)
        invalid_finalized, timeout_finalized = coordinator.finish()
        assert invalid_finalized.status == "error"
        assert invalid_finalized.metadata["failure_stage"] == "rawdata_validation"
        assert timeout_finalized.status == "timeout"
        records = {str(row["job_name"]): row for row in session.records()}
        assert records["candidate_0_0"]["status"] == "error"
        assert records["candidate_0_0"]["interpretation_state"] == "not_applicable"
        assert records["candidate_0_1"]["status"] == "timeout"
        assert records["candidate_0_1"]["interpretation_state"] == "not_applicable"
    finally:
        session.close()


def test_failed_retained_group_wakes_every_receipt(tmp_path: Path, monkeypatch) -> None:
    from yadof.recorded_data import session as session_module

    root = _workspace(tmp_path / "workspace")

    def fail_publish(*_args, **_kwargs):
        raise OSError("injected group publication failure")

    monkeypatch.setattr(session_module, "publish_segment", fail_publish)
    config = load_config(
        root,
        overrides={
            "HISTORY_SEGMENT_MAX_CANDIDATES": 3,
            "HISTORY_UNPUBLISHED_MAX_CANDIDATES": 4,
            "HISTORY_WRITER_MAX_CONSECUTIVE_FAILURES": 1,
        },
    )
    session = CampaignSession(config)
    snapshot = session.begin_generation(config)
    receipts = []
    for index in range(3):
        result = _result(index, index / 10.0)
        envelope = build_owned_envelope(
            snapshot.config.workspace,
            result.job_name,
            result.unnormalized_variables,
            result.raw_data_items,
            result.metadata,
        )
        receipts.append(session.submit_evidence(envelope, group_id="failed-group"))
    with pytest.raises(RecordingError, match="no later evaluation may proceed"):
        session.flush_boundary()
    for receipt in receipts:
        assert receipt.state == "failed"
        with pytest.raises(RecordingError, match="publication failed"):
            receipt.wait_committed(0.1)
    assert session.counters()["receipts_failed"] == 3
    with pytest.raises(RecordingError, match="before all evidence could be published"):
        session.close()


def _child_finalizer_source(root: Path) -> str:
    return (
        "from pathlib import Path\n"
        "import numpy as np\n"
        "from yadof.config import load_config\n"
        "from yadof.evaluate_manager.finalizer import finalize_result\n"
        "from yadof.evaluate_manager.types import JobResult\n"
        "from yadof.job_template import NamedRawDataItem, RAWDATA_SCHEMA_VERSION\n"
        "from yadof.recorded_data.session import CampaignSession\n"
        f"root = Path({str(root)!r})\n"
        "config = load_config(root, overrides={'HISTORY_SEGMENT_MAX_CANDIDATES': 1})\n"
        "session = CampaignSession(config)\n"
        "snapshot = session.begin_generation(config)\n"
        "values = np.asarray(0.4, dtype=np.float64)\n"
        "result = JobResult(job_name='candidate_0_0', job_dir=None, status='done', "
        "unnormalized_variables=(0.2,), normalized_variables=(0.6,), "
        "raw_data_items=(NamedRawDataItem('response.npz', {'values': values, "
        "'metadata': {'schema_version': RAWDATA_SCHEMA_VERSION, 'shape': [], "
        "'rawdata_name': 'response'}}),), metadata={'run_id': 'child', "
        "'generation_index': 0, 'population_index': 0})\n"
        "finalize_result(session, snapshot, result)\n"
    )


@pytest.mark.parametrize("action", ["exit", "hang"])
def test_process_loss_after_commit_preserves_recoverable_evidence(
    tmp_path: Path,
    action: str,
) -> None:
    root = _workspace(tmp_path / "workspace")
    marker = tmp_path / f"cost-{action}.marker"
    terminal = "import os; os._exit(91)" if action == "exit" else "import time; time.sleep(60)"
    _write_cost(
        root,
        f"from pathlib import Path; Path({str(marker)!r}).write_text('entered'); {terminal}",
    )
    child = tmp_path / f"cost-{action}-child.py"
    child.write_text(_child_finalizer_source(root), encoding="utf-8", newline="\n")
    process = subprocess.Popen([sys.executable, str(child)])
    if action == "exit":
        assert process.wait(timeout=10.0) == 91
    else:
        deadline = time.monotonic() + 10.0
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert marker.exists()
        process.terminate()
        process.wait(timeout=10.0)
    assert marker.read_text(encoding="utf-8") == "entered"
    catalog = discover_catalog(recorded_data_paths(root))
    assert len(catalog.references) == 1
    assert catalog.references[0].record["status"] == "completed"
    assert catalog.references[0].rawdata_members
    recovered = CampaignSession(load_config(root))
    try:
        recovered.begin_generation(load_config(root))
        samples = recovered.named_rawdata_samples(status="completed")
        assert len(samples) == 1
        assert samples[0][0] == "candidate_0_0"
    finally:
        recovered.close()


def test_process_loss_after_enqueue_does_not_claim_commit(tmp_path: Path) -> None:
    root = _workspace(tmp_path / "workspace")
    marker = tmp_path / "receipt-state.marker"
    child = tmp_path / "enqueue-child.py"
    child.write_text(
        "from pathlib import Path\n"
        "import os, time\n"
        "import numpy as np\n"
        "from yadof.config import load_config\n"
        "from yadof.job_template import NamedRawDataItem, RAWDATA_SCHEMA_VERSION\n"
        "from yadof.recorded_data.records import build_owned_envelope\n"
        "from yadof.recorded_data.session import CampaignSession\n"
        "from yadof.recorded_data import session as session_module\n"
        f"root = Path({str(root)!r})\n"
        f"marker = Path({str(marker)!r})\n"
        "session_module.publish_segment = lambda *_args, **_kwargs: time.sleep(60)\n"
        "config = load_config(root, overrides={'HISTORY_SEGMENT_MAX_CANDIDATES': 1})\n"
        "session = CampaignSession(config)\n"
        "values = np.asarray(0.4, dtype=np.float64)\n"
        "item = NamedRawDataItem('response.npz', {'values': values, 'metadata': "
        "{'schema_version': RAWDATA_SCHEMA_VERSION, 'shape': [], "
        "'rawdata_name': 'response'}})\n"
        "envelope = build_owned_envelope(config.workspace, 'candidate_0_0', (0.2,), "
        "(item,), {'run_id': 'child', 'generation_index': 0})\n"
        "receipt = session.submit_evidence(envelope, group_id='enqueue-only')\n"
        "marker.write_text(receipt.state, encoding='utf-8')\n"
        "os._exit(92)\n",
        encoding="utf-8",
        newline="\n",
    )
    completed = subprocess.run([sys.executable, str(child)], timeout=10.0)
    assert completed.returncode == 92
    assert marker.read_text(encoding="utf-8") == "pending"
    assert discover_catalog(recorded_data_paths(root)).references == ()
    recovered = CampaignSession(load_config(root))
    recovered.close()
