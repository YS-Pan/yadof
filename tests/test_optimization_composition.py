from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest

from yadof.config import DEFAULT_CONFIG, load_config
from yadof.optimize import run_one_generation
from yadof.optimize.state import read_active_strategy_state
from yadof.optimize.strategy import load_workspace_strategy
from yadof.recorded_data.session import CampaignSession
from yadof.workspace.check import check_workspace
from yadof.workspace.init import init_workspace


def _small_workspace(root: Path) -> Path:
    init_workspace(root)
    (root / "config.py").write_text(
        'EVALUATION_MODE = "local"\n'
        "OPTIMIZE_POPULATION_SIZE = 2\n"
        "OPTIMIZE_SURROGATE_ALPHA = 1\n"
        "OPTIMIZE_SURROGATE_BETA = 0\n"
        "OPTIMIZE_SMOKE_TEST_ENABLED = False\n",
        encoding="utf-8",
    )
    return root


def test_public_parent_imports_are_lazy_and_config_has_no_second_selector() -> None:
    command = (
        "import json, sys; import yadof.optimize, yadof.surrogate; "
        "names=('torch','pymoo.algorithms','matplotlib','tkinter'); "
        "print(json.dumps([name for name in names if name in sys.modules]))"
    )
    completed = subprocess.run(
        [sys.executable, "-I", "-c", command],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert json.loads(completed.stdout) == []
    assert not {
        "OPTIMIZATION_METHOD",
        "OPTIMIZE_METHOD",
        "SURROGATE_METHOD",
        "SEARCH_BACKEND",
    } & set(DEFAULT_CONFIG)


def test_default_composition_dispatches_ga_and_nsga3_by_objective_count(
    tmp_path: Path,
) -> None:
    single = _small_workspace(tmp_path / "default-single")
    single_result = run_one_generation(single, generation_index=0, random_seed=31)

    multi = _small_workspace(tmp_path / "default-multi")
    (multi / "submit/calc_cost.py").write_text(
        "def calculate_cost(sample_rawdata, raw_variables=None):\n"
        "    value = float(sample_rawdata[0]['values'])\n"
        "    return (value, 1.0 - value)\n"
        "def get_objective_names():\n"
        "    return ('response', 'inverse_response')\n",
        encoding="utf-8",
    )
    multi_result = run_one_generation(multi, generation_index=0, random_seed=31)

    assert single_result.diagnostics["strategy_identity"]["strategy"] == "gpsaf"
    assert single_result.diagnostics["backend_algorithm"] == "ga"
    assert multi_result.diagnostics["strategy_identity"]["strategy"] == "gpsaf"
    assert multi_result.diagnostics["backend_algorithm"] == "nsga3"


def test_real_multiobjective_nsga3_strategy_runs_without_surrogate(
    tmp_path: Path,
) -> None:
    root = _small_workspace(tmp_path / "multiobjective")
    (root / "submit/calc_cost.py").write_text(
        "def calculate_cost(sample_rawdata, raw_variables=None):\n"
        "    value = float(sample_rawdata[0]['values'])\n"
        "    return (value, 1.0 - value)\n"
        "def get_objective_names():\n"
        "    return ('response', 'inverse_response')\n",
        encoding="utf-8",
    )
    (root / "submit/optimization.py").write_text(
        "from yadof.optimize import pymoo_nsga3, real_search\n"
        "def build_optimization():\n"
        "    return real_search(search=pymoo_nsga3())\n",
        encoding="utf-8",
    )

    report = check_workspace(root)
    result = run_one_generation(
        root,
        generation_index=0,
        population_size=2,
        random_seed=41,
    )

    assert report.ok, report.format()
    assert len(result.population) == 2
    assert all(len(row) == 2 for row in result.costs)
    assert result.diagnostics["strategy_identity"]["strategy"] == "real-search"
    assert result.diagnostics["backend_algorithm"] == "nsga3"
    assert result.surrogate_used is False
    assert not (root / ".yadof/surrogate/checkpoints").exists()


def test_check_rejects_nsga3_for_one_objective_without_runtime_mutation(
    tmp_path: Path,
) -> None:
    root = _small_workspace(tmp_path / "invalid-nsga3")
    (root / "submit/optimization.py").write_text(
        "from yadof.optimize import pymoo_nsga3, real_search\n"
        "def build_optimization():\n"
        "    return real_search(search=pymoo_nsga3())\n",
        encoding="utf-8",
    )

    report = check_workspace(root)

    assert not report.ok
    assert "NSGA-III requires at least two objectives" in report.format()
    assert not (root / "jobs").exists()
    assert not (root / ".yadof/optimization").exists()
    assert not (root / ".yadof/surrogate/checkpoints").exists()


def test_strategy_switch_retains_inactive_namespace_and_can_return(
    tmp_path: Path,
) -> None:
    root = _small_workspace(tmp_path / "switch")
    optimization_path = root / "submit/optimization.py"
    default_source = optimization_path.read_text(encoding="utf-8")

    first = run_one_generation(root, generation_index=0, random_seed=17)
    first_state = read_active_strategy_state(root)
    assert first_state is not None
    retained = (
        root
        / ".yadof/surrogate/checkpoints/runs"
        / first_state.strategy_namespace
        / "components/conditional-inr/retained.txt"
    )
    retained.parent.mkdir(parents=True, exist_ok=True)
    retained.write_text("inactive evidence\n", encoding="utf-8")

    optimization_path.write_text(
        "from yadof.optimize import pymoo_ga, real_search\n"
        "def build_optimization():\n"
        "    return real_search(search=pymoo_ga())\n",
        encoding="utf-8",
    )
    second = run_one_generation(root, generation_index=1, random_seed=17)
    second_state = read_active_strategy_state(root)
    assert second_state is not None
    assert second_state.strategy_signature != first_state.strategy_signature
    assert retained.read_text(encoding="utf-8") == "inactive evidence\n"

    optimization_path.write_text(default_source, encoding="utf-8")
    third = run_one_generation(root, generation_index=2, random_seed=17)
    third_state = read_active_strategy_state(root)
    assert third_state is not None
    assert third_state.strategy_signature == first_state.strategy_signature
    assert first.diagnostics["strategy_signature"] == third.diagnostics[
        "strategy_signature"
    ]
    assert second.diagnostics["strategy_signature"] != third.diagnostics[
        "strategy_signature"
    ]
    active_payload = json.loads(
        (root / ".yadof/optimization/active.json").read_text(encoding="utf-8")
    )
    assert active_payload["strategy_namespace"] == first_state.strategy_namespace


def test_real_strategy_switch_does_not_require_optional_surrogate_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import yadof.surrogate.api as surrogate_api

    root = _small_workspace(tmp_path / "core-only-switch")
    (root / "submit/optimization.py").write_text(
        "from yadof.optimize import pymoo_ga, real_search\n"
        "def build_optimization():\n"
        "    return real_search(search=pymoo_ga())\n",
        encoding="utf-8",
    )
    first = run_one_generation(root, generation_index=0, random_seed=13)

    def missing_optional_backend(_workspace):
        raise ImportError("synthetic missing Torch runtime")

    monkeypatch.setattr(
        surrogate_api,
        "deactivate_workspace",
        missing_optional_backend,
    )
    config_path = root / "config.py"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "OPTIMIZE_POPULATION_SIZE = 2",
            "OPTIMIZE_POPULATION_SIZE = 3",
        ),
        encoding="utf-8",
    )
    second = run_one_generation(root, generation_index=1, random_seed=13)

    assert len(second.population) == 3
    assert first.diagnostics["strategy_signature"] != second.diagnostics[
        "strategy_signature"
    ]


