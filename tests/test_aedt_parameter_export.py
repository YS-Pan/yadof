from __future__ import annotations

import runpy
import math
from pathlib import Path

import pytest

from yadof.tools.user_tools.aedt_parameters import export_aedt_parameters, read_aedt_parameters
from yadof.tools.user_tools.aedt_parameters import parameter_extraction as generator


def _setup(variables: str, *, name: str = "OptimizationSetup1") -> str:
    return (
        f"$begin '{name}'\n"
        "$begin 'Variables'\n" + variables + "\n$end 'Variables'\n"
        f"$end '{name}'\n"
    )


def _project(tmp_path: Path, *, attrs: str | None = None, current: str = "1.5mm") -> Path:
    folder = tmp_path / "工程 with spaces"
    folder.mkdir(exist_ok=True)
    project = folder / "model.aedt"
    attrs = attrs or "i=true, int=false, Min='1mm', Max='2mm', Level='[0: 4] mm'"
    project.write_text(
        f"VariableProp('宽度', 'UD', '', '{current}', oa({attrs}), "
        "sa(i=false, int=false, Min='10mm', Max='20mm'))\n"
        + _setup(f"宽度({attrs})"),
        encoding="utf-8",
    )
    return project


def test_export_creates_importable_yadof_parameters_beside_project(tmp_path):
    project = _project(tmp_path)
    result = export_aedt_parameters(f'"{project}"', backup_dir=tmp_path / "备份")

    assert result.parameter_file == project.parent / "parameters_constraints.py"
    assert result.parameter_count == 1
    assert result.backup_file is None
    module = runpy.run_path(str(result.parameter_file))
    parameters = module["get_parameters"]()
    assert [(p.name, p.ranges, p.unit) for p in parameters] == [("宽度", ((1.0, 2.0),), "mm")]
    assert module["CONSTRAINTS"] == ()
    assert not (tmp_path / "备份").exists()


def test_export_backs_up_arbitrary_old_bytes_before_replacing(tmp_path):
    project = _project(tmp_path)
    output = project.parent / "parameters_constraints.py"
    original = b"old custom code\r\nCONSTRAINTS = ('custom',)\r\n\xff"
    output.write_bytes(original)
    backup_dir = tmp_path / "custom backups"

    first = export_aedt_parameters(project, backup_dir=backup_dir)
    generated = output.read_bytes()
    second = export_aedt_parameters(project, backup_dir=backup_dir)

    assert first.backup_file.parent == backup_dir
    assert first.backup_file.read_bytes() == original
    assert second.backup_file != first.backup_file
    assert second.backup_file.read_bytes() == generated
    assert runpy.run_path(str(output))["CONSTRAINTS"] == ()


def test_backup_failure_preserves_old_file_and_cleans_staging(tmp_path, monkeypatch):
    project = _project(tmp_path)
    output = project.parent / "parameters_constraints.py"
    output.write_bytes(b"original")

    def fail(*_args, **_kwargs):
        raise PermissionError("backup unavailable")

    monkeypatch.setattr(generator, "_backup_parameter_file", fail)
    with pytest.raises(PermissionError, match="backup unavailable"):
        export_aedt_parameters(project, backup_dir=tmp_path / "backup")

    assert output.read_bytes() == b"original"
    assert not list(project.parent.glob(".*.tmp"))


def test_publish_failure_retains_old_file_and_recoverable_backup(tmp_path, monkeypatch):
    project = _project(tmp_path)
    output = project.parent / "parameters_constraints.py"
    output.write_bytes(b"original")
    backup_dir = tmp_path / "backup"

    def fail(*_args):
        raise PermissionError("output locked")

    monkeypatch.setattr(generator.os, "replace", fail)
    with pytest.raises(PermissionError, match="output locked"):
        export_aedt_parameters(project, backup_dir=backup_dir)

    assert output.read_bytes() == b"original"
    assert [path.read_bytes() for path in backup_dir.iterdir()] == [b"original"]
    assert not list(project.parent.glob(".*.tmp"))


@pytest.mark.parametrize("attrs", [
    "i=true, int=false, Min='2mm', Max='1mm'",
    "i=true, int=false, Min='1mm', Max='2cm'",
    "i=true, int=false, Min='1e999mm', Max='2e999mm'",
    "i=true, int=false, Min='base/2', Max='2mm', Level='[1: 2] mm'",
    "i=true, int=false, Min='1mm'",
    "i=true, int=false, Level='[nan, 2] mm'",
    "i=true, int=false, Level='[base, 2] mm'",
    "i=false, int=false, Min='1mm', Max='2mm'",
])
def test_unusable_enabled_ranges_never_replace_or_backup(tmp_path, attrs):
    project = _project(tmp_path, attrs=attrs)
    output = project.parent / "parameters_constraints.py"
    output.write_bytes(b"original")
    backup_dir = tmp_path / "backup"

    with pytest.raises(ValueError):
        export_aedt_parameters(project, backup_dir=backup_dir)

    assert output.read_bytes() == b"original"
    assert not backup_dir.exists()


def test_preview_accepts_expression_current_value_without_executing_it(tmp_path):
    project = _project(tmp_path, current="base * 2")
    parameters = read_aedt_parameters(project)

    assert [(p.name, p.ranges, p.unit) for p in parameters] == [("宽度", ((1, 2),), "mm")]
    assert math.isnan(parameters[0].value)
    assert not (project.parent / "parameters_constraints.py").exists()


@pytest.mark.parametrize("encoding", ["utf-8-sig", "utf-16"])
def test_multiline_records_and_bom_encodings(tmp_path, encoding):
    project = _project(tmp_path)
    project.write_text(
        _setup("长度(\\\n i = true, int = false, Min = '1mm',\n Max = '3mm')"),
        encoding=encoding,
    )
    assert read_aedt_parameters(project)[0].ranges == ((1, 3),)


