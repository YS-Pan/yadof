from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import runpy

import numpy as np
import pytest
import yadof

from yadof.cli import main as cli_main
from yadof.cli.main import _default_view_output_name, build_parser
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

    assert set(adapter_names()) == {
        "chrono_com.py",
        "hfss_com.py",
        "ngspice_com.py",
        "test_com.py",
    }
    assert adapter_resource("chrono_com").is_file()
    assert adapter_resource("test_com").is_file()
    assert cli_main(["task", "adapters"]) == 0
    listed = capsys.readouterr().out
    assert "chrono_com.py" in listed
    assert "hfss_com.py" in listed

    result = copy_adapter(workspace, "test_com")
    assert result.created is True
    assert result.destination.is_file()
    assert not (workspace / "job_template" / "hfss_com.py").exists()
    assert not (workspace / "job_template" / "ngspice_com.py").exists()
    assert not (workspace / "job_template" / "chrono_com.py").exists()
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
    assert "objectives: cost_response" in cost_output
    assert "saved:" in cost_output
    cost_plots = tuple(
        (workspace / ".yadof" / "tool_output").glob("cost_*.png")
    )
    assert len(cost_plots) == 1

    assert cli_main(
        ["view", "time", "--workspace", str(workspace)]
    ) == 0
    time_output = capsys.readouterr().out
    assert "rows: 1" in time_output
    assert "failure rate: 0.00 %" in time_output
    assert "saved:" in time_output
    time_plots = tuple(
        (workspace / ".yadof" / "tool_output").glob("time_*.png")
    )
    assert len(time_plots) == 1

    assert cli_main(
        [
            "view",
            "time",
            "--workspace",
            str(workspace),
            "--summary-only",
        ]
    ) == 0
    summary_only_output = capsys.readouterr().out
    assert "rows: 1" in summary_only_output
    assert "saved:" not in summary_only_output
    assert tuple(
        (workspace / ".yadof" / "tool_output").glob("time_*.png")
    ) == time_plots


def test_view_default_output_name_matches_legacy_timestamp_format():
    now = datetime(2026, 7, 24, 17, 30, 45)

    assert _default_view_output_name("cost", now=now) == Path(
        "cost_20260724_173045.png"
    )
    assert _default_view_output_name("time", now=now) == Path(
        "time_20260724_173045.png"
    )


def test_surrogate_viewer_cli_is_registered_without_loading_optional_modules():
    parser = build_parser()
    args = parser.parse_args(
        ["view", "surrogate", "--workspace", "D:/work/viewer"]
    )

    assert args.view_kind == "surrogate"
    assert args.workspace == Path("D:/work/viewer")
    assert args.handler.__name__ == "_surrogate_viewer_command"

    summary_args = parser.parse_args(
        [
            "view",
            "surrogate",
            "summary",
            "--workspace",
            "D:/work/viewer",
            "--format",
            "json",
        ]
    )
    assert summary_args.surrogate_action == "summary"
    assert summary_args.workspace == Path("D:/work/viewer")
    assert summary_args.output_format == "json"
    assert summary_args.handler.__name__ == "_surrogate_report_command"

    audit_args = parser.parse_args(
        [
            "view",
            "surrogate",
            "audit",
            "--sample-percent",
            "25",
            "--metric",
            "both",
            "--quantity",
            "rawdata:gain",
        ]
    )
    assert audit_args.surrogate_action == "audit"
    assert audit_args.sample_percent == 25.0
    assert audit_args.metric == "both"
    assert audit_args.quantity == "rawdata:gain"
    assert audit_args.handler.__name__ == "_surrogate_report_command"


def test_view_all_prints_both_results_and_creates_both_images(capsys, tmp_path):
    workspace = _workspace(tmp_path, "view_all_workspace")
    evaluate_population(workspace, ((0.25,),))

    assert cli_main(
        ["view", "all", "--workspace", str(workspace)]
    ) == 0

    output = capsys.readouterr()
    assert output.err == ""
    assert "=== cost ===" in output.out
    assert "=== time ===" in output.out
    assert "=== error ===" not in output.out
    assert output.out.count("saved:") == 2
    tool_output = workspace / ".yadof" / "tool_output"
    for view_kind in ("cost", "time"):
        assert len(tuple(tool_output.glob(f"{view_kind}_*.png"))) == 1


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


def test_hfss_extract_parameters_uses_workspace_paths_and_confirmation(capsys, tmp_path):
    workspace = _workspace(tmp_path, "extract_workspace")
    project_path = workspace / "job_template" / "synthetic.aedt"
    project_path.write_text(
        "VariableProp('Wc1', 'UD', '', '36.9mm', "
        "oa(i=true, int=false, Min='30mm', Max='40mm', "
        "Level='[22.5 : 67.5] mm'))\n",
        encoding="utf-8",
    )
    parameter_file = workspace / "job_template" / "parameters_constraints.py"
    original = parameter_file.read_text(encoding="utf-8")

    assert cli_main(
        [
            "task",
            "hfss",
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
            "hfss",
            "extract-parameters",
            "--workspace",
            str(workspace),
            "--project",
            "job_template/synthetic.aedt",
            "--yes",
        ]
    ) == 0
    source = parameter_file.read_text(encoding="utf-8")
    assert "Parameter('Wc1', ((30, 40),), unit='mm')" in source
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
    assert Path("src/yadof/tools/surrogate_viewer/app.py").is_file()
    assert Path(
        "src/yadof/tools/surrogate_viewer/dev_doc/README.md"
    ).is_file()
    assert not Path("src/yadof/tools/view_error.py").exists()
