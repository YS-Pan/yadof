from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pytest

import yadof
from yadof.config import ConfigError, load_config
from yadof.job_template import (
    Parameter,
    calculate_cost,
    get_parameter_definition_signature,
    materialize_job_parameters,
    validate_rawdata_item,
    validate_task,
)
from yadof.task_loader import load_task_module
from yadof.workspace import WorkspaceContext


def _task_files(root: Path, *, limit: int, offset: int) -> WorkspaceContext:
    root.mkdir()
    task_dir = root / "job_template"
    task_dir.mkdir()
    (root / "config.py").write_text(
        "EVALUATION_MODE = 'local'\n"
        "OPTIMIZE_POPULATION_SIZE = 21\n"
        "JOBS_DIR = 'state/jobs'\n",
        encoding="utf-8",
    )
    (task_dir / "local_values.py").write_text(
        f"LIMIT = {limit}\nOFFSET = {offset}\n", encoding="utf-8"
    )
    (task_dir / "parameters_constraints.py").write_text(
        "from yadof.job_template import Parameter\n"
        "from local_values import LIMIT\n"
        "PARAMETERS = (Parameter('x', ((0, LIMIT),), unit='m'),)\n"
        "CONSTRAINTS = ()\n"
        "def get_parameters():\n"
        "    return tuple(PARAMETERS)\n",
        encoding="utf-8",
    )
    (task_dir / "calc_cost.py").write_text(
        "from . import parameters_constraints\n"
        "from local_values import OFFSET\n"
        "def calculate_cost(sample_rawdata, raw_variables=None):\n"
        "    return (float(sample_rawdata[0]['value']) + OFFSET,)\n"
        "def get_objective_names():\n"
        "    return (f'objective_{OFFSET}',)\n"
        "def get_objective_count():\n"
        "    return len(get_objective_names())\n",
        encoding="utf-8",
    )
    (task_dir / "workflow.py").write_text(
        "# Workflow execution is intentionally not triggered by task validation.\n",
        encoding="utf-8",
    )
    return WorkspaceContext.from_path(root)