def test_standalone_project_variable_and_discrete_levels(tmp_path):
    project = _project(tmp_path)
    project.write_text(
        _setup("$mode(i=true, int=false, Min='0', Max='10', Level='[1, 2, 4]')"),
        encoding="utf-8",
    )
    parameter, = read_aedt_parameters(project)
    assert (parameter.name, parameter.ranges, parameter.unit) == ("$mode", (1, 2, 4), "")


def test_integer_bounds_become_discrete_yadof_values(tmp_path):
    project = _project(tmp_path, attrs="i=true, int=true, Min='1', Max='4'")
    assert read_aedt_parameters(project)[0].ranges == (1, 2, 3, 4)


def test_multiple_named_setups_are_rejected(tmp_path):
    project = _project(tmp_path)
    project.write_text(project.read_text(encoding="utf-8") * 2, encoding="utf-8")
    with pytest.raises(ValueError, match="多个 OptimizationSetup1"):
        read_aedt_parameters(project)


def test_only_target_variables_include_flags_and_ranges_are_used(tmp_path):
    project = _project(tmp_path)
    selected = _setup(
        "kept(i=true, int=false, Min='10mm', Max='20mm', Level='[0: 100] mm')\n"
        "unchecked(i=false, int=false, Min='bad', Max='bad')"
    ).replace(
        "$end 'OptimizationSetup1'",
        "$begin 'Goals'\n$begin 'Variables'\n"
        "goal_only(i=true, int=false, Min='1mm', Max='2mm')\n"
        "$end 'Variables'\n$end 'Goals'\n$end 'OptimizationSetup1'",
    )
    project.write_text(
        "VariableProp('kept', 'UD', '', '900cm', oa(i=true, int=false, Min='bad', Max='bad'))\n"
        "VariableProp('unchecked', 'UD', '', '1mm', oa(i=true, int=false, Min='1mm', Max='2mm'))\n"
        "outside_only(i=true, int=false, Min='1mm', Max='2mm')\n"
        + _setup("kept(i=true, int=false, Min='100mm', Max='200mm')", name="OptimizationSetup2")
        + selected
        + _setup("after_only(i=true, int=false, Min='1mm', Max='2mm')", name="OptimizationSetup11"),
        encoding="utf-8",
    )

    parameter, = read_aedt_parameters(project)
    assert (parameter.name, parameter.ranges, parameter.unit) == ("kept", ((10, 20),), "mm")
    assert math.isnan(parameter.value)


def test_units_are_never_inferred_from_global_variableprop(tmp_path):
    project = _project(tmp_path, attrs="i=true, int=false, Min='1', Max='2'", current="1.5mm")
    assert read_aedt_parameters(project)[0].unit == ""


@pytest.mark.parametrize("selected", [
    "",
    _setup("width(i=true, int=false, Min='1mm', Max='2mm')", name="OptimizationSetup11"),
    _setup("width(i=false, int=false, Min='1mm', Max='2mm')"),
    _setup(""),
    "$begin 'OptimizationSetup1'\n$begin 'StartingPoint'\nwidth='1mm'\n$end 'StartingPoint'\n$end 'OptimizationSetup1'\n",
    "$begin 'OptimizationSetup1'\n$begin 'Variables'\nwidth(i=true, int=false, Min='1mm', Max='2mm')\n$end 'Variables'\n",
    "$begin 'OptimizationSetup1'\n$begin 'Variables'\nwidth(i=true, int=false, Min='1mm', Max='2mm')\n$end 'OptimizationSetup1'\n",
])
def test_missing_empty_or_malformed_setup_never_falls_back_or_writes(tmp_path, selected, monkeypatch):
    project = _project(tmp_path)
    project.write_text(
        "VariableProp('outside', 'UD', '', '1mm', oa(i=true, int=false, Min='1mm', Max='2mm'))\n"
        + selected,
        encoding="utf-8",
    )
    output = project.parent / "parameters_constraints.py"
    output.write_bytes(b"original")
    backup_dir = tmp_path / "backup"

    def no_simulator(*_args, **_kwargs):
        raise AssertionError("the GUI must not launch AEDT")

    monkeypatch.setattr(generator, "_open_hfss_project", no_simulator)
    with pytest.raises(ValueError):
        export_aedt_parameters(project, backup_dir=backup_dir)
    assert output.read_bytes() == b"original"
    assert not backup_dir.exists()


def test_duplicate_variable_records_inside_selected_setup_are_rejected(tmp_path):
    project = _project(tmp_path)
    project.write_text(_setup("width(i=true, Min='1mm', Max='2mm')\n" * 2), encoding="utf-8")
    with pytest.raises(ValueError, match="多个定义"):
        read_aedt_parameters(project)


def test_repeated_backup_timestamp_does_not_overwrite(tmp_path):
    original = tmp_path / "parameters_constraints.py"
    original.write_bytes(b"first")
    first = generator._backup_parameter_file(original, tmp_path / "backup", timestamp="same")
    original.write_bytes(b"second")
    second = generator._backup_parameter_file(original, tmp_path / "backup", timestamp="same")
    assert first != second
    assert first.read_bytes() == b"first"
    assert second.read_bytes() == b"second"


@pytest.mark.parametrize("path", ["", "missing.aedt", "model.txt"])
def test_invalid_project_paths_are_reported(tmp_path, path):
    with pytest.raises((ValueError, FileNotFoundError)):
        read_aedt_parameters(str(tmp_path / path) if path else path)
