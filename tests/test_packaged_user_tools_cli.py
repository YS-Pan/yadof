from __future__ import annotations

import os
from pathlib import Path
import runpy

import numpy as np
import pytest
import yadof

from yadof.cli import main as cli_main
from yadof.evaluate_manager import evaluate_population
from yadof.recorded_data import list_records
from yadof.resources import adapter_names, adapter_resource
from yadof.tools.adapters import copy_adapter
from yadof.tools.history import (
    HistoryClearConfirmationRequired,
    clear_history,
)
from yadof.workspace.init import init_workspace


@pytest.fixture(autouse=True)
def _source_package_for_worker_processes(monkeypatch: pytest.MonkeyPatch) -> None:
    package_parent = Path(yadof.__file__).resolve().parents[1]
    inherited = os.environ.get("PYTHONPATH", "")
    value = str(package_parent)
    if inherited:
        value += os.pathsep + inherited
    monkeypatch.setenv("PYTHONPATH", value)


def _workspace(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    init_workspace(root)
    return root


def test_bundled_adapters_are_listed_and_only_selected_file_is_copied(
    tmp_path, capsys
):
    workspace = _workspace(tmp_path, "adapter_workspace")

    assert set(adapter_names()) == {"hfss_com.py", "test_com.py"}
    assert adapter_resource("test_com").is_file()
    assert cli_main(["task", "adapters"]) == 0
    assert "hfss_com.py" in capsys.readouterr().out

    result = copy_adapter(workspace, "test_com")
    assert result.created is True
    assert result.destination.is_file()
    assert not (workspace / "job_template" / "hfss_com.py").exists()
    repeated = copy_adapter(workspace, "test_com.py")
    assert repeated.created is False

    result.destination.write_text("# user edit\n", encoding="utf-8")
    assert cli_main(
        [
            "task",
            "copy-adapter",
            "test_com.py",
            "--workspace",
            str(workspace),
        ]
    ) == 1
    assert result.destination.read_text(encoding="utf-8") == "# user edit\n"


def test_test_com_large_scale_profile_has_exact_multidimensional_shapes():
    namespace = runpy.run_path(str(adapter_resource("test_com.py")))
    evaluate_raw_data = namespace["evaluate_raw_data"]
    variables = {f"x{index}": index / 29.0 for index in range(30)}

    blocks = evaluate_raw_data(variables, profile="large_scale")
    expected_shapes = {
        "scalar_0": (),
        "scalar_1": (),
        "curve_0": (20,),
        "curve_1": (20,),
        "surface": (100, 100),
        "volume": (5, 100, 100),
    }
    assert tuple(blocks) == tuple(expected_shapes)

    for name, expected_shape in expected_shapes.items():
        block = blocks[name]
        values = np.asarray(block["arrays"]["values"])
        metadata = block["metadata"]
        assert values.shape == expected_shape
        assert values.dtype == np.float32
        assert metadata["schema_version"] == 1
        assert metadata["rawdata_name"] == name
        assert metadata["shape"] == list(expected_shape)
        assert len(metadata["axes"]) == len(expected_shape)

    repeated = evaluate_raw_data(variables, profile="stress")
    for name in expected_shapes:
        np.testing.assert_array_equal(
            repeated[name]["arrays"]["values"],
            blocks[name]["arrays"]["values"],
        )


def test_view_commands_use_one_explicit_workspace(capsys, tmp_path):
    workspace = _workspace(tmp_path, "view_workspace")
    evaluate_population(workspace, ((0.25,),))

    assert cli_main(
        ["view", "cost", "--workspace", str(workspace)]
    ) == 0
    cost_output = capsys.readouterr().out
    assert "rows: 1" in cost_output
    assert "objectives: objective" in cost_output

    assert cli_main(
        ["view", "time", "--workspace", str(workspace)]
    ) == 0
    time_output = capsys.readouterr().out
    assert "rows: 1" in time_output
    assert "failure rate: 0.00 %" in time_output


def test_history_clear_requires_confirmation_and_clears_only_selected_workspace(
    capsys, tmp_path
):
    workspace_a = _workspace(tmp_path, "clear_a")
    workspace_b = _workspace(tmp_path, "clear_b")
    evaluate_population(workspace_a, ((0.25,),))
    evaluate_population(workspace_b, ((0.75,),))

    try:
        clear_history(workspace_a)
    except HistoryClearConfirmationRequired:
        pass
    else:  # pragma: no cover - protects the destructive API default.
        raise AssertionError("clear_history accepted missing confirmation")

    assert cli_main(
        ["history", "clear", "--workspace", str(workspace_a)]
    ) == 1
    assert len(list_records(workspace_a)) == 1
    assert "requires --yes" in capsys.readouterr().err

    assert cli_main(
        [
            "history",
            "clear",
            "--workspace",
            str(workspace_a),
            "--yes",
        ]
    ) == 0
    assert list_records(workspace_a) == ()
    assert len(list_records(workspace_b)) == 1
    assert not any((workspace_a / "jobs").iterdir())


def test_extract_parameters_uses_workspace_paths_and_confirmation(capsys, tmp_path):
    workspace = _workspace(tmp_path, "extract_workspace")
    project_path = workspace / "job_template" / "synthetic.aedt"
    project_path.write_text(
        "VariableProp('width', 'VariableProp', '', '1.5mm')\n"
        "width(i=true, int=false, Min='1mm', Max='2mm', Level='[1 : 2] mm')\n",
        encoding="utf-8",
    )
    parameter_file = workspace / "job_template" / "parameters_constraints.py"
    original = parameter_file.read_text(encoding="utf-8")

    assert cli_main(
        [
            "task",
            "extract-parameters",
            "--workspace",
            str(workspace),
            "--project",
            "job_template/synthetic.aedt",
        ]
    ) == 1
    assert parameter_file.read_text(encoding="utf-8") == original
    assert "requires --yes" in capsys.readouterr().err

    assert cli_main(
        [
            "task",
            "extract-parameters",
            "--workspace",
            str(workspace),
            "--project",
            "job_template/synthetic.aedt",
            "--yes",
        ]
    ) == 0
    source = parameter_file.read_text(encoding="utf-8")
    assert "Parameter('width', ((1, 2),), unit='mm')" in source
    backups = tuple(
        (workspace / ".yadof" / "tool_output" / "parameter_history").glob(
            "parameters_constraints_*.py"
        )
    )
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == original


def test_only_the_package_tool_namespace_is_present():
    assert not Path("project").exists()
    assert Path("src/yadof/tools/view_cost.py").is_file()
    assert Path("src/yadof/tools/view_time.py").is_file()
