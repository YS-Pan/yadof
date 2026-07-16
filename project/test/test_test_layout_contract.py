from __future__ import annotations

import ast
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
NON_SOURCE_TOP_LEVEL_DIRS = {"jobs", "test"}


def _contains_pytest_definitions(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
        or isinstance(node, ast.ClassDef) and node.name.startswith("Test")
        for node in ast.walk(tree)
    )


def test_maintained_pytest_modules_live_only_in_project_test():
    colocated_tests: list[str] = []

    for path in PROJECT_DIR.rglob("*.py"):
        relative = path.relative_to(PROJECT_DIR)
        if relative.parts[0] in NON_SOURCE_TOP_LEVEL_DIRS or "__pycache__" in relative.parts:
            continue
        if not (path.name.startswith("test_") or path.name.endswith("_test.py")):
            continue
        if _contains_pytest_definitions(path):
            colocated_tests.append(relative.as_posix())

    assert colocated_tests == [], (
        "maintained pytest modules must be moved to project/test/: "
        + ", ".join(sorted(colocated_tests))
    )
