from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
import yadof

from yadof.cli import main as cli_main
from yadof.recorded_data import list_optimization_metadata
from yadof.workspace.init import init_workspace


@pytest.fixture(autouse=True)
def _source_package_for_worker_processes(monkeypatch: pytest.MonkeyPatch) -> None:
    package_parent = Path(yadof.__file__).resolve().parents[1]
    inherited = os.environ.get("PYTHONPATH", "")
    value = str(package_parent)
    if inherited:
        value += os.pathsep + inherited
    monkeypatch.setenv("PYTHONPATH", value)


def _workspace(tmp_path: Path, *, smoke: bool = False) -> Path:
    root = tmp_path / "workspace"
    init_workspace(root)
    (root / "config.py").write_text(
        'EVALUATION_MODE = "local"\n'
        "OPTIMIZE_POPULATION_SIZE = 2\n"
        f"OPTIMIZE_SMOKE_TEST_ENABLED = {smoke!r}\n",
        encoding="utf-8",
    )
    (root / "submit/optimization.py").write_text(
        "from yadof.optimize import by_objective_count, gpsaf, pymoo_ga, pymoo_nsga3\n"
        "from yadof.surrogate import conditional_inr\n"
        "def build_optimization():\n"
        "    search = by_objective_count(single=pymoo_ga(), multi=pymoo_nsga3())\n"
        "    return gpsaf(search=search, surrogate=conditional_inr(), alpha=1, beta=0)\n",
        encoding="utf-8",
    )
    return root


def _result(generation: int, costs=((0.25,),)):
    return SimpleNamespace(
        generation_index=generation,
        source="real",
        surrogate_used=False,
        history_count=0,
        costs=costs,
    )


def test_run_cli_defaults_to_fifty_generations():
    parser = __import__("yadof.cli", fromlist=["build_parser"]).build_parser()
    run_parser = parser._subparsers._group_actions[0].choices["run"]

    defaults = parser.parse_args(["run"])
    assert defaults.generations == 50
    assert defaults.progress is True
    assert parser.parse_args(["run", "--no-progress"]).progress is False
    assert "default: 50" in run_parser.format_help()
    assert "--no-progress" in run_parser.format_help()


def test_run_cli_direct_start_and_resume_use_workspace_metadata(tmp_path, capsys):
    workspace = _workspace(tmp_path)
    assert cli_main(
        [
            "run",
            "--workspace",
            str(workspace),
            "--generations",
            "1",
            "--start-generation",
            "3",
            "--population-size",
            "2",
            "--no-smoke-test",
        ]
    ) == 0
    assert "gen=3" in capsys.readouterr().out

    assert cli_main(
        [
            "run",
            "--workspace",
            str(workspace),
            "--generations",
            "1",
            "--start-generation",
            "4",
            "--population-size",
            "2",
            "--no-smoke-test",
        ]
    ) == 0
    rows = list_optimization_metadata(workspace)
    assert [row["generation_index"] for row in rows] == [3, 4]


def test_run_cli_smoke_default_and_both_explicit_overrides(
    tmp_path, monkeypatch, capsys
):
    from yadof import run_command

    workspace = _workspace(tmp_path, smoke=True)
    events: list[str] = []
    monkeypatch.setattr(
        run_command,
        "run_smoke_test",
        lambda *_args, **_kwargs: events.append("smoke") or ((0.1,),),
    )
    monkeypatch.setattr(
        run_command,
        "run_generations",
        lambda *_args, **_kwargs: events.append("generations") or (_result(0),),
    )

    base = ["run", "--workspace", str(workspace)]
    assert cli_main(base) == 0
    assert events == ["smoke", "generations"]
    capsys.readouterr()

    events.clear()
    assert cli_main(base + ["--no-smoke-test"]) == 0
    assert events == ["generations"]
    assert "CLI override" in capsys.readouterr().out

    events.clear()
    config_file = workspace / "config.py"
    config_file.write_text(
        config_file.read_text(encoding="utf-8").replace(
            "OPTIMIZE_SMOKE_TEST_ENABLED = True",
            "OPTIMIZE_SMOKE_TEST_ENABLED = False",
        ),
        encoding="utf-8",
    )
    assert cli_main(base + ["--smoke-test"]) == 0
    assert events == ["smoke", "generations"]


def test_run_cli_stops_before_generation_when_smoke_has_no_finite_cost(
    tmp_path, monkeypatch, capsys
):
    from yadof import run_command

    workspace = _workspace(tmp_path, smoke=True)
    monkeypatch.setattr(
        run_command, "run_smoke_test", lambda *_args, **_kwargs: ((float("inf"),),)
    )
    monkeypatch.setattr(
        run_command,
        "run_generations",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("generation must not start")
        ),
    )

    assert cli_main(["run", "--workspace", str(workspace)]) == 1
    assert "optimization was not started" in capsys.readouterr().err


def test_run_cli_passes_mode_progress_and_strict_failure_options(
    tmp_path, monkeypatch
):
    from yadof import run_command

    workspace = _workspace(tmp_path)
    seen = {}

    def fake_run(*_args, **kwargs):
        seen.update(kwargs)
        assert os.environ["YADOF_PROGRESS"] == "1"
        return (_result(7),)

    monkeypatch.setattr(run_command, "run_generations", fake_run)
    monkeypatch.delenv("YADOF_PROGRESS", raising=False)
    assert cli_main(
        [
            "run",
            "--workspace",
            str(workspace),
            "--mode",
            "distributed",
            "--start-generation",
            "7",
            "--no-smoke-test",
            "--fail-on-all-infinite",
        ]
    ) == 0
    assert seen["config_overrides"] == {"EVALUATION_MODE": "distributed"}
    assert seen["fail_on_all_infinite"] is True
    assert "YADOF_PROGRESS" not in os.environ


def test_population_progress_reports_generation_outcomes(
    monkeypatch, capsys
):
    from yadof.evaluate_manager.api import _PopulationProgress

    monkeypatch.setenv("YADOF_PROGRESS", "1")
    progress = _PopulationProgress(total=3, mode="local", generation_index=7)
    progress.start()
    progress.complete(2, successful=True)
    progress.complete(0, successful=False)
    progress.complete(1, successful=True)
    progress.close()

    lines = capsys.readouterr().err.splitlines()
    assert len(lines) == 4
    assert "generation 7 (local)" in lines[-1]
    assert "3/3" in lines[-1]
    assert "successful=2" in lines[-1]
    assert "errors=1" in lines[-1]
    assert "remaining=0" in lines[-1]
