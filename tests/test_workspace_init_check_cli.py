from __future__ import annotations

import builtins
import json
from pathlib import Path

import pytest

import yadof
from yadof import cli
from yadof.job_template import calculate_cost, validate_rawdata_directory
from yadof.task_loader import load_task_module
from yadof.workspace.check import check_workspace
from yadof.workspace.init import WorkspaceInitError, init_workspace


EXPECTED_WORKSPACE_FILES = {
    ".yadof/workspace.json",
    "config.py",
    "job_template/calc_cost.py",
    "job_template/parameters_constraints.py",
    "job_template/workflow.py",
}

FORBIDDEN_FRAMEWORK_PATHS = {
    "job_template/api.py",
    "job_template/cost_misc.py",
    "job_template/parameters_constraints_class.py",
    "job_template/rawdata_contract.py",
    "evaluate_manager",
    "optimize",
    "recorded_data",
    "surrogate",
}


def _relative_files(root: Path) -> set[str]:
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_init_empty_directory_creates_generic_workspace_and_check_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()

    assert cli.main(["init", str(root)]) == 0
    output = capsys.readouterr()
    assert "Initialized yadof workspace" in output.out
    assert output.err == ""
    assert _relative_files(root) == EXPECTED_WORKSPACE_FILES
    assert not FORBIDDEN_FRAMEWORK_PATHS & {
        path.relative_to(root).as_posix() for path in root.rglob("*")
    }
    assert not tuple(root.rglob("__pycache__"))

    marker_path = root / ".yadof/workspace.json"
    marker_text = marker_path.read_text(encoding="utf-8")
    marker = json.loads(marker_text)
    assert marker == {
        "rawdata_schema_version": 1,
        "template_name": "default",
        "template_version": 1,
        "workspace_schema_version": 1,
        "yadof_version": yadof.__version__,
    }
    assert str(root.resolve()) not in marker_text

    assert cli.main(["check", "--workspace", str(root)]) == 0
    output = capsys.readouterr()
    assert "Workspace check passed" in output.out
    assert "workflow was not imported or executed" in output.out
    assert output.err == ""
    assert not (root / "job_template/rawData").exists()
    assert not (root / "job_template/individual_metadata.json").exists()


