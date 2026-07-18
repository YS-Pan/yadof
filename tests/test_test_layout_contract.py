from __future__ import annotations

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_maintained_pytest_modules_live_only_in_standard_tests_directory():
    maintained = sorted(
        path
        for path in REPOSITORY_ROOT.rglob("test_*.py")
        if "tests" not in path.relative_to(REPOSITORY_ROOT).parts[:1]
        and "_resources" not in path.relative_to(REPOSITORY_ROOT).parts
        and not any(
            part in {".git", "build", "dist", "temp", "dev_doc"}
            for part in path.relative_to(REPOSITORY_ROOT).parts
        )
    )
    assert maintained == []


def test_removed_project_namespace_does_not_exist():
    assert not (REPOSITORY_ROOT / "project").exists()
