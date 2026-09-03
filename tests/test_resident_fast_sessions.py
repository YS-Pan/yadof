"""Observable lifecycle, invalidation and numerical independence of resident fast."""

import json
import math

import psutil
import pytest

from yadof.config import load_config
from yadof.evaluate_manager import evaluate_population
from yadof.job_template import validate_fast_task
from yadof.recorded_data import list_records
from yadof.recorded_data.session import CampaignSession
from yadof.workspace.init import init_workspace


TASK = '''
import json, os, uuid
from pathlib import Path
import numpy as np
from model import SCALE
YADOF_FAST_API = "yadof.fast.session/v1"
class PhysicsFailure(RuntimeError): pass
PHYSICAL_FAILURE_TYPES = (PhysicsFailure,)
MODULE_TOKEN = uuid.uuid4().hex
class Session:
    def __init__(self, context):
        self.marker = Path(context["environment"]["SESSION_EVENTS"])
        self.calls = 0
        self.mark("create")
    def mark(self, event):
        with self.marker.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"event": event, "pid": os.getpid(), "module": MODULE_TOKEN}) + "\\n")
    def evaluate_rawdata(self, parameters, context):
        self.calls += 1
        value = float(parameters["input_value"])
        if value > .8: raise PhysicsFailure("declared geometry failure")
        return {"response.npz": {"values": np.asarray(SCALE * value),
            "metadata": json.dumps({"schema_version": 1, "shape": [], "rawdata_name": "response"})}}, {
            "calls": self.calls, "module": MODULE_TOKEN}
    def close(self): self.mark("close")
def create_evaluation_session(context): return Session(context)
'''


def test_resident_reuse_aba_failure_cost_reload_and_simulation_invalidation(tmp_path):
    root = tmp_path / "task"
    init_workspace(root)
    (root / "job_template/parameters_constraints.py").write_text(
        "from yadof.job_template import Parameter\nPARAMETERS=(Parameter('input_value', ((0., 1.),)),)\nCONSTRAINTS=()\ndef get_parameters(): return PARAMETERS\n",
        encoding="utf-8")
    (root / "config.py").write_text("EVALUATION_MODE='fast'\nFAST_EVALUATION_MAX_WORKERS=1\nEVALUATION_TIMEOUT_SEC=5\n", encoding="utf-8")
    (root / "job_template/evaluation.py").write_text(TASK, encoding="utf-8")
    model = root / "job_template/model.py"
    model.write_text("SCALE=1\n", encoding="utf-8")
    cost = root / "submit/calc_cost.py"
    cost.write_text('''FACTOR=1
def get_objective_names(): return ("value",)
def calculate_cost(items, raw_variables=None): return (FACTOR * float(items[0]["values"]),)
''', encoding="utf-8")
    marker = tmp_path / "events.jsonl"
    session = CampaignSession(load_config(root))
    populations = (((.2,), (.7,), (.2,), (.9,), (.2,)), ((.2,),) * 5,
                   ((.2,),) * 5, ((.2,),) * 5)
    try:
        outcomes = []
        for generation, population in enumerate(populations):
            if generation == 1:
                cost.write_text(cost.read_text().replace("FACTOR=1", "FACTOR=2"), encoding="utf-8")
            elif generation == 2:
                model.write_text("SCALE=2\n", encoding="utf-8")
            elif generation == 3:
                with (root / "config.py").open("a", encoding="utf-8") as stream:
                    stream.write("EVALUATION_TIMEOUT_SEC=6\n")
            snapshot = session.begin_generation(load_config(root))
            outcomes.append(evaluate_population(root, population, generation_index=generation,
                env={"SESSION_EVENTS": str(marker)}, _campaign_session=session, _task_snapshot=snapshot))
            session.finish_generation()
        assert outcomes[0][0] == outcomes[0][2] == outcomes[0][4] == (.2,)
        assert math.isinf(outcomes[0][3][0])
        assert outcomes[1][0] == (.4,)
        assert outcomes[2][0] == outcomes[3][0] == (.8,)
        records = sorted(list_records(root), key=lambda r: (r["generation_index"], r["population_index"]))
        pids = [records[index]["job_metadata"]["fast_worker_pid"] for index in (0, 5, 10, 15)]
        assert pids[0] == pids[1]
        assert len({pids[0], pids[2], pids[3]}) == 3
        assert records[4]["job_metadata"]["task_diagnostics"]["calls"] == 5
        assert records[9]["job_metadata"]["task_diagnostics"]["calls"] == 10
        assert len(records) == 20
    finally:
        session.close()
    events = [json.loads(line) for line in marker.read_text().splitlines()]
    assert [e["event"] for e in events] == ["create", "close"] * 3
    assert not any(psutil.pid_exists(pid) for pid in pids)
    assert not list((root / ".yadof/fast_scratch").glob("*"))


def test_legacy_fast_entry_is_rejected_without_constructing_a_session(tmp_path):
    init_workspace(tmp_path)
    evaluation = tmp_path / "job_template/evaluation.py"
    evaluation.write_text("def evaluate_rawdata(parameters, context): return {}\n", encoding="utf-8")
    with pytest.raises(TypeError, match="migration_0_6"):
        validate_fast_task(tmp_path)
    evaluation.write_text('''YADOF_FAST_API="yadof.fast.session/v1"
def create_evaluation_session(context): raise AssertionError("check must not create resources")
''', encoding="utf-8")
    assert validate_fast_task(tmp_path) == evaluation


def test_idle_crashed_worker_is_replaced_at_next_generation(tmp_path):
    init_workspace(tmp_path)
    config = load_config(tmp_path, overrides={"EVALUATION_MODE": "fast", "FAST_EVALUATION_MAX_WORKERS": 1})
    session = CampaignSession(config)
    try:
        snapshot = session.begin_generation(config)
        first = evaluate_population(tmp_path, ((.25,),), generation_index=0,
            _campaign_session=session, _task_snapshot=snapshot)
        record = list_records(tmp_path)[0]
        pid = record["job_metadata"]["fast_worker_pid"]
        process = psutil.Process(pid)
        process.kill()
        process.wait(timeout=5)
        snapshot = session.begin_generation(config)
        second = evaluate_population(tmp_path, ((.25,),), generation_index=1,
            _campaign_session=session, _task_snapshot=snapshot)
        assert first == second
        records = sorted(list_records(tmp_path), key=lambda row: row["generation_index"])
        assert records[1]["job_metadata"]["fast_worker_pid"] != pid
    finally:
        session.close()
