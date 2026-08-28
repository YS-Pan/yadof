from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import re
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
    ResourceNotFoundError,
    documentation_names,
    read_documentation,
    read_documentation_entry,
    read_template_manifest,
    template_names,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


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
                (
                    [str(yadof_executable), "docs", "list", "user"],
                    "optimization_workflow.md",
                ),
                (
                    [str(yadof_executable), "docs", "show", "user", "README.md"],
                    "# yadof user-workflow guide for AI agents",
                ),
                (
                    [str(yadof_executable), "docs", "show", "dev", "README.md"],
                    "# dev_doc README",
                ),
                (
                    [str(yadof_executable), "docs", "bundle", "user"],
                    "===== user/README.md =====",
                ),
                (
                    [str(yadof_executable), "view", "surrogate", "--help"],
                    "does not train",
                ),
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
                        "task=root/'job_template'; task.mkdir(); submit=root/'submit'; submit.mkdir(); "
                        "(root/'config.py').write_text(\"JOBS_DIR='state/jobs'\\n\", encoding='utf-8'); "
                        "[(task/name).write_text('# task\\n', encoding='utf-8') for name in "
                        "('parameters_constraints.py','workflow.py')]; "
                        "[(submit/name).write_text('# submit task\\n', encoding='utf-8') for name in "
                        "('calc_cost.py','optimization.py')]; "
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
            assert successful_metadata["execute_machine"]
            assert successful_metadata["yadof_version"] == yadof.__version__
            assert successful_metadata["workspace_identity"]["root"] == str(workspace.resolve())
            assert successful_metadata["effective_config_summary"]["EVALUATION_TIMEOUT_SEC"]["value"] is None
            assert (successful_job / "worker_misc.py").is_file()
            assert not (successful_job / "yadof_worker_package.zip").exists()
            assert not (successful_job / "yadof_worker_config.json").exists()
            assert not (successful_job / "calc_cost.py").exists()
            assert not (successful_job / "cost.json").exists()
            recorded_dir = workspace / "recorded_data"
            queried = _run(
                [
                    str(python_executable),
                    "-c",
                    (
                        "import json; from pathlib import Path; "
                        "from yadof.recorded_data import list_records; "
                        f"print(json.dumps(list_records(Path({str(workspace)!r}))))"
                    ),
                ],
                cwd=outside_dir,
            )
            assert queried.returncode == 0, queried.stdout + queried.stderr
            successful_records = json.loads(queried.stdout)
            assert len(successful_records) == 1
            assert successful_records[0]["status"] == "completed"
            assert successful_records[0]["job_name"] == successful_job.name
            assert (
                successful_records[0]["job_metadata"]["execute_machine"]
                == successful_metadata["execute_machine"]
            )
            assert len(tuple(recorded_dir.glob("segments/*/*/segment_*.zip"))) == 1

            run_workspace = outside_dir / "run-workspace"
            run_initialized = _run(
                [str(yadof_executable), "init", str(run_workspace)],
                cwd=outside_dir,
            )
            assert run_initialized.returncode == 0, run_initialized.stdout + run_initialized.stderr
            (run_workspace / "config.py").write_text(
                'EVALUATION_MODE = "local"\n'
                "OPTIMIZE_POPULATION_SIZE = 2\n"
                "OPTIMIZE_SMOKE_TEST_ENABLED = False\n",
                encoding="utf-8",
            )
            (run_workspace / "submit/optimization.py").write_text(
                "from yadof.optimize import by_objective_count, gpsaf, pymoo_ga, pymoo_nsga3\n"
                "from yadof.surrogate import conditional_inr\n"
                "def build_optimization():\n"
                "    search = by_objective_count(single=pymoo_ga(), multi=pymoo_nsga3())\n"
                "    return gpsaf(search=search, surrogate=conditional_inr(), alpha=1, beta=0)\n",
                encoding="utf-8",
            )
            for generation in (2, 3):
                run_result = _run(
                    [
                        str(yadof_executable),
                        "run",
                        "--workspace",
                        str(run_workspace),
                        "--generations",
                        "1",
                        "--start-generation",
                        str(generation),
                        "--population-size",
                        "2",
                        "--no-smoke-test",
                    ],
                    cwd=outside_dir,
                    timeout=60,
                )
                assert run_result.returncode == 0, run_result.stdout + run_result.stderr
                assert f"gen={generation}" in run_result.stdout
            for view_kind in ("cost", "time"):
                viewed = _run(
                    [
                        str(yadof_executable),
                        "view",
                        view_kind,
                        "--workspace",
                        str(run_workspace),
                    ],
                    cwd=outside_dir,
                )
                assert viewed.returncode == 0, viewed.stdout + viewed.stderr
                assert viewed.stdout.strip()
                assert "saved:" in viewed.stdout
                assert len(
                    tuple(
                        (run_workspace / ".yadof" / "tool_output").glob(
                            f"{view_kind}_*.png"
                        )
                    )
                ) == 1
            cleared = _run(
                [
                    str(yadof_executable),
                    "history",
                    "clear",
                    "--workspace",
                    str(run_workspace),
                    "--yes",
                ],
                cwd=outside_dir,
            )
            assert cleared.returncode == 0, cleared.stdout + cleared.stderr
            assert "history cleared" in cleared.stdout.lower()
            assert not tuple((run_workspace / "recorded_data").iterdir())

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

            queried = _run(
                [
                    str(python_executable),
                    "-c",
                    (
                        "import json; from pathlib import Path; "
                        "from yadof.recorded_data import list_records; "
                        f"print(json.dumps(list_records(Path({str(workspace)!r}))))"
                    ),
                ],
                cwd=outside_dir,
            )
            assert queried.returncode == 0, queried.stdout + queried.stderr
            all_records = json.loads(queried.stdout)
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
                "job_template/parameters_constraints.py",
                "job_template/workflow.py",
                "submit/calc_cost.py",
                "submit/optimization.py",
                "recorded_data/segments",
            } <= workspace_paths
            assert any(path.endswith(".zip") for path in workspace_paths)
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
    assert "psutil>=5.9,<8" in project["dependencies"]
    assert {"surrogate", "qnehvi", "plot", "hfss", "dev"} <= set(
        project["optional-dependencies"]
    )
    assert project["optional-dependencies"]["surrogate"] == ["torch>=2.2,<3"]
    assert project["optional-dependencies"]["qnehvi"] == [
        "torch>=2.4,<3",
        "botorch>=0.18,<0.19",
    ]
    assert metadata["tool"]["hatch"]["version"]["path"] == "src/yadof/_version.py"
    assert yadof.__version__ == "0.4.2"

    assert read_documentation_entry("dev").startswith("# dev_doc README")
    assert read_documentation_entry("user").startswith(
        "# yadof user-workflow guide for AI agents"
    )
    assert read_documentation("user", "adapters/README.md").startswith(
        "# Packaged adapters"
    )
    source_user_names = {
        path.relative_to(REPOSITORY_ROOT / "user_doc").as_posix()
        for path in (REPOSITORY_ROOT / "user_doc").rglob("*")
        if path.is_file()
    }
    assert set(documentation_names("user")) == source_user_names
    with pytest.raises(ResourceNotFoundError):
        read_documentation("user", "../README.md")
    with pytest.raises(ValueError, match="expected one of: dev, user"):
        documentation_names("agent")  # type: ignore[arg-type]
    assert template_names() == ("default",)
    manifest = read_template_manifest("default")
    assert manifest["name"] == "default"
    assert set(manifest) == {
        "description",
        "files",
        "name",
        "rawdata_schema_version",
        "schema_version",
    }

    template_root = REPOSITORY_ROOT / "src" / "yadof" / "_resources" / "templates" / "default"
    template_text = "\n".join(
        path.read_text(encoding="utf-8") for path in template_root.rglob("*") if path.is_file()
    ).lower()
    for forbidden in ("hfss", "ansys", ".aedt", "newchoke"):
        assert forbidden not in template_text


