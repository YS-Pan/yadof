from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

from project.evaluate_manager.config import PROJECT_CONFIG_DIR_NAME, PROJECT_DIR
from project.evaluate_manager.job_files import prepare_job, prepared_job_static_hash


def _parameter_source(
    *,
    x0_name: str = "x0",
    x0_max: float = 2.0,
    x0_unit: str = "",
    constraints: tuple[str, ...] = (),
) -> str:
    constraint_lines = "\n".join(f"    {constraint!r}," for constraint in constraints)
    return "\n".join(
        [
            "from __future__ import annotations",
            "",
            "try:",
            "    from .parameters_constraints_class import Parameter",
            "except ImportError:",
            "    from parameters_constraints_class import Parameter",
            "",
            "PARAMETERS = (",
            f"    Parameter({x0_name!r}, ((-2.0, {x0_max}),), unit={x0_unit!r}),",
            "    Parameter('x1', ((-2.0, 2.0),), unit=''),",
            "    Parameter('x2', ((0.0, 1.0),), unit=''),",
            ")",
            "",
            "CONSTRAINTS = (",
            constraint_lines,
            ")",
            "",
            "",
            "def get_parameters() -> tuple[Parameter, ...]:",
            "    return tuple(PARAMETERS)",
            "",
        ]
    )


def _make_template(template_dir, *, workflow_body: str = "WORKFLOW_VERSION = 1\n", x0_max: float = 2.0):
    template_dir.mkdir(parents=True, exist_ok=True)
    (template_dir / "workflow.py").write_text(workflow_body, encoding="utf-8", newline="\n")
    (template_dir / "solver_adapter.py").write_text("ADAPTER_VERSION = 1\n", encoding="utf-8", newline="\n")
    (template_dir / "model.input").write_bytes(b"model bytes v1\n")
    (template_dir / "calc_cost.py").write_text("SHOULD_NOT_COPY = True\n", encoding="utf-8", newline="\n")
    (template_dir / "individual_metadata.json").write_text('{"status": "error"}\n', encoding="utf-8", newline="\n")
    (template_dir / "rawData_outputs.zip").write_bytes(b"old zip")
    (template_dir / "job.sub").write_text("queue 1\n", encoding="utf-8", newline="\n")
    from project.job_template import parameters_constraints_class

    shutil.copy2(Path(parameters_constraints_class.__file__), template_dir / "parameters_constraints_class.py")
    (template_dir / "parameters_constraints.py").write_text(
        _parameter_source(x0_max=x0_max),
        encoding="utf-8",
        newline="\n",
    )
    (template_dir / "rawData").mkdir(exist_ok=True)
    (template_dir / "rawData" / "old.npz").write_bytes(b"runtime artifact")
    return template_dir


def _metadata(job_dir, name="metadata.json"):
    return json.loads((job_dir / name).read_text(encoding="utf-8"))


def _values(x0: float, x1: float, x2: float) -> tuple[float, ...]:
    return (x0, x1, x2)


def test_job_static_hash_is_written_and_stable_across_individual_values(tmp_path):
    template_dir = _make_template(tmp_path / "template")
    jobs_dir = tmp_path / "jobs"

    first = prepare_job(_values(0.1, 0.2, 0.3), jobs_dir=jobs_dir, job_template_dir=template_dir, job_name="first")
    second = prepare_job(_values(0.9, 0.8, 0.7), jobs_dir=jobs_dir, job_template_dir=template_dir, job_name="second")

    first_hash = _metadata(first.directory)["job_static_hash"]
    second_hash = _metadata(second.directory)["job_static_hash"]

    assert first_hash == second_hash
    assert first_hash == _metadata(first.directory, "metaData.json")["job_static_hash"]
    assert first_hash == prepared_job_static_hash(first.directory)
    assert len(first_hash) == 64
    assert not (first.directory / "cost.json").exists()
    assert not (first.directory / "calc_cost.py").exists()
    assert not (first.directory / "individual_metadata.json").exists()
    assert not (first.directory / "rawData_outputs.zip").exists()
    assert not (first.directory / "job.sub").exists()
    assert not (first.directory / "job_input.json").exists()
    assert not (first.directory / "variables.json").exists()
    assert not (first.directory / "parameters_values.py").exists()

def test_prepare_job_copies_submit_side_config_package(tmp_path):
    template_dir = _make_template(tmp_path / "template")
    job = prepare_job(_values(0.1, 0.2, 0.3), jobs_dir=tmp_path / "jobs", job_template_dir=template_dir)

    copied_dir = job.directory / PROJECT_CONFIG_DIR_NAME
    source_dir = PROJECT_DIR / PROJECT_CONFIG_DIR_NAME

    assert copied_dir.is_dir()
    source_files = {
        path.relative_to(source_dir)
        for path in source_dir.rglob("*.py")
        if "__pycache__" not in path.parts
    }
    copied_files = {
        path.relative_to(copied_dir)
        for path in copied_dir.rglob("*.py")
        if "__pycache__" not in path.parts
    }
    assert copied_files == source_files
    for relative_path in source_files:
        assert (copied_dir / relative_path).read_text(encoding="utf-8") == (
            source_dir / relative_path
        ).read_text(encoding="utf-8")
    assert not tuple(copied_dir.rglob("__pycache__"))


