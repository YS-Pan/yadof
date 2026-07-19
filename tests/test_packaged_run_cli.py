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
        f"OPTIMIZE_SMOKE_TEST_ENABLED = {smoke!r}\n"
        "OPTIMIZE_SURROGATE_ALPHA = 1\n"
        "OPTIMIZE_SURROGATE_BETA = 0\n",
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
            "--progress",
            "--fail-on-all-infinite",
        ]
    ) == 0
    assert seen["config_overrides"] == {"EVALUATION_MODE": "distributed"}
    assert seen["fail_on_all_infinite"] is True
    assert "YADOF_PROGRESS" not in os.environ


def test_repository_root_launchers_are_removed():
    assert not Path("start_optimization_from_config.py").exists()
    assert not Path("start_optimization_aedtopt.cmd").exists()
