from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import tomllib
import zipfile

import pytest


AUTOMATION_ROOT = Path(__file__).resolve().parents[1]


def _selected_postprocessor(case_id: str):
    with (AUTOMATION_ROOT / "benchmark.toml").open("rb") as stream:
        config = tomllib.load(stream)
    baseline = AUTOMATION_ROOT / config["cases"][case_id]["baseline"]
    path = baseline / "workspace" / "postprocess.py"
    spec = importlib.util.spec_from_file_location(
        f"benchmark_postprocess_{case_id.replace('-', '_')}", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_saw_postprocessor_writes_multiple_prefixes_to_one_flat_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _selected_postprocessor("saw")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    output = tmp_path / "visualizations"
    output.mkdir()
    (output / "prior-result.txt").write_text("prior", encoding="utf-8")
    selection = {
        "source_job_name": "job",
        "normalized_variables": [0.5],
        "costs": [0.25],
        "average_cost": 0.25,
        "generation_index": 0,
        "population_index": 0,
    }
    monkeypatch.setattr(module, "_select_best", lambda _workspace: selection)
    monkeypatch.setattr(
        module,
        "_response",
        lambda _workspace, _job: (
            module.np.asarray([0.98e9, 1.02e9]),
            module.np.asarray([-2.0, -3.0]),
            module.np.asarray([-12.0, -15.0]),
        ),
    )

    for prefix in ("saw-cell-a__", "saw-cell-b__"):
        monkeypatch.setattr(
            module,
            "_parse_args",
            lambda prefix=prefix: argparse.Namespace(
                workspace=workspace,
                output_dir=output,
                output_prefix=prefix,
            ),
        )
        assert module.main() == 0

    assert not [path for path in output.iterdir() if path.is_dir()]
    assert {path.name for path in output.iterdir()} == {
        "prior-result.txt",
        *{
            f"{prefix}{name}"
            for prefix in ("saw-cell-a__", "saw-cell-b__")
            for name in (
                "saw_best_response.png",
                "saw_best_response.svg",
                "saw_best_response.csv",
                "postprocess_manifest.json",
            )
        },
    }


class _View:
    def __init__(self, data, **axes) -> None:
        self.data = data
        self._axes = axes

    def axis_coordinates(self, name: str):
        return self._axes[name]


def test_test_com_postprocessor_writes_prefixed_files_without_subdirectories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _selected_postprocessor("test-com")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    output = tmp_path / "visualizations"
    output.mkdir()
    (output / "prior-result.txt").write_text("prior", encoding="utf-8")
    selection = {
        "source_job_name": "job",
        "normalized_variables": [0.25, 0.75],
        "raw_variables": [1.0, 2.0],
        "costs": [0.2, 0.4],
        "average_cost": 0.3,
        "generation_index": 0,
        "population_index": 0,
    }
    views = {}
    for state in (1, 2, 3):
        views[f"s11_pinState{state}"] = _View(
            module.np.asarray([-8.0, -14.0]),
            Freq=module.np.asarray([2.4, 2.44]),
        )
        views[f"gain_lhcp_pinState{state}"] = _View(
            module.np.asarray([[[2.0, 3.0]]]),
            Freq=module.np.asarray([2.44]),
            Phi=module.np.asarray([90.0]),
            Theta=module.np.asarray([-30.0, 30.0]),
        )
        views[f"axial_ratio_pinState{state}"] = _View(
            module.np.asarray([[[1.0, 2.0]]]),
            Freq=module.np.asarray([2.44]),
            Phi=module.np.asarray([90.0]),
            Theta=module.np.asarray([-30.0, 30.0]),
        )
    monkeypatch.setattr(module, "_select_best", lambda _workspace: selection)
    monkeypatch.setattr(module, "_views", lambda _workspace, _job: views)
    monkeypatch.setattr(module, "_parameter_names", lambda _workspace: ["a", "b"])
    monkeypatch.setattr(
        module,
        "_parse_args",
        lambda: argparse.Namespace(
            workspace=workspace,
            output_dir=output,
            output_prefix="test-com-cell__",
        ),
    )

    assert module.main() == 0
    assert not [path for path in output.iterdir() if path.is_dir()]
    assert {path.name for path in output.iterdir()} == {
        "prior-result.txt",
        "test-com-cell__test_com_best_response.png",
        "test-com-cell__postprocess_manifest.json",
    }


def test_trebuchet_postprocessor_archives_scratch_and_keeps_output_flat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _selected_postprocessor("chrono")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    output = tmp_path / "visualizations"
    output.mkdir()
    (output / "prior-result.txt").write_text("prior", encoding="utf-8")
    prefix = "chrono-cell__attempt-0001__"
    selection = {
        "source_job_name": "job",
        "normalized_variables": [0.5],
        "raw_variables": [1.0],
        "costs": [0.2, 0.4],
        "average_cost": 0.3,
        "generation_index": 0,
        "population_index": 0,
        "recorded_at": "now",
    }
    monkeypatch.setattr(module, "_select_best", lambda _workspace: selection)

    def fake_stage(_workspace, scratch_root, _selection):
        snapshot = scratch_root / "selected_job"
        snapshot.mkdir()
        (snapshot / "evidence.txt").write_text("snapshot", encoding="utf-8")
        return snapshot

    def fake_run(command, *, cwd, check):
        assert cwd == str(workspace)
        assert check is True
        video = Path(command[command.index("--output") + 1])
        poster = Path(command[command.index("--poster") + 1])
        work_dir = Path(command[command.index("--work-dir") + 1])
        work_dir.mkdir(parents=True)
        video.write_bytes(b"video")
        poster.write_bytes(b"poster")
        (work_dir / "continuation_diagnostics.json").write_text(
            "{}\n", encoding="utf-8"
        )
        (work_dir / "trebuchet_animation_trajectory.npz").write_bytes(b"trajectory")

    monkeypatch.setattr(module, "_stage_snapshot", fake_stage)
    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(
        module,
        "_parse_args",
        lambda: argparse.Namespace(
            workspace=workspace,
            output_dir=output,
            output_prefix=prefix,
            fps=30,
            dpi=120,
            continuation_timeout=180.0,
        ),
    )

    assert module.main() == 0
    assert not [path for path in output.iterdir() if path.is_dir()]
    expected = {
        "prior-result.txt",
        f"{prefix}trebuchet_best.mp4",
        f"{prefix}trebuchet_best_poster.png",
        f"{prefix}trebuchet_selected_job.zip",
        f"{prefix}trebuchet_continuation_diagnostics.json",
        f"{prefix}trebuchet_animation_trajectory.npz",
        f"{prefix}postprocess_manifest.json",
    }
    assert {path.name for path in output.iterdir()} == expected
    with zipfile.ZipFile(output / f"{prefix}trebuchet_selected_job.zip") as archive:
        assert "selected_job/evidence.txt" in archive.namelist()
    manifest = json.loads(
        (output / f"{prefix}postprocess_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["output_prefix"] == prefix
    for key in (
        "snapshot_archive",
        "video",
        "poster",
        "continuation_diagnostics",
        "animation_trajectory",
    ):
        assert Path(manifest[key]).parent == output