@pytest.mark.parametrize(
    ("changed_file", "new_content"),
    [
        ("workflow.py", "WORKFLOW_VERSION = 2\n"),
        (
            "parameters_constraints.py",
            _parameter_source(x0_max=3.0),
        ),
    ],
)

def test_job_static_hash_changes_when_static_definition_changes(tmp_path, changed_file, new_content):
    template_dir = _make_template(tmp_path / "template")
    jobs_dir = tmp_path / "jobs"

    before = prepare_job(_values(0.1, 0.2, 0.3), jobs_dir=jobs_dir, job_template_dir=template_dir, job_name="before")
    (template_dir / changed_file).write_text(new_content, encoding="utf-8", newline="\n")
    after = prepare_job(_values(0.1, 0.2, 0.3), jobs_dir=jobs_dir, job_template_dir=template_dir, job_name="after")

    assert _metadata(before.directory)["job_static_hash"] != _metadata(after.directory)["job_static_hash"]


def test_prepared_job_static_hash_ignores_runtime_artifacts(tmp_path):
    template_dir = _make_template(tmp_path / "template")
    job = prepare_job(_values(0.1, 0.2, 0.3), jobs_dir=tmp_path / "jobs", job_template_dir=template_dir)
    original_hash = prepared_job_static_hash(job.directory)

    (job.directory / "metadata.json").write_text('{"status": "running"}', encoding="utf-8")
    (job.directory / "metaData.json").write_text('{"status": "running"}', encoding="utf-8")
    (job.directory / "individual_metadata.json").write_text('{"status": "done"}', encoding="utf-8")
    (job.directory / "cost.json").write_text('{"cost": 123}', encoding="utf-8")
    (job.directory / "rawData" / "curve.npz").write_bytes(b"runtime raw data")
    (job.directory / "__pycache__").mkdir()
    (job.directory / "__pycache__" / "workflow.pyc").write_bytes(b"cache")
    (job.directory / "_tmp").mkdir()
    (job.directory / "_tmp" / "solver.tmp").write_bytes(b"temp")

    assert prepared_job_static_hash(job.directory) == original_hash


@pytest.mark.parametrize(
    "changed_source",
    (
        _parameter_source(x0_name="renamed"),
        _parameter_source(x0_max=3.0),
        _parameter_source(x0_unit="mm"),
        _parameter_source(constraints=("x0 - x1",)),
    ),
)
def test_parameter_definition_fields_change_static_hash(tmp_path, changed_source):
    template_dir = _make_template(tmp_path / "template")
    before = prepare_job(_values(0.25, 0.5, 0.75), jobs_dir=tmp_path / "jobs", job_template_dir=template_dir)
    before_hash = _metadata(before.directory)["job_static_hash"]

    (template_dir / "parameters_constraints.py").write_text(changed_source, encoding="utf-8", newline="\n")
    after = prepare_job(_values(0.25, 0.5, 0.75), jobs_dir=tmp_path / "jobs", job_template_dir=template_dir)

    assert _metadata(after.directory)["job_static_hash"] != before_hash


def test_job_template_api_copy_skips_runtime_artifacts(tmp_path, monkeypatch):
    from project.job_template import api as job_template_api

    template_dir = tmp_path / "api_template"
    template_dir.mkdir()
    (template_dir / "workflow.py").write_text("# workflow\n", encoding="utf-8", newline="\n")
    (template_dir / "individual_metadata.json").write_text('{"status": "error"}\n', encoding="utf-8", newline="\n")
    (template_dir / "rawData_outputs.zip").write_bytes(b"old zip")
    (template_dir / "job.sub").write_text("queue 1\n", encoding="utf-8", newline="\n")
    (template_dir / "rawData").mkdir()
    (template_dir / "rawData" / "old.npz").write_bytes(b"old data")
    (template_dir / "._home").mkdir()
    (template_dir / "._home" / "profile.txt").write_text("old profile\n", encoding="utf-8", newline="\n")

    monkeypatch.setattr(job_template_api, "TEMPLATE_DIR", template_dir)
    job_dir = tmp_path / "job"

    job_template_api.copy_job_files(job_dir)

    assert (job_dir / "workflow.py").is_file()
    assert not (job_dir / "individual_metadata.json").exists()
    assert not (job_dir / "rawData_outputs.zip").exists()
    assert not (job_dir / "job.sub").exists()
    assert not (job_dir / "._home").exists()
    assert (job_dir / "rawData").is_dir()
    assert not (job_dir / "rawData" / "old.npz").exists()
