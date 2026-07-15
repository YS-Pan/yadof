from __future__ import annotations

import math
from pathlib import Path
import shutil

import pytest

from project.evaluate_manager.job_files import prepare_job
from project.job_template.parameters_constraints_class import Parameter


def _parameter_source(*, upper: float) -> str:
    return f'''from __future__ import annotations

try:
    from .parameters_constraints_class import Parameter
except ImportError:
    from parameters_constraints_class import Parameter

PARAMETERS = (
    Parameter("continuous", ((0.0, {upper}),), unit="mm"),
    Parameter("mixed", (2.0, (10.0, 20.0)), unit=""),
)

CONSTRAINTS = (
    "continuous - 0.5",
)


def get_parameters() -> tuple[Parameter, ...]:
    return tuple(PARAMETERS)
'''


def _make_template(path: Path, *, upper: float) -> Path:
    from project.job_template import parameters_constraints_class

    path.mkdir(parents=True)
    shutil.copy2(Path(parameters_constraints_class.__file__), path / "parameters_constraints_class.py")
    (path / "parameters_constraints.py").write_text(
        _parameter_source(upper=upper),
        encoding="utf-8",
        newline="\n",
    )
    (path / "workflow.py").write_text("# generic workflow fixture\n", encoding="utf-8", newline="\n")
    return path


def test_parameter_denormalize_tracks_assigned_values_and_clips():
    continuous = Parameter("continuous", ((10.0, 30.0),), normalized_value=0.5)
    assert continuous.denormalize() == pytest.approx(20.0)
    assert continuous.value == pytest.approx(20.0)
    assert continuous.normalized_value == pytest.approx(0.5)

    assert continuous.denormalize(-0.5) == pytest.approx(10.0)
    assert continuous.normalized_value == pytest.approx(0.0)
    assert continuous.denormalize(1.5) == pytest.approx(30.0)
    assert continuous.normalized_value == pytest.approx(1.0)


def test_parameter_denormalize_supports_discrete_and_mixed_ranges():
    parameter = Parameter("mixed", (2.0, (10.0, 20.0)))

    assert parameter.denormalize(0.1) == pytest.approx(2.0)
    assert parameter.denormalize(0.5) == pytest.approx(10.0)
    assert parameter.denormalize(0.75) == pytest.approx(15.0)
    assert parameter.denormalize(1.0) == pytest.approx(20.0)


@pytest.mark.parametrize("ranges", ((), (float("nan"),), ((0.0, float("inf")),)))
def test_parameter_rejects_invalid_ranges(ranges):
    with pytest.raises(ValueError):
        Parameter("invalid", ranges)


@pytest.mark.parametrize("normalized", (float("nan"), float("inf"), -float("inf")))
def test_parameter_rejects_nonfinite_assigned_normalized_value(normalized):
    with pytest.raises(ValueError, match="normalized_value must be finite"):
        Parameter("x", ((0.0, 1.0),), normalized_value=normalized).denormalize()


def test_same_process_range_edit_refreshes_api_and_next_job(tmp_path, monkeypatch):
    from project.job_template import api as job_template_api

    template_dir = _make_template(tmp_path / "template", upper=2.0)
    monkeypatch.setattr(job_template_api, "TEMPLATE_DIR", template_dir)

    assert job_template_api.get_parameter_definitions()[0].ranges == ((0.0, 2.0),)
    first = prepare_job(
        (0.25, 0.75),
        jobs_dir=tmp_path / "jobs",
        job_template_dir=template_dir,
        job_name="first",
    )
    assert first.unnormalized_variables == pytest.approx((0.5, 15.0))

    (template_dir / "parameters_constraints.py").write_text(
        _parameter_source(upper=6.0),
        encoding="utf-8",
        newline="\n",
    )

    assert job_template_api.get_parameter_definitions()[0].ranges == ((0.0, 6.0),)
    second = prepare_job(
        (0.25, 0.75),
        jobs_dir=tmp_path / "jobs",
        job_template_dir=template_dir,
        job_name="second",
    )
    snapshot, constraints = job_template_api._load_parameter_file(
        second.directory / "parameters_constraints.py"
    )

    assert second.unnormalized_variables == pytest.approx((1.5, 15.0))
    assert snapshot[0].ranges == ((0.0, 6.0),)
    assert snapshot[0].normalized_value == pytest.approx(0.25)
    assert snapshot[0].value == pytest.approx(1.5)
    assert snapshot[1].value == pytest.approx(15.0)
    assert constraints == ("continuous - 0.5",)
    assert all(math.isfinite(parameter.value) for parameter in snapshot)
    for filename in ("job_input.json", "variables.json", "parameters_values.py"):
        assert not (second.directory / filename).exists()


def test_materialization_rejects_parameter_count_mismatch(tmp_path):
    template_dir = _make_template(tmp_path / "template", upper=2.0)

    with pytest.raises(ValueError, match="expected 2 normalized values, got 1"):
        prepare_job(
            (0.5,),
            jobs_dir=tmp_path / "jobs",
            job_template_dir=template_dir,
        )


def test_recorded_data_normalizes_history_with_current_ranges(tmp_path, monkeypatch):
    from project.job_template import api as job_template_api
    from project.recorded_data import api as recorded_api

    template_dir = _make_template(tmp_path / "template", upper=6.0)
    monkeypatch.setattr(job_template_api, "TEMPLATE_DIR", template_dir)
    record_root = tmp_path / "recorded_data"
    monkeypatch.setattr(recorded_api, "MODULE_DIR", record_root)
    monkeypatch.setattr(recorded_api, "IND_META_PATH", record_root / "indMeta.jsonl")
    monkeypatch.setattr(recorded_api, "RAWDATA_ARCHIVE_PATH", record_root / "rawData.npz")
    monkeypatch.setattr(recorded_api, "OPT_META_DIR", record_root / "optMeta")
    monkeypatch.setattr(recorded_api, "OPT_META_PATH", record_root / "optMeta" / "optMeta.jsonl")
    recorded_api.record_job_result("historical", (1.5, 15.0), (), status="error")

    ((job_name, normalized),) = recorded_api.get_normalized_variables(status=None)
    assert job_name == "historical"
    assert normalized == pytest.approx((0.25, 0.75))

    (template_dir / "parameters_constraints.py").write_text(
        _parameter_source(upper=3.0),
        encoding="utf-8",
        newline="\n",
    )

    ((job_name, normalized),) = recorded_api.get_normalized_variables(status=None)
    assert job_name == "historical"
    assert normalized == pytest.approx((0.5, 0.75))