def test_user_documentation_links_resolve_inside_source_tree() -> None:
    root = REPOSITORY_ROOT / "user_doc"
    for document in root.rglob("*.md"):
        for target in MARKDOWN_LINK.findall(document.read_text(encoding="utf-8")):
            path_text = target.split("#", 1)[0]
            if not path_text or "://" in path_text:
                continue
            assert (document.parent / path_text).is_file(), (
                f"broken user documentation link in {document.relative_to(root)}: {target}"
            )


def test_surrogate_viewer_developer_documentation_links_resolve() -> None:
    root_entry = REPOSITORY_ROOT / "dev_doc" / "README.md"
    root_targets = MARKDOWN_LINK.findall(root_entry.read_text(encoding="utf-8"))
    expected = "../src/yadof/tools/surrogate_viewer/dev_doc/README.md"
    assert expected in root_targets
    assert (root_entry.parent / expected).is_file()

    viewer_root = (
        REPOSITORY_ROOT
        / "src"
        / "yadof"
        / "tools"
        / "surrogate_viewer"
        / "dev_doc"
    )
    for document in viewer_root.rglob("*.md"):
        for target in MARKDOWN_LINK.findall(document.read_text(encoding="utf-8")):
            path_text = target.split("#", 1)[0]
            if not path_text or "://" in path_text:
                continue
            assert (document.parent / path_text).is_file(), (
                "broken surrogate viewer documentation link in "
                f"{document.relative_to(viewer_root)}: {target}"
            )