def test_generic_starter_runs_only_when_explicitly_invoked(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    init_workspace(root)
    workflow = load_task_module(root, "workflow")
    parameters = workflow.get_parameters()
    parameters[0].value = 0.25
    parameters[0].normalized_value = 0.625

    assert workflow.main() == 0

    rawdata_files = validate_rawdata_directory(root / "job_template/rawData")
    assert [path.name for path in rawdata_files] == ["response.npz"]
    assert calculate_cost(root, ((rawdata_files[0],),)) == ((0.0625,),)
    metadata = json.loads(
        (root / "job_template/individual_metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["status"] == "done"


def test_init_defaults_to_current_directory_and_is_non_interactive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "current"
    root.mkdir()
    monkeypatch.chdir(root)
    monkeypatch.setattr(
        builtins,
        "input",
        lambda *args, **kwargs: pytest.fail("init/check must not prompt for input"),
    )

    assert cli.main(["init"]) == 0
    assert cli.main(["check"]) == 0
    assert _relative_files(root) == EXPECTED_WORKSPACE_FILES
    assert capsys.readouterr().err == ""


def test_repeated_init_preserves_user_changes_and_unrelated_history(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "workspace"
    assert init_workspace(root).created
    config_path = root / "config.py"
    config_path.write_text(
        "EVALUATION_MODE = 'local'\nOPTIMIZE_POPULATION_SIZE = 13\n",
        encoding="utf-8",
    )
    history = root / "recorded_data/history.txt"
    history.parent.mkdir()
    history.write_text("user history\n", encoding="utf-8")
    before = {path: path.read_bytes() for path in (config_path, history)}

    assert cli.main(["init", str(root)]) == 0
    output = capsys.readouterr()
    assert "already initialized" in output.out
    assert "no files changed" in output.out
    assert output.err == ""
    assert {path: path.read_bytes() for path in before} == before


@pytest.mark.parametrize(
    "relative_path",
    [
        "config.py",
        "job_template/workflow.py",
        "job_template",
    ],
)
def test_init_stops_on_partial_or_obstructing_targets_and_lists_exact_path(
    tmp_path: Path,
    relative_path: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / relative_path.replace("/", "_")
    root.mkdir()
    conflict = root / relative_path
    conflict.parent.mkdir(parents=True, exist_ok=True)
    if relative_path == "job_template":
        conflict.write_text("blocks required directory\n", encoding="utf-8")
    else:
        conflict.write_text("user content\n", encoding="utf-8")

    assert cli.main(["init", str(root)]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert str(conflict.resolve()) in output.err
    assert "would overwrite" in output.err
    assert conflict.read_text(encoding="utf-8").startswith(("user", "blocks"))
    assert not (root / ".yadof/workspace.json").exists()
    assert _relative_files(root) == {relative_path}


def test_init_allows_and_preserves_unrelated_existing_content(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    note = root / "notes/keep.txt"
    note.parent.mkdir()
    note.write_text("keep me\n", encoding="utf-8")

    assert init_workspace(root).created

    assert note.read_text(encoding="utf-8") == "keep me\n"
    assert _relative_files(root) == EXPECTED_WORKSPACE_FILES | {"notes/keep.txt"}


def test_repeated_init_does_not_repair_an_incomplete_workspace(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    init_workspace(root)
    missing = root / "job_template/workflow.py"
    missing.unlink()

    with pytest.raises(WorkspaceInitError, match="will not recreate user files"):
        init_workspace(root)

    assert not missing.exists()


def test_init_validation_failure_removes_stage_root_and_new_parents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from yadof.workspace import init as workspace_init

    root = tmp_path / "new-parent/child/workspace"

    def fail_validation(stage: Path, template: object) -> None:
        raise RuntimeError("injected validation failure")

    monkeypatch.setattr(workspace_init, "_validate_staged_workspace", fail_validation)

    with pytest.raises(WorkspaceInitError, match="injected validation failure"):
        init_workspace(root)

    assert not root.exists()
    assert not (tmp_path / "new-parent").exists()
    assert not tuple(tmp_path.rglob("*.yadof-init-*"))


def test_init_publish_failure_rolls_back_only_created_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from yadof.workspace import init as workspace_init

    root = tmp_path / "workspace"
    root.mkdir()
    note = root / "keep.txt"
    note.write_text("user content\n", encoding="utf-8")
    original_publish = workspace_init._publish_file_exclusive
    calls = 0

    def fail_second_publish(source: Path, target: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected publish failure")
        original_publish(source, target)

    monkeypatch.setattr(workspace_init, "_publish_file_exclusive", fail_second_publish)

    with pytest.raises(WorkspaceInitError, match="injected publish failure"):
        init_workspace(root)

    assert note.read_text(encoding="utf-8") == "user content\n"
    assert _relative_files(root) == {"keep.txt"}
    assert not tuple(tmp_path.glob(".workspace.yadof-init-*"))


def test_check_reports_invalid_marker_config_and_static_rawdata(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    init_workspace(root)
    (root / "config.py").write_text("EVALUATION_MODE = 'invalid'\n", encoding="utf-8")
    marker = root / ".yadof/workspace.json"
    marker.write_text("{not json}\n", encoding="utf-8")

    report = check_workspace(root)

    assert not report.ok
    assert "workspace marker is not valid JSON" in report.format()
    assert "EVALUATION_MODE must be 'local' or 'distributed'" in report.format()

    init_workspace_root = tmp_path / "rawdata-workspace"
    init_workspace(init_workspace_root)
    (init_workspace_root / "job_template/rawData/nested").mkdir(parents=True)
    rawdata_report = check_workspace(init_workspace_root)
    assert not rawdata_report.ok
    assert "rawData directory must be flat" in rawdata_report.format()


def test_check_continues_static_checks_after_task_import_failure(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    init_workspace(root)
    (root / "job_template/parameters_constraints.py").write_text(
        "raise RuntimeError('broken parameters')\n",
        encoding="utf-8",
    )
    (root / "job_template/workflow.py").write_text("if invalid syntax\n", encoding="utf-8")
    (root / "job_template/rawData/nested").mkdir(parents=True)

    report = check_workspace(root)

    assert not report.ok
    text = report.format()
    assert "broken parameters" in text
    assert "syntax/read failure" in text
    assert "rawData directory must be flat" in text


def test_check_parses_but_never_imports_or_executes_workflow(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    init_workspace(root)
    sentinel = root / "workflow-ran.txt"
    (root / "job_template/workflow.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(sentinel)!r}).write_text('ran', encoding='utf-8')\n",
        encoding="utf-8",
    )

    report = check_workspace(root)

    assert report.ok
    assert "workflow was not imported or executed" in report.format()
    assert not sentinel.exists()


def test_check_distributed_backend_reports_prerequisites_without_repair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from yadof.workspace import check as workspace_check

    root = tmp_path / "workspace"
    init_workspace(root)
    (root / "config.py").write_text("EVALUATION_MODE = 'distributed'\n", encoding="utf-8")
    monkeypatch.setattr(workspace_check.shutil, "which", lambda command: None)

    report = check_workspace(root)

    assert not report.ok
    text = report.format()
    assert text.count("[ERROR] distributed backend") == 3
    assert "ask an administrator to prepare HTCondor" in text


def test_cli_help_describes_safe_non_executing_contract(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as init_exit:
        cli.main(["init", "--help"])
    assert init_exit.value.code == 0
    init_help = capsys.readouterr()
    assert "without overwriting" in init_help.out
    assert "without" in init_help.out and "workflow" in init_help.out

    with pytest.raises(SystemExit) as check_exit:
        cli.main(["check", "--help"])
    assert check_exit.value.code == 0
    check_help = capsys.readouterr()
    assert "never runs the workflow" in check_help.out
    assert "installs/repairs" in check_help.out
