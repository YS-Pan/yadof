from __future__ import annotations

from pathlib import Path
import shutil

import pytest

from project.job_template import api as job_template_api
from project.job_template import hfss_com


def test_hfss_adapter_reads_assigned_values_from_job_parameter_file(tmp_path):
    from project.job_template import parameters_constraints_class

    template_dir = tmp_path / "template"
    job_dir = tmp_path / "job"
    template_dir.mkdir()
    job_dir.mkdir()
    shutil.copy2(Path(parameters_constraints_class.__file__), template_dir / "parameters_constraints_class.py")
    shutil.copy2(Path(parameters_constraints_class.__file__), job_dir / "parameters_constraints_class.py")
    (template_dir / "parameters_constraints.py").write_text(
        '''from __future__ import annotations

try:
    from .parameters_constraints_class import Parameter
except ImportError:
    from parameters_constraints_class import Parameter

PARAMETERS = (
    Parameter("length", ((1.0, 3.0),), unit="mm"),
    Parameter("mode", (1.0, 2.0, 3.0), unit=""),
)
CONSTRAINTS = ()

def get_parameters() -> tuple[Parameter, ...]:
    return tuple(PARAMETERS)
''',
        encoding="utf-8",
        newline="\n",
    )

    raw_values = job_template_api.materialize_job_parameters(
        (0.25, 0.5),
        source_dir=template_dir,
        job_dir=job_dir,
    )
    values = hfss_com._load_parameters_py_value_only(str(job_dir / "parameters_constraints.py"))

    assert raw_values == pytest.approx((1.5, 2.0))
    assert values == {"length": "1.5mm", "mode": "2"}


def test_active_hfss_workflow_uses_parameter_snapshot_directly():
    workflow_path = Path(__file__).resolve().parents[3] / "job_template" / "workflow.py"
    source = workflow_path.read_text(encoding="utf-8")

    assert "set_para(hfss_app)" in source
    assert "load_variables" not in source
    assert "job_input.json" not in source
    assert "parameters_values.py" not in source