def test_workspace_paths_are_explicit_absolute_and_read_only_to_construct(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    context = WorkspaceContext.from_path(root)

    assert context.root == root.resolve()
    assert context.config_file == root.resolve() / "config.py"
    assert context.job_template_dir == root.resolve() / "job_template"
    assert context.jobs_dir == root.resolve() / "jobs"
    assert context.recorded_data_dir == root.resolve() / "recorded_data"
    assert context.surrogate_checkpoint_dir == root.resolve() / ".yadof/surrogate/checkpoints"
    assert context.logs_dir == root.resolve() / ".yadof/logs"
    assert context.tool_output_dir == root.resolve() / ".yadof/tool_output"
    assert not root.exists()

    package_dir = Path(yadof.__file__).resolve().parent
    assert all(package_dir not in path.parents for path in context.writable_paths())


def test_config_precedence_paths_sources_and_non_mutating_override(tmp_path: Path) -> None:
    context = _task_files(tmp_path / "workspace", limit=2, offset=1)
    original = context.config_file.read_bytes()

    config = load_config(
        context,
        overrides={"EVALUATION_MODE": "distributed", "OPTIMIZE_POPULATION_SIZE": 8},
    )

    assert config.EVALUATION_MODE == "distributed"
    assert config.OPTIMIZE_POPULATION_SIZE == 8
    assert config.HTCONDOR_REQUEST_CPUS == 1
    assert config.workspace.jobs_dir == context.root / "state/jobs"
    assert config.JOBS_DIR == context.root / "state/jobs"
    assert config.source_for("HTCONDOR_REQUEST_CPUS") == "package default"
    assert config.source_for("JOBS_DIR").startswith("workspace config:")
    assert config.source_for("EVALUATION_MODE") == "temporary override"
    assert "# temporary override" in config.describe()
    assert context.config_file.read_bytes() == original


def test_config_accepts_explicit_absolute_task_path(tmp_path: Path) -> None:
    context = _task_files(tmp_path / "workspace", limit=2, offset=1)
    external = tmp_path / "external_task"
    external.mkdir()
    for name in ("parameters_constraints.py", "workflow.py", "calc_cost.py"):
        (external / name).write_text("# explicit task path\n", encoding="utf-8")
    context.config_file.write_text(
        f"JOB_TEMPLATE_DIR = {str(external)!r}\n", encoding="utf-8"
    )

    config = load_config(context)

    assert config.workspace.job_template_dir == external.resolve()
    assert config.JOB_TEMPLATE_DIR == external.resolve()


def test_config_preserves_explicit_context_paths_until_file_override(tmp_path: Path) -> None:
    base = _task_files(tmp_path / "workspace", limit=2, offset=1)
    explicit_jobs = tmp_path / "external_jobs"
    context = WorkspaceContext.from_path(base.root, jobs_dir=explicit_jobs)

    config = load_config(context)

    # The config file in this fixture explicitly wins with its relative JOBS_DIR.
    assert config.workspace.jobs_dir == base.root / "state/jobs"
    assert config.source_for("JOBS_DIR").startswith("workspace config:")

    base.config_file.write_text("EVALUATION_MODE = 'local'\n", encoding="utf-8")
    config = load_config(context)
    assert config.workspace.jobs_dir == explicit_jobs.resolve()
    assert config.source_for("JOBS_DIR") == "explicit workspace context"


@pytest.mark.parametrize(
    ("config_text", "message"),
    [
        ("UNKNOWN_SETTING = 1\n", "unknown config setting"),
        ("OPTIMIZE_POPULATION_SIZE = 'many'\n", "must be an integer"),
        ("EVALUATION_MODE = 'cluster'\n", "must be 'local' or 'distributed'"),
        ("HTCONDOR_JOB_TIMEOUT_MODE = 'sometimes'\n", "must be 'auto' or 'fixed'"),
        ("SURROGATE_RAWDATA_IMPORTANCE_FLOOR = -0.1\n", "must be >= 0"),
    ],
)
def test_config_rejects_unknown_names_types_and_modes(
    tmp_path: Path, config_text: str, message: str
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "config.py").write_text(config_text, encoding="utf-8")

    with pytest.raises(ConfigError, match=message):
        load_config(root, validate_task_paths=False)


def test_config_validates_required_task_paths_before_batch_work(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "config.py").write_text("EVALUATION_MODE = 'local'\n", encoding="utf-8")
    task_dir = root / "job_template"
    task_dir.mkdir()
    (task_dir / "parameters_constraints.py").write_text("PARAMETERS = ()\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="workflow.py, calc_cost.py"):
        load_config(root)


def test_config_and_task_loader_report_system_exit_as_validation_errors(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "config.py").write_text("raise SystemExit(9)\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="failed to load workspace config"):
        load_config(root, validate_task_paths=False)

    context = _task_files(tmp_path / "task_workspace", limit=2, offset=1)
    (context.job_template_dir / "probe.py").write_text(
        "raise SystemExit(7)\n", encoding="utf-8"
    )
    with pytest.raises(ImportError, match="failed to load task module"):
        load_task_module(context, "probe")


def test_two_workspaces_and_fresh_edits_are_module_and_cache_isolated(tmp_path: Path) -> None:
    first = _task_files(tmp_path / "first", limit=2, offset=1)
    second = _task_files(tmp_path / "second", limit=8, offset=7)
    original_sys_path = tuple(sys.path)
    original_local_module = sys.modules.get("local_values")

    assert validate_task(first).parameter_names == ("x",)
    assert validate_task(first).objective_names == ("objective_1",)
    assert validate_task(second).objective_names == ("objective_7",)
    assert get_parameter_definition_signature(first)["parameters"][0]["ranges"] == [[0.0, 2.0]]
    assert get_parameter_definition_signature(second)["parameters"][0]["ranges"] == [[0.0, 8.0]]
    assert calculate_cost(first, (({"value": 3.0},),)) == ((4.0,),)
    assert calculate_cost(second, (({"value": 3.0},),)) == ((10.0,),)

    # Same-length content changes must be visible without relying on mtime/pyc rules.
    (first.job_template_dir / "local_values.py").write_text(
        "LIMIT = 4\nOFFSET = 5\n", encoding="utf-8"
    )
    first.config_file.write_text(
        "EVALUATION_MODE = 'local'\n"
        "OPTIMIZE_POPULATION_SIZE = 34\n"
        "JOBS_DIR = 'state/jobs'\n",
        encoding="utf-8",
    )

    assert validate_task(first).objective_names == ("objective_5",)
    assert calculate_cost(first, (({"value": 3.0},),)) == ((8.0,),)
    assert load_config(first).OPTIMIZE_POPULATION_SIZE == 34
    assert validate_task(second).objective_names == ("objective_7",)
    assert tuple(sys.path) == original_sys_path
    assert sys.modules.get("local_values") is original_local_module
    assert not tuple(first.root.rglob("__pycache__"))
    assert not tuple(second.root.rglob("__pycache__"))


def test_task_loader_supports_local_packages_without_global_cache(tmp_path: Path) -> None:
    context = _task_files(tmp_path / "workspace", limit=2, offset=1)
    helpers = context.job_template_dir / "helpers"
    helpers.mkdir()
    (helpers / "__init__.py").write_text("from .value import VALUE\n", encoding="utf-8")
    (helpers / "value.py").write_text("VALUE = 42\n", encoding="utf-8")
    (context.job_template_dir / "probe.py").write_text(
        "from helpers import VALUE\n", encoding="utf-8"
    )

    loaded = load_task_module(context, "probe")

    assert loaded.VALUE == 42
    assert "helpers" not in sys.modules
    assert "helpers.value" not in sys.modules


def test_packaged_parameter_materialization_and_rawdata_contract(tmp_path: Path) -> None:
    context = _task_files(tmp_path / "workspace", limit=4, offset=1)
    job_dir = context.root / "jobs" / "one"

    raw_values = materialize_job_parameters(context, (0.25,), job_dir=job_dir)
    snapshot = (job_dir / "parameters_constraints.py").read_text(encoding="utf-8")
    loaded_snapshot = load_task_module(
        WorkspaceContext.from_path(context.root, job_template_dir=job_dir),
        "parameters_constraints",
    )
    rawdata = {
        "values": np.asarray([1.0, 2.0]),
        "metadata": '{"schema_version": 1, "shape": [2]}',
    }

    assert raw_values == (1.0,)
    assert "class Parameter:" in snapshot
    assert "import yadof" not in snapshot
    assert not (job_dir / "parameters_constraints_class.py").exists()
    assert not isinstance(loaded_snapshot.PARAMETERS[0], Parameter)
    assert loaded_snapshot.PARAMETERS[0].name == "x"
    assert loaded_snapshot.PARAMETERS[0].value == pytest.approx(1.0)
    assert validate_rawdata_item(rawdata)["values"].tolist() == [1.0, 2.0]
