from __future__ import annotations

from pathlib import Path
import shutil
from uuid import uuid4

import pytest

from project.com_lib import hfss_com
from project.job_template import api as job_template_api


def test_hfss_adapter_reads_assigned_values_from_job_parameter_file(tmp_path):
    from project.job_template import parameters_constraints_class

    continuous_name = f"parameter_{uuid4().hex}"
    discrete_name = f"parameter_{uuid4().hex}"
    template_dir = tmp_path / "template"
    job_dir = tmp_path / "job"
    template_dir.mkdir()
    job_dir.mkdir()
    shutil.copy2(Path(parameters_constraints_class.__file__), template_dir / "parameters_constraints_class.py")
    shutil.copy2(Path(parameters_constraints_class.__file__), job_dir / "parameters_constraints_class.py")
    (template_dir / "parameters_constraints.py").write_text(
        f'''from __future__ import annotations

try:
    from .parameters_constraints_class import Parameter
except ImportError:
    from parameters_constraints_class import Parameter

PARAMETERS = (
    Parameter({continuous_name!r}, ((1.0, 3.0),), unit="mm"),
    Parameter({discrete_name!r}, (1.0, 2.0, 3.0), unit=""),
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
    assert values == {continuous_name: "1.5mm", discrete_name: "2"}