def test_strategy_deactivation_waits_for_pending_component_training(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from yadof.surrogate.conditional_inr import runtime, scheduler

    root = _small_workspace(tmp_path / "pending-switch")
    training_started = threading.Event()
    release_training = threading.Event()
    deactivation_done = threading.Event()
    outcome: list[object] = []

    def fake_train_with_config(_config, *, generation_index, **_kwargs):
        training_started.set()
        assert release_training.wait(timeout=5.0)
        return SimpleNamespace(generation_index=int(generation_index))

    monkeypatch.setattr(runtime, "train_with_config", fake_train_with_config)
    monkeypatch.setattr(runtime, "_is_usable_state", lambda _state: False)
    monkeypatch.setattr(runtime, "reset_workspace_state", lambda _workspace: None)

    started = scheduler.start_training(root, generation_index=4, block=False)
    assert started.action == "started"
    assert training_started.wait(timeout=5.0)

    def deactivate() -> None:
        outcome.append(scheduler.deactivate_workspace(root))
        deactivation_done.set()

    worker = threading.Thread(target=deactivate)
    worker.start()
    try:
        assert not deactivation_done.wait(timeout=0.1)
        release_training.set()
        worker.join(timeout=5.0)
        assert not worker.is_alive()
        assert deactivation_done.is_set()
        assert outcome[0].action == "deactivated"
        assert outcome[0].pending_generation_index is None
        assert outcome[0].latest_completed_generation_index is None
        assert scheduler.wait_for_pending_training(root).action == "idle"
    finally:
        release_training.set()
        worker.join(timeout=5.0)


def test_generation_snapshot_freezes_both_complete_source_roots(
    tmp_path: Path,
) -> None:
    root = _small_workspace(tmp_path / "snapshot")
    config = load_config(root)
    session = CampaignSession(config)
    try:
        first = session.begin_generation(config)
        first_definition = load_workspace_strategy(
            first.config.workspace,
            config=first.config,
        )
        (root / "submit/optimization.py").write_text(
            "from yadof.optimize import pymoo_ga, real_search\n"
            "def build_optimization():\n"
            "    return real_search(search=pymoo_ga())\n",
            encoding="utf-8",
        )
        second = session.begin_generation(load_config(root))
        second_definition = load_workspace_strategy(
            second.config.workspace,
            config=second.config,
        )
        optimization_path = root / "submit/optimization.py"
        optimization_path.write_text(
            optimization_path.read_text(encoding="utf-8")
            + "\n# provenance-only source edit\n",
            encoding="utf-8",
        )
        third = session.begin_generation(load_config(root))
        third_definition = load_workspace_strategy(
            third.config.workspace,
            config=third.config,
        )

        assert first_definition.identity["strategy"] == "gpsaf"
        assert second_definition.identity["strategy"] == "real-search"
        assert first_definition.signature != second_definition.signature
        assert first.optimization_fingerprint != second.optimization_fingerprint
        assert second_definition.signature == third_definition.signature
        assert second.optimization_fingerprint != third.optimization_fingerprint
        assert "submit/optimization.py" in first.source_hashes
        assert "job_template/workflow.py" in first.source_hashes
        assert first.submit_directory.parent == first.snapshot_root
        assert first.job_template_directory.parent == first.snapshot_root
    finally:
        session.close()