def test_cost_viewer_developer_documentation_links_resolve() -> None:
    root_entry = REPOSITORY_ROOT / "dev_doc" / "README.md"
    root_targets = MARKDOWN_LINK.findall(root_entry.read_text(encoding="utf-8"))
    expected = "../src/yadof/tools/cost_viewer/dev_doc/README.md"
    assert expected in root_targets
    assert (root_entry.parent / expected).is_file()

    viewer_root = (
        REPOSITORY_ROOT
        / "src"
        / "yadof"
        / "tools"
        / "cost_viewer"
        / "dev_doc"
    )
    for document in viewer_root.rglob("*.md"):
        for target in MARKDOWN_LINK.findall(document.read_text(encoding="utf-8")):
            path_text = target.split("#", 1)[0]
            if not path_text or "://" in path_text:
                continue
            assert (document.parent / path_text).is_file(), (
                "broken cost viewer documentation link in "
                f"{document.relative_to(viewer_root)}: {target}"
            )


def test_minimal_cli_output_and_streams(capsys) -> None:
    assert cli.main([]) == 0
    output = capsys.readouterr()
    assert "usage: yadof" in output.out
    assert output.err == ""

    assert cli.main(["version"]) == 0
    output = capsys.readouterr()
    assert output.out == f"{yadof.__version__}\n"
    assert output.err == ""

    assert cli.main(["docs", "show", "user", "README.md"]) == 0
    output = capsys.readouterr()
    assert output.out.startswith("# yadof user-workflow guide for AI agents")
    assert output.err == ""

    assert cli.main(["docs", "list", "user"]) == 0
    output = capsys.readouterr()
    assert output.out.splitlines()[0] == "README.md"
    assert "adapters/hfss_com.md" in output.out
    assert output.err == ""

    assert cli.main(["docs", "bundle", "user"]) == 0
    output = capsys.readouterr()
    assert output.out.startswith(
        "===== user/README.md =====\n# yadof user-workflow guide for AI agents"
    )
    assert "===== user/optimization_workflow.md =====" in output.out
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
        assert "yadof/cli/__init__.py" in wheel_names
        assert "yadof/cli/main.py" in wheel_names
        assert "yadof/cli/docs.py" in wheel_names
        assert "yadof/cli/run.py" in wheel_names
        assert "yadof/cli/smoke.py" in wheel_names
        assert "yadof/workspace/__init__.py" in wheel_names
        assert "yadof/workspace/context.py" in wheel_names
        assert "yadof/config.py" in wheel_names
        assert "yadof/task_loader.py" in wheel_names
        assert "yadof/workspace/manifest.py" in wheel_names
        assert "yadof/workspace/init.py" in wheel_names
        assert "yadof/workspace/check.py" in wheel_names
        assert "yadof/evaluate_manager/__init__.py" in wheel_names
        assert "yadof/evaluate_manager/api.py" in wheel_names
        assert "yadof/evaluate_manager/job_files.py" in wheel_names
        assert "yadof/evaluate_manager/job_result.py" in wheel_names
        assert "yadof/evaluate_manager/local_runner.py" in wheel_names
        assert "yadof/evaluate_manager/local_resources.py" in wheel_names
        assert "yadof/evaluate_manager/condor_runner.py" in wheel_names
        assert "yadof/evaluate_manager/resource_calibration.py" in wheel_names
        assert "yadof/evaluate_manager/resource_requests.py" in wheel_names
        assert "yadof/evaluate_manager/resource_retries.py" in wheel_names
        assert "yadof/evaluate_manager/time_limits.py" in wheel_names
        assert "yadof/evaluate_manager/finalizer.py" in wheel_names
        assert "yadof/evaluate_manager/recorded_data_client.py" not in wheel_names
        assert "yadof/evaluate_manager/types.py" in wheel_names
        assert "yadof/evaluate_manager/worker_files/worker_misc.py" in wheel_names
        assert "yadof/evaluate_manager/worker_files/sitecustomize.py" not in wheel_names
        assert "yadof/evaluate_manager/worker_files/yadof_worker.py" not in wheel_names
        assert "yadof/evaluate_manager/worker_files/run_workflow.py" not in wheel_names
        assert "yadof/recorded_data/__init__.py" in wheel_names
        assert "yadof/recorded_data/api.py" in wheel_names
        assert "yadof/recorded_data/campaign_lock.py" in wheel_names
        assert "yadof/recorded_data/paths.py" in wheel_names
        assert "yadof/recorded_data/query.py" in wheel_names
        assert "yadof/recorded_data/rawdata.py" in wheel_names
        assert "yadof/recorded_data/records.py" in wheel_names
        assert "yadof/recorded_data/segment_store.py" in wheel_names
        assert "yadof/recorded_data/session.py" in wheel_names
        assert "yadof/recorded_data/manifest_store.py" not in wheel_names
        assert "yadof/recorded_data/rawdata_store.py" not in wheel_names
        assert "yadof/recorded_data/utils.py" in wheel_names
        assert "yadof/task_snapshot.py" in wheel_names
        assert "yadof/job_template/api.py" in wheel_names
        assert "yadof/job_template/parameters_constraints_class.py" in wheel_names
        assert "yadof/job_template/rawdata_contract.py" in wheel_names
        assert "yadof/job_template/cost_misc.py" in wheel_names
        assert "yadof/optimize/api.py" in wheel_names
        assert "yadof/optimize/components.py" in wheel_names
        assert "yadof/optimize/gpsaf/__init__.py" in wheel_names
        assert "yadof/optimize/gpsaf/assistance.py" in wheel_names
        assert "yadof/optimize/gpsaf/phases.py" in wheel_names
        assert "yadof/optimize/gpsaf/records.py" in wheel_names
        assert "yadof/optimize/pymoo/__init__.py" in wheel_names
        assert "yadof/optimize/pymoo/backend.py" in wheel_names
        assert "yadof/optimize/qnehvi/__init__.py" in wheel_names
        assert "yadof/optimize/qnehvi/acquisition.py" in wheel_names
        assert "yadof/optimize/qnehvi/backend.py" in wheel_names
        assert "yadof/optimize/qnehvi/_botorch_backend.py" in wheel_names
        assert "yadof/optimize/posterior_assisted.py" in wheel_names
        assert "yadof/optimize/state.py" in wheel_names
        assert "yadof/optimize/strategy.py" in wheel_names
        assert "yadof/optimize/gpsaf.py" not in wheel_names
        assert "yadof/optimize/gpsaf_assistance.py" not in wheel_names
        assert "yadof/optimize/gpsaf_phases.py" not in wheel_names
        assert "yadof/optimize/gpsaf_pymoo.py" not in wheel_names
        assert "yadof/optimize/gpsaf_misc.py" not in wheel_names
        assert "yadof/optimize/qnehvi_acquisition.py" not in wheel_names
        assert "yadof/optimize/qnehvi_backend.py" not in wheel_names
        assert "yadof/optimize/_qlognehvi_backend.py" not in wheel_names
        assert "yadof/surrogate/conditional_inr/__init__.py" in wheel_names
        assert "yadof/surrogate/conditional_inr/runtime.py" in wheel_names
        assert "yadof/surrogate/conditional_inr/modeling.py" in wheel_names
        assert "yadof/surrogate/conditional_inr/checkpoints.py" in wheel_names
        assert "yadof/surrogate/conditional_inr/scheduler.py" in wheel_names
        assert "yadof/surrogate/conditional_inr/metadata.py" in wheel_names
        assert "yadof/surrogate/conditional_inr/types.py" in wheel_names
        assert "yadof/surrogate/conditional_inr/posterior_adapter.py" in wheel_names
        assert "yadof/surrogate/quality.py" in wheel_names
        assert "yadof/surrogate/exploitation.py" in wheel_names
        assert "yadof/surrogate/hierarchical_cae/__init__.py" in wheel_names
        assert "yadof/surrogate/hierarchical_cae/types.py" in wheel_names
        assert "yadof/surrogate/hierarchical_cae/schema.py" in wheel_names
        assert "yadof/surrogate/hierarchical_cae/networks.py" in wheel_names
        assert "yadof/surrogate/hierarchical_cae/objectives.py" in wheel_names
        assert "yadof/surrogate/hierarchical_cae/training.py" in wheel_names
        assert "yadof/surrogate/hierarchical_cae/inference.py" in wheel_names
        assert "yadof/surrogate/hierarchical_cae/runtime.py" in wheel_names
        assert "yadof/surrogate/hierarchical_cae/data_adapter.py" in wheel_names
        assert "yadof/surrogate/hierarchical_cae/state_repository.py" in wheel_names
        assert "yadof/surrogate/hierarchical_cae/projection.py" in wheel_names
        assert "yadof/surrogate/hierarchical_cae/checkpoints.py" in wheel_names
        assert "yadof/surrogate/hierarchical_cae/scheduler.py" in wheel_names
        assert "yadof/surrogate/hierarchical_cae/posterior_adapter.py" in wheel_names
        assert "yadof/surrogate/_shared/artifacts.py" in wheel_names
        assert "yadof/surrogate/_shared/training_events.py" in wheel_names
        assert "yadof/surrogate/_shared/finite_members.py" in wheel_names
        assert "yadof/surrogate/hierarchical_cae/modeling.py" not in wheel_names
        assert "yadof/surrogate/hierarchical_cae/metadata.py" not in wheel_names
        assert "yadof/surrogate/runtime.py" not in wheel_names
        assert "yadof/surrogate/scheduler.py" not in wheel_names
        assert "yadof/tools/view_cost.py" in wheel_names
        assert "yadof/tools/cost_viewer/__init__.py" in wheel_names
        assert "yadof/tools/cost_viewer/api.py" in wheel_names
        assert "yadof/tools/cost_viewer/analysis.py" in wheel_names
        assert "yadof/tools/cost_viewer/history.py" in wheel_names
        assert "yadof/tools/cost_viewer/plotting.py" in wheel_names
        assert "yadof/tools/cost_viewer/report.py" in wheel_names
        assert "yadof/tools/cost_viewer/style.py" in wheel_names
        assert "yadof/tools/cost_viewer/types.py" in wheel_names
        assert (
            "yadof/tools/cost_viewer/dev_doc/README.md"
        ) in wheel_names
        assert "yadof/tools/view_time.py" in wheel_names
        assert "yadof/tools/surrogate_viewer/__init__.py" in wheel_names
        assert "yadof/tools/surrogate_viewer/__main__.py" in wheel_names
        assert "yadof/tools/surrogate_viewer/app.py" in wheel_names
        assert "yadof/tools/surrogate_viewer/report.py" in wheel_names
        assert "yadof/tools/surrogate_viewer/backend/workspace.py" in wheel_names
        assert "yadof/tools/surrogate_viewer/ui/heatmap.py" in wheel_names
        assert (
            "yadof/tools/surrogate_viewer/dev_doc/README.md"
        ) in wheel_names
        assert "yadof/tools/view_error.py" not in wheel_names
        assert "yadof/tools/history.py" in wheel_names
        assert "yadof/tools/hfss/parameter_extraction.py" in wheel_names
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
            "yadof/_resources/templates/default/workspace/submit/calc_cost.py"
        ) in wheel_names
        assert (
            "yadof/_resources/templates/default/workspace/submit/optimization.py"
        ) in wheel_names
        assert (
            "yadof/_resources/templates/default/workspace/job_template/calc_cost.py"
        ) not in wheel_names
        assert "yadof/_resources/docs/dev_doc/README.md" in wheel_names
        assert "yadof/_resources/docs/user_doc/README.md" in wheel_names
        assert (
            "yadof/_resources/docs/dev_doc/obsolete/"
            "20260827_082610_conditional-inr-posterior-adapter.md"
        ) in wheel_names
        assert (
            "yadof/_resources/docs/dev_doc/change_records/"
            "20260827_152421_conditional-inr-posterior-and-qlognehvi-spike.md"
        ) in wheel_names
        assert (
            "yadof/_resources/docs/dev_doc/change_records/"
            "20260828_020622_qnehvi-posterior-assisted-framework.md"
        ) in wheel_names
        assert (
            "yadof/_resources/docs/dev_doc/obsolete/"
            "20260827_082611_qnehvi-acquisition-strategy.md"
        ) in wheel_names
        assert (
            "yadof/_resources/docs/dev_doc/toDo/"
            "20260828_121904_surrogate-qnehvi-remaining-work.md"
        ) in wheel_names
        assert (
            "yadof/_resources/docs/dev_doc/toDo/"
            "20260827_082611_qnehvi-acquisition-strategy.md"
        ) not in wheel_names
        assert (
            "yadof/_resources/docs/dev_doc/toDo/"
            "20260827_082610_conditional-inr-posterior-adapter.md"
        ) not in wheel_names
        for source in (REPOSITORY_ROOT / "user_doc").rglob("*"):
            if source.is_file():
                relative = source.relative_to(REPOSITORY_ROOT / "user_doc").as_posix()
                assert f"yadof/_resources/docs/user_doc/{relative}" in wheel_names
        entry_points_name = next(name for name in wheel_names if name.endswith(".dist-info/entry_points.txt"))
        metadata_name = next(name for name in wheel_names if name.endswith(".dist-info/METADATA"))
        assert "yadof = yadof.cli:main" in archive.read(entry_points_name).decode("utf-8")
        built_metadata = archive.read(metadata_name).decode("utf-8")
        assert "Name: yadof" in built_metadata
        assert f"Version: {yadof.__version__}" in built_metadata
        assert "Requires-Dist: numpy" in built_metadata
        assert "Requires-Dist: pymoo" in built_metadata
        assert "Provides-Extra: qnehvi" in built_metadata
        assert "botorch<0.19,>=0.18" in built_metadata
        assert "torch<3,>=2.4" in built_metadata
        assert "Provides-Extra: viewer" in built_metadata
        assert not any(name.startswith("project/") for name in wheel_names)
        assert "yadof/cli.py" not in wheel_names
        assert "yadof/workspace.py" not in wheel_names
        assert "yadof/workspace_init.py" not in wheel_names
        assert "yadof/workspace_check.py" not in wheel_names
        assert "yadof/workspace_manifest.py" not in wheel_names
        wheel_documentation_roots = {
            PurePosixPath(name).parts[3]
            for name in wheel_names
            if name.startswith("yadof/_resources/docs/")
            and len(PurePosixPath(name).parts) > 3
        }
        assert wheel_documentation_roots == {"dev_doc", "user_doc"}
        assert not any(name.lower().endswith(".aedt") for name in wheel_names)
        assert not any("__pycache__" in name or name.endswith((".pyc", ".pyo")) for name in wheel_names)

    with tarfile.open(sdist_path, "r:gz") as archive:
        sdist_names = set(archive.getnames())
        assert any(name.endswith("/src/yadof/cli/main.py") for name in sdist_names)
        assert any(name.endswith("/src/yadof/workspace/context.py") for name in sdist_names)
        assert any(
            name.endswith("/src/yadof/tools/surrogate_viewer/app.py")
            for name in sdist_names
        )
        assert any(
            name.endswith("/src/yadof/tools/surrogate_viewer/report.py")
            for name in sdist_names
        )
        assert any(
            name.endswith("/src/yadof/tools/surrogate_viewer/dev_doc/README.md")
            for name in sdist_names
        )
        assert any(
            name.endswith("/src/yadof/tools/cost_viewer/api.py")
            for name in sdist_names
        )
        assert any(
            name.endswith("/src/yadof/tools/cost_viewer/dev_doc/README.md")
            for name in sdist_names
        )
        assert any(name.endswith("/dev_doc/README.md") for name in sdist_names)
        assert any(name.endswith("/user_doc/README.md") for name in sdist_names)
        sdist_documentation_roots = {
            PurePosixPath(name).parts[1]
            for name in sdist_names
            if len(PurePosixPath(name).parts) > 2
            and PurePosixPath(name).parts[1].endswith("_doc")
        }
        assert sdist_documentation_roots == {"dev_doc", "user_doc"}
        assert any(name.endswith("/src/yadof/_resources/templates/default/README.md") for name in sdist_names)
        assert not any(
            len(PurePosixPath(name).parts) > 1 and PurePosixPath(name).parts[1] == "project"
            for name in sdist_names
        )
        assert not any(
            len(PurePosixPath(name).parts) > 1
            and PurePosixPath(name).parts[1] in {"examples", "tests"}
            for name in sdist_names
        )
        assert not any(name.lower().endswith(".aedt") for name in sdist_names)
        assert not any("__pycache__" in name or name.endswith((".pyc", ".pyo")) for name in sdist_names)

    _verify_clean_external_install(wheel_path)
    _verify_external_workspace_commands(wheel_path)
