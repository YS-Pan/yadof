"""Confirmed full-workspace reset and destructive-operation isolation."""

from pathlib import Path
import subprocess

import pytest

from yadof.recorded_data.campaign_lock import CampaignActiveError, CampaignLock
from yadof.tools import history
from yadof.workspace.init import init_workspace


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "study"
    init_workspace(root)
    return root


def test_full_clear_uses_configured_paths_and_preserves_task_and_other_workspace(workspace):
    other = workspace.parent / "other"
    init_workspace(other)
    sentinel = other / "retained.txt"
    sentinel.write_text("keep", encoding="utf-8")
    config = workspace / "config.py"
    config.write_text(config.read_text(encoding="utf-8") + (
        '\nJOBS_DIR = "results/jobs"\n'
        'RECORDED_DATA_DIR = "results/records"\n'
        'SURROGATE_CHECKPOINT_DIR = "results/models"\n'
    ), encoding="utf-8")
    original = config.read_bytes()
    for name in (
        "results/jobs/j1/rawData.npz", "results/records/metadata/training.json",
        "results/records/extra.txt", "results/models/inactive/model.npz",
        ".yadof/optimization/program-completion.json",
    ):
        path = workspace / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("old", encoding="utf-8")

    result = history.clear_history(workspace, confirm=True, all_recorded_data=True)

    assert result["jobs_entries_deleted"] == 1
    assert result["surrogate_checkpoints_deleted"]
    assert result["optimization_state_deleted"]
    assert not tuple((workspace / "results/jobs").iterdir())
    assert not tuple((workspace / "results/records").iterdir())
    assert not (workspace / "results/models").exists()
    assert not (workspace / ".yadof/optimization").exists()
    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert config.read_bytes() == original
    assert (workspace / "submit/optimization.py").is_file()
    assert (workspace / "job_template/workflow.py").is_file()
    assert (workspace / ".yadof/workspace.json").is_file()
    # Repeated reset also succeeds when no campaign artifacts remain.
    assert history.clear_history(workspace, confirm=True, all_recorded_data=True)["jobs_entries_deleted"] == 0


def test_full_clear_requires_confirmation(workspace):
    with pytest.raises(history.HistoryClearConfirmationRequired):
        history.clear_history(workspace, all_recorded_data=True)
    assert not (workspace / ".yadof/campaign.lock").exists()


def test_full_clear_rejects_external_target_before_any_deletion(workspace):
    outside = workspace.parent / "outside"
    outside.mkdir()
    sentinel = outside / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    jobs = workspace / "jobs"
    jobs.mkdir()
    (jobs / "keep.txt").write_text("keep", encoding="utf-8")
    config = workspace / "config.py"
    config.write_text(
        config.read_text(encoding="utf-8") + f"\nRECORDED_DATA_DIR = {str(outside)!r}\n",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="outside workspace"):
        history.clear_history(workspace, confirm=True, all_recorded_data=True)
    assert sentinel.is_file()
    assert (jobs / "keep.txt").is_file()


@pytest.mark.parametrize("fail", (False, True))
def test_clear_holds_campaign_lock_for_entire_mutation_and_releases_it(workspace, monkeypatch, fail):
    lock_path = workspace / ".yadof/campaign.lock"
    original_remove = history._remove_path
    calls = []

    def remove(path):
        competing = CampaignLock(lock_path)
        with pytest.raises(CampaignActiveError):
            competing.acquire()
        calls.append(path)
        if fail:
            raise OSError("deletion denied")
        return original_remove(path)

    monkeypatch.setattr(history, "_remove_path", remove)
    if fail:
        with pytest.raises(OSError, match="deletion denied"):
            history.clear_history(workspace, confirm=True, all_recorded_data=True)
    else:
        history.clear_history(workspace, confirm=True, all_recorded_data=True)
    assert calls
    lock = CampaignLock(lock_path)
    lock.acquire()
    lock.release()


def test_full_clear_removes_nested_junction_without_touching_external_data(workspace):
    outside = workspace.parent / "outside"
    outside.mkdir()
    sentinel = outside / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    jobs = workspace / "jobs"
    jobs.mkdir()
    link = jobs / "linked"
    # Use one shell only to create the Windows junction; deletion is package code.
    import os

    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode:
            pytest.skip("Cannot create junction")
    else:
        link.symlink_to(outside, target_is_directory=True)
    history.clear_history(workspace, confirm=True, all_recorded_data=True)
    assert not link.exists()
    assert sentinel.read_text(encoding="utf-8") == "keep"
