from __future__ import annotations

import json

import pytest

from project.evaluate_manager.job_files import prepare_job, prepared_job_static_hash


def _make_template(template_dir, *, workflow_body: str = "WORKFLOW_VERSION = 1\n", x0_max: float = 2.0):
    template_dir.mkdir(parents=True, exist_ok=True)
    (template_dir / "workflow.py").write_text(workflow_body, encoding="utf-8", newline="\n")
    (template_dir / "test_com.py").write_text("COM_VERSION = 1\n", encoding="utf-8", newline="\n")
    (template_dir / "xxxx.aedt").write_bytes(b"model bytes v1\n")
    (template_dir / "calc_cost.py").write_text("SHOULD_NOT_COPY = True\n", encoding="utf-8", newline="\n")
    (template_dir / "parameters_constraints.py").write_text(
        "\n".join(
            [
                "PARAMETERS = (",
                f"    ('x0', ((-2.0, {x0_max}),), ''),",
                "    ('x1', ((-2.0, 2.0),), ''),",
                "    ('x2', ((0.0, 1.0),), ''),",
                ")",
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )
    (template_dir / "rawData").mkdir(exist_ok=True)
    (template_dir / "rawData" / "old.npz").write_bytes(b"runtime artifact")
    return template_dir


def _metadata(job_dir, name="metadata.json"):
    return json.loads((job_dir / name).read_text(encoding="utf-8"))


def _values(x0: float, x1: float, x2: float) -> tuple[float, ...]:
    return (x0, x1, x2) + (0.5,) * 17


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


@pytest.mark.parametrize(
    ("changed_file", "new_content"),
    [
        ("workflow.py", "WORKFLOW_VERSION = 2\n"),
        (
            "parameters_constraints.py",
            "\n".join(
                [
                    "PARAMETERS = (",
                    "    ('x0', ((-2.0, 3.0),), ''),",
                    "    ('x1', ((-2.0, 2.0),), ''),",
                    "    ('x2', ((0.0, 1.0),), ''),",
                    ")",
                    "",
                ]
            ),
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

    (job.directory / "job_input.json").write_text('{"normalized_variables": [9, 9, 9]}', encoding="utf-8")
    (job.directory / "metadata.json").write_text('{"status": "running"}', encoding="utf-8")
    (job.directory / "metaData.json").write_text('{"status": "running"}', encoding="utf-8")
    (job.directory / "cost.json").write_text('{"cost": 123}', encoding="utf-8")
    (job.directory / "rawData" / "curve.npz").write_bytes(b"runtime raw data")
    (job.directory / "__pycache__").mkdir()
    (job.directory / "__pycache__" / "workflow.pyc").write_bytes(b"cache")
    (job.directory / "_tmp").mkdir()
    (job.directory / "_tmp" / "solver.tmp").write_bytes(b"temp")

    assert prepared_job_static_hash(job.directory) == original_hash
