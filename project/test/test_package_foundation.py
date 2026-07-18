from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import stat
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import venv
import zipfile

import pytest
import yadof
from yadof import cli
from yadof.resources import (
    read_documentation_entry,
    read_template_manifest,
    template_names,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _run(command: list[str], *, cwd: Path, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.pop("PYTHONHOME", None)
    environment.pop("PYTHONPATH", None)
    return subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _venv_commands(environment_dir: Path) -> tuple[Path, Path]:
    if os.name == "nt":
        return environment_dir / "Scripts" / "python.exe", environment_dir / "Scripts" / "yadof.exe"
    return environment_dir / "bin" / "python", environment_dir / "bin" / "yadof"


def _file_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def _verify_clean_external_install(wheel_path: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="yadof-package-test-") as temporary_dir:
        external_root = Path(temporary_dir)
        environment_dir = external_root / "clean-environment"
        venv.EnvBuilder(with_pip=True, clear=True).create(environment_dir)
        python_executable, yadof_executable = _venv_commands(environment_dir)
        install = _run(
            [str(python_executable), "-m", "pip", "install", "--no-deps", str(wheel_path)],
            cwd=external_root,
        )
        assert install.returncode == 0, install.stdout + install.stderr

        outside_dir = external_root / "outside-repository"
        outside_dir.mkdir()
        package_query = _run(
            [
                str(python_executable),
                "-c",
                "import pathlib, yadof; print(pathlib.Path(yadof.__file__).resolve().parent)",
            ],
            cwd=outside_dir,
        )
        assert package_query.returncode == 0, package_query.stdout + package_query.stderr
        installed_package_dir = Path(package_query.stdout.strip())
        assert environment_dir.resolve() in installed_package_dir.parents
        assert REPOSITORY_ROOT.resolve() not in installed_package_dir.parents

        original_modes = {
            path: stat.S_IMODE(path.stat().st_mode)
            for path in installed_package_dir.rglob("*")
            if path.is_file()
        }
        before_hashes = _file_hashes(installed_package_dir)
        try:
            for path, mode in original_modes.items():
                path.chmod(mode & ~stat.S_IWUSR & ~stat.S_IWGRP & ~stat.S_IWOTH)

            commands = (
                ([str(yadof_executable), "--help"], "usage: yadof"),
                ([str(yadof_executable), "--version"], f"yadof {yadof.__version__}"),
                ([str(yadof_executable), "version"], yadof.__version__),
                ([str(yadof_executable), "docs", "user"], "# user_doc README"),
                ([str(yadof_executable), "docs", "dev"], "# dev_doc README"),
            )
            for command, expected in commands:
                result = _run(command, cwd=outside_dir)
                assert result.returncode == 0, result.stdout + result.stderr
                assert expected in result.stdout
                assert result.stderr == ""

            workspace_check = _run(
                [
                    str(python_executable),
                    "-c",
                    (
                        "from pathlib import Path; import sys; "
                        "from yadof import WorkspaceContext, load_config; "
                        "from yadof.task_loader import load_task_module; "
                        "root=Path('workspace').resolve(); root.mkdir(); "
                        "task=root/'job_template'; task.mkdir(); "
                        "(root/'config.py').write_text(\"JOBS_DIR='state/jobs'\\n\", encoding='utf-8'); "
                        "[(task/name).write_text('# task\\n', encoding='utf-8') for name in "
                        "('parameters_constraints.py','workflow.py','calc_cost.py')]; "
                        "(task/'helper.py').write_text('VALUE=17\\n', encoding='utf-8'); "
                        "(task/'probe.py').write_text('from helper import VALUE\\n', encoding='utf-8'); "
                        "before=tuple(sys.path); cfg=load_config(root); "
                        "probe=load_task_module(cfg.workspace, 'probe'); "
                        "assert probe.VALUE == 17 and tuple(sys.path) == before; "
                        "assert all(root in (path, *path.parents) for path in cfg.workspace.writable_paths()); "
                        "print(cfg.workspace.jobs_dir)"
                    ),
                ],
                cwd=outside_dir,
            )
            assert workspace_check.returncode == 0, workspace_check.stdout + workspace_check.stderr
            assert "state" in workspace_check.stdout

            assert _file_hashes(installed_package_dir) == before_hashes
        finally:
            for path, mode in original_modes.items():
                if path.exists():
                    path.chmod(mode | stat.S_IWUSR)


def _verify_external_workspace_commands(wheel_path: Path) -> None:
    source_before_hashes = _file_hashes(REPOSITORY_ROOT / "src/yadof")
    with tempfile.TemporaryDirectory(prefix="yadof-workspace-wheel-test-") as temporary_dir:
        external_root = Path(temporary_dir)
        environment_dir = external_root / "runtime-environment"
        venv.EnvBuilder(
            with_pip=True,
            clear=True,
            system_site_packages=True,
        ).create(environment_dir)
        python_executable, yadof_executable = _venv_commands(environment_dir)
        install = _run(
            [str(python_executable), "-m", "pip", "install", "--no-deps", str(wheel_path)],
            cwd=external_root,
        )
        assert install.returncode == 0, install.stdout + install.stderr

        outside_dir = external_root / "outside-repository"
        outside_dir.mkdir()
        package_query = _run(
            [
                str(python_executable),
                "-c",
                "import pathlib, yadof; print(pathlib.Path(yadof.__file__).resolve().parent)",
            ],
            cwd=outside_dir,
        )
        assert package_query.returncode == 0, package_query.stdout + package_query.stderr
        installed_package_dir = Path(package_query.stdout.strip())
        assert environment_dir.resolve() in installed_package_dir.parents
        assert REPOSITORY_ROOT.resolve() not in installed_package_dir.parents

        original_modes = {
            path: stat.S_IMODE(path.stat().st_mode)
            for path in installed_package_dir.rglob("*")
            if path.is_file()
        }
        before_hashes = _file_hashes(installed_package_dir)
        try:
            for path, mode in original_modes.items():
                path.chmod(mode & ~stat.S_IWUSR & ~stat.S_IWGRP & ~stat.S_IWOTH)

            workspace = outside_dir / "generic-workspace"
            initialized = _run(
                [str(yadof_executable), "init", str(workspace)],
                cwd=outside_dir,
            )
            assert initialized.returncode == 0, initialized.stdout + initialized.stderr
            assert initialized.stderr == ""
            checked = _run(
                [str(yadof_executable), "check", "--workspace", str(workspace)],
                cwd=outside_dir,
            )
            assert checked.returncode == 0, checked.stdout + checked.stderr
            assert "Workspace check passed" in checked.stdout
            assert checked.stderr == ""

            smoke_help = _run(
                [str(yadof_executable), "smoke-test", "--help"],
                cwd=outside_dir,
            )
            assert smoke_help.returncode == 0, smoke_help.stdout + smoke_help.stderr
            assert "exactly one individual" in smoke_help.stdout
            assert "no timeout" in smoke_help.stdout
            assert "package self-tests" in smoke_help.stdout
            assert "launch simulator or custom software" in smoke_help.stdout

            smoke = _run(
                [str(yadof_executable), "smoke-test", "--workspace", str(workspace)],
                cwd=outside_dir,
            )
            assert smoke.returncode == 0, smoke.stdout + smoke.stderr
            assert "Smoke test succeeded for exactly one individual" in smoke.stdout
            assert smoke.stderr == ""
            jobs_dir = workspace / "jobs"
            jobs = tuple(path for path in jobs_dir.iterdir() if path.is_dir())
            assert len(jobs) == 1
            successful_job = jobs[0]
            successful_metadata = json.loads(
                (successful_job / "metadata.json").read_text(encoding="utf-8")
            )
            assert successful_metadata["status"] == "done"
            assert successful_metadata["timed_out"] is False
            assert successful_metadata["yadof_version"] == yadof.__version__
            assert successful_metadata["workspace_identity"]["root"] == str(workspace.resolve())
            assert successful_metadata["effective_config_summary"]["EVALUATION_TIMEOUT_SEC"]["value"] is None
            assert (successful_job / "worker_misc.py").is_file()
            assert (successful_job / "yadof_worker_config.json").is_file()
            assert not (successful_job / "calc_cost.py").exists()
            assert not (successful_job / "cost.json").exists()
            recorded_dir = workspace / "recorded_data"
            successful_records = [
                json.loads(line)
                for line in (recorded_dir / "indMeta.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            assert len(successful_records) == 1
            assert successful_records[0]["status"] == "completed"
            assert successful_records[0]["job_name"] == successful_job.name
            assert (recorded_dir / "rawData.npz").is_file()
            assert (recorded_dir / "indMeta.jsonl.lock").is_file()

            workflow_path = workspace / "job_template/workflow.py"
            workflow_path.write_text(
                workflow_path.read_text(encoding="utf-8") + "\n# edited task\n",
                encoding="utf-8",
            )
            refused = _run(
                [str(yadof_executable), "smoke-test", "--workspace", str(workspace)],
                cwd=outside_dir,
            )
            assert refused.returncode == 1
            assert "--real-task" in refused.stderr
            assert len(tuple(path for path in jobs_dir.iterdir() if path.is_dir())) == 1

            workflow_path.write_text(
                "raise RuntimeError('installed workflow failure')\n",
                encoding="utf-8",
            )
            failed = _run(
                [
                    str(yadof_executable),
                    "smoke-test",
                    "--workspace",
                    str(workspace),
                    "--real-task",
                ],
                cwd=outside_dir,
            )
            assert failed.returncode == 1
            assert "no finite objective cost" in failed.stderr
            failed_job = sorted(
                (path for path in jobs_dir.iterdir() if path.is_dir()),
                key=lambda path: path.name,
            )[-1]
            assert json.loads((failed_job / "metadata.json").read_text(encoding="utf-8"))["status"] == "error"

            workflow_path.write_text("import time\ntime.sleep(5)\n", encoding="utf-8")
            timeout_check = _run(
                [
                    str(python_executable),
                    "-c",
                    (
                        "import json, math; from pathlib import Path; "
                        "from yadof.evaluate_manager import evaluate_population; "
                        f"root=Path({str(workspace)!r}); "
                        "costs=evaluate_population(root, ((0.5,),), mode='local', timeout_sec=0.1); "
                        "assert costs == ((math.inf,),); "
                        "job=sorted((root/'jobs').iterdir())[-1]; "
                        "meta=json.loads((job/'metadata.json').read_text(encoding='utf-8')); "
                        "assert meta['status'] == 'timeout' and meta['timed_out'] is True"
                    ),
                ],
                cwd=outside_dir,
                timeout=30,
            )
            assert timeout_check.returncode == 0, timeout_check.stdout + timeout_check.stderr

            all_records = [
                json.loads(line)
                for line in (recorded_dir / "indMeta.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            assert sorted(record["status"] for record in all_records) == [
                "completed",
                "error",
                "timeout",
            ]

            workspace_paths = {
                path.relative_to(workspace).as_posix()
                for path in workspace.rglob("*")
            }
            assert {
                ".yadof/workspace.json",
                "config.py",
                "job_template/calc_cost.py",
                "job_template/parameters_constraints.py",
                "job_template/workflow.py",
                "recorded_data/indMeta.jsonl",
                "recorded_data/indMeta.jsonl.lock",
                "recorded_data/rawData.npz",
            } <= workspace_paths
            for forbidden in (
                "job_template/api.py",
                "job_template/parameters_constraints_class.py",
                "job_template/rawdata_contract.py",
                "job_template/cost_misc.py",
                "optimize",
                "evaluate_manager",
                "surrogate",
            ):
                assert forbidden not in workspace_paths
            assert not tuple(recorded_dir.rglob("*.tmp"))
            assert not any("__pycache__" in path for path in workspace_paths)
            marker_text = (workspace / ".yadof/workspace.json").read_text(encoding="utf-8")
            assert str(installed_package_dir) not in marker_text
            assert _file_hashes(installed_package_dir) == before_hashes
            assert _file_hashes(REPOSITORY_ROOT / "src/yadof") == source_before_hashes
        finally:
            for path, mode in original_modes.items():
                if path.exists():
                    path.chmod(mode | stat.S_IWUSR)


def test_package_metadata_and_source_resources() -> None:
    metadata = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = metadata["project"]

    assert project["name"] == "yadof"
    assert project["dynamic"] == ["version"]
    assert project["requires-python"] == ">=3.10"
    assert project["scripts"] == {"yadof": "yadof.cli:main"}
    assert {"surrogate", "plot", "hfss", "dev"} <= set(project["optional-dependencies"])
    assert metadata["tool"]["hatch"]["version"]["path"] == "src/yadof/_version.py"
    assert yadof.__version__ == "0.1.0"

    assert read_documentation_entry("dev").startswith("# dev_doc README")
    assert read_documentation_entry("user").startswith("# user_doc README")
    assert template_names() == ("default",)
    manifest = read_template_manifest("default")
    assert manifest["name"] == "default"
    assert manifest["template_version"] == 1

    template_root = REPOSITORY_ROOT / "src" / "yadof" / "_resources" / "templates" / "default"
    template_text = "\n".join(
        path.read_text(encoding="utf-8") for path in template_root.rglob("*") if path.is_file()
    ).lower()
    for forbidden in ("hfss", "ansys", ".aedt", "newchoke"):
        assert forbidden not in template_text


def test_minimal_cli_output_and_streams(capsys) -> None:
    assert cli.main([]) == 0
    output = capsys.readouterr()
    assert "usage: yadof" in output.out
    assert output.err == ""

    assert cli.main(["version"]) == 0
    output = capsys.readouterr()
    assert output.out == f"{yadof.__version__}\n"
    assert output.err == ""

    assert cli.main(["docs", "user"]) == 0
    output = capsys.readouterr()
    assert output.out.startswith("# user_doc README")
    assert output.err == ""


def test_wheel_sdist_and_clean_external_install(tmp_path: Path) -> None:
    if importlib.util.find_spec("build") is None or importlib.util.find_spec("hatchling") is None:
        pytest.skip("install the yadof dev extra to run package artifact tests")

    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    build = _run(
        [sys.executable, "-m", "build", "--no-isolation", "--outdir", str(artifact_dir)],
        cwd=REPOSITORY_ROOT,
    )
    assert build.returncode == 0, build.stdout + build.stderr

    wheel_path = next(artifact_dir.glob("yadof-*.whl"))
    sdist_path = next(artifact_dir.glob("yadof-*.tar.gz"))

    with zipfile.ZipFile(wheel_path) as archive:
        wheel_names = set(archive.namelist())
        assert "yadof/__init__.py" in wheel_names
        assert "yadof/cli.py" in wheel_names
        assert "yadof/workspace.py" in wheel_names
        assert "yadof/config.py" in wheel_names
        assert "yadof/task_loader.py" in wheel_names
        assert "yadof/workspace_manifest.py" in wheel_names
        assert "yadof/workspace_init.py" in wheel_names
        assert "yadof/workspace_check.py" in wheel_names
        assert "yadof/smoke_test.py" in wheel_names
        assert "yadof/evaluate_manager/__init__.py" in wheel_names
        assert "yadof/evaluate_manager/api.py" in wheel_names
        assert "yadof/evaluate_manager/job_files.py" in wheel_names
        assert "yadof/evaluate_manager/job_result.py" in wheel_names
        assert "yadof/evaluate_manager/local_runner.py" in wheel_names
        assert "yadof/evaluate_manager/recorded_data_client.py" in wheel_names
        assert "yadof/evaluate_manager/types.py" in wheel_names
        assert "yadof/evaluate_manager/worker_files/worker_misc.py" in wheel_names
        assert "yadof/recorded_data/__init__.py" in wheel_names
        assert "yadof/recorded_data/api.py" in wheel_names
        assert "yadof/recorded_data/manifest_store.py" in wheel_names
        assert "yadof/recorded_data/paths.py" in wheel_names
        assert "yadof/recorded_data/query.py" in wheel_names
        assert "yadof/recorded_data/rawdata_store.py" in wheel_names
        assert "yadof/recorded_data/records.py" in wheel_names
        assert "yadof/recorded_data/utils.py" in wheel_names
        assert "yadof/job_template/api.py" in wheel_names
        assert "yadof/job_template/parameters_constraints_class.py" in wheel_names
        assert "yadof/job_template/rawdata_contract.py" in wheel_names
        assert "yadof/job_template/cost_misc.py" in wheel_names
        assert "yadof/_resources/templates/default/README.md" in wheel_names
        assert "yadof/_resources/templates/default/template.json" in wheel_names
        assert "yadof/_resources/templates/default/workspace/config.py" in wheel_names
        assert (
            "yadof/_resources/templates/default/workspace/job_template/"
            "parameters_constraints.py"
        ) in wheel_names
        assert (
            "yadof/_resources/templates/default/workspace/job_template/workflow.py"
        ) in wheel_names
        assert (
            "yadof/_resources/templates/default/workspace/job_template/calc_cost.py"
        ) in wheel_names
        assert "yadof/_resources/docs/dev_doc/README.md" in wheel_names
        assert "yadof/_resources/docs/user_doc/README.md" in wheel_names
        entry_points_name = next(name for name in wheel_names if name.endswith(".dist-info/entry_points.txt"))
        metadata_name = next(name for name in wheel_names if name.endswith(".dist-info/METADATA"))
        assert "yadof = yadof.cli:main" in archive.read(entry_points_name).decode("utf-8")
        built_metadata = archive.read(metadata_name).decode("utf-8")
        assert "Name: yadof" in built_metadata
        assert f"Version: {yadof.__version__}" in built_metadata
        assert "Requires-Dist: numpy" in built_metadata
        assert "Requires-Dist: pymoo" in built_metadata
        assert not any(name.startswith("project/") for name in wheel_names)
        assert not any(name.lower().endswith(".aedt") for name in wheel_names)
        assert not any("__pycache__" in name or name.endswith((".pyc", ".pyo")) for name in wheel_names)

    with tarfile.open(sdist_path, "r:gz") as archive:
        sdist_names = set(archive.getnames())
        assert any(name.endswith("/src/yadof/cli.py") for name in sdist_names)
        assert any(name.endswith("/dev_doc/README.md") for name in sdist_names)
        assert any(name.endswith("/user_doc/README.md") for name in sdist_names)
        assert any(name.endswith("/src/yadof/_resources/templates/default/README.md") for name in sdist_names)
        assert not any(
            len(PurePosixPath(name).parts) > 1 and PurePosixPath(name).parts[1] == "project"
            for name in sdist_names
        )
        assert not any(name.lower().endswith(".aedt") for name in sdist_names)
        assert not any("__pycache__" in name or name.endswith((".pyc", ".pyo")) for name in sdist_names)

    _verify_clean_external_install(wheel_path)
    _verify_external_workspace_commands(wheel_path)
