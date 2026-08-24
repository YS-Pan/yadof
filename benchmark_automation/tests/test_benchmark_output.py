from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import benchmark
import benchmark_core as core


def _plan() -> dict:
    return {
        "schema_version": 1,
        "suite": "performance",
        "purpose": "performance",
        "fail_fast": False,
        "selection": {
            "cases": ["case-a"],
            "arms": ["real", "surrogate"],
            "seeds": [1],
        },
        "cell_count": 2,
        "cells": [
            {
                "cell_id": "case-a__real__seed-1",
                "kind": "measured",
                "case": "case-a",
                "planned_attempted_evaluations": 8,
                "planned_commands": [["python", "-m", "yadof", "run", "--many", "arguments"]],
            },
            {
                "cell_id": "case-a__surrogate__seed-1",
                "kind": "measured",
                "case": "case-a",
                "planned_attempted_evaluations": 8,
                "planned_commands": [["python", "-m", "yadof", "run", "--many", "arguments"]],
            },
        ],
        "estimates": {
            "evaluation_wall_lower_bound_sec": 12.5,
            "record_storage_mib": 4.0,
            "scope_note": "fixture",
        },
        "prerequisites": {"case-a": {"kind": "cuda"}},
    }


def test_plan_summary_omits_expanded_cells_and_commands() -> None:
    summary = core.summarize_plan(_plan())
    encoded = json.dumps(summary)
    assert summary["view"] == "plan-summary"
    assert summary["cells"]["planned_attempted_evaluations"] == 16
    assert summary["cells"]["by_case"]["case-a"]["measured_cells"] == 2
    assert isinstance(summary["cells"], dict)
    assert "python" not in encoded
    assert "--many" not in encoded
    assert len(encoded) < 2500


def test_preflight_summary_bounds_subprocess_diagnostics() -> None:
    result = {
        "schema_version": 1,
        "suite": "performance",
        "ok": False,
        "checked_utc": "2026-08-23T00:00:00Z",
        "package": {
            "version": "0.4.0",
            "origin": "site-packages/yadof/__init__.py",
            "python": "python",
            "python_version": "3.13.0\nlong build details",
        },
        "plan": _plan(),
        "checks": [
            {"name": "baseline:case-a", "ok": True, "details": {"large": "x" * 10000}},
            {
                "name": "yadof-check:case-a",
                "ok": False,
                "details": {
                    "returncode": 2,
                    "stdout": "x" * 10000,
                    "stderr": "prefix\n" + "diagnostic " * 1000,
                },
            },
        ],
    }
    summary = core.summarize_preflight(result)
    encoded = json.dumps(summary)
    assert summary["checks"]["failed"] == 1
    assert summary["checks"]["items"][1]["details"]["returncode"] == 2
    assert "diagnostic_tail" in summary["checks"]["items"][1]
    assert "x" * 1000 not in encoded
    assert len(encoded) < 5000


def test_stream_pipe_can_log_without_forwarding_to_console(tmp_path: Path) -> None:
    output = tmp_path / "stdout.log"
    core._stream_pipe(io.BytesIO("first\n第二行\n".encode()), output, None, "[out] ")
    assert output.read_text(encoding="utf-8") == "first\n第二行\n"


def test_interactive_progress_redraws_below_lifecycle_text() -> None:
    class TtyBuffer(io.StringIO):
        def isatty(self) -> bool:
            return True

    terminal = TtyBuffer()
    progress = core.CellProgress(2, stream=terminal, width=10)
    progress.start()
    progress.write_above("[cell] first started\n")
    progress.set_current("first")
    progress.advance("completed")
    progress.finish()
    output = terminal.getvalue()
    assert "\r" in output
    assert "\x1b" not in output
    assert "[cell] first started\n" in output
    assert output.endswith(
        "[benchmark] [#####-----] 1/2 cells | completed=1 failed=0 skipped=0\n"
    )


def test_execute_logged_preserves_large_child_output_without_streaming(
    tmp_path: Path, capsys
) -> None:
    attempt_root = tmp_path / "attempt"
    attempt_root.mkdir()
    attempt = {"commands": []}
    payload = "large-child-output-" * 1000
    metadata = core._execute_logged(
        [sys.executable, "-c", f"print({payload!r})"],
        cwd=tmp_path,
        attempt_root=attempt_root,
        attempt=attempt,
        timeout_sec=30,
        label="fixture",
    )
    captured = capsys.readouterr()
    assert metadata["returncode"] == 0
    assert payload not in captured.out
    assert payload not in captured.err
    assert "commands" in captured.err
    assert str(tmp_path) not in captured.err
    assert Path(metadata["stdout"]).read_text(encoding="utf-8").strip() == payload


def test_execute_logged_keeps_imports_from_writing_bytecode(tmp_path: Path) -> None:
    (tmp_path / "declared_input.py").write_text("VALUE = 1\n", encoding="utf-8")
    attempt_root = tmp_path / "attempt"
    attempt_root.mkdir()
    metadata = core._execute_logged(
        [sys.executable, "-c", "import declared_input"],
        cwd=tmp_path,
        attempt_root=attempt_root,
        attempt={"commands": []},
        timeout_sec=30,
        label="bytecode-fixture",
    )
    assert metadata["returncode"] == 0
    assert not (tmp_path / "__pycache__").exists()


def test_report_summary_keeps_decision_evidence_without_fingerprints() -> None:
    report = {
        "schema_version": 1,
        "run_id": "fixture",
        "suite": "performance",
        "purpose": "performance",
        "generated_utc": "2026-08-23T00:00:00Z",
        "tool_gaps": {"metric": "not available"},
        "validity_by_cell": {
            "case-a__real__seed-1": {
                "execution_status": "completed",
                "exclusion_reason": None,
                "public_api_issues": [],
                "validity": {
                    "planned_real_evaluations": 8,
                    "attempted_real_evaluations": 8,
                    "completed_candidate_evaluations": 8,
                    "failed_candidate_evaluations": 0,
                    "timeout_candidate_evaluations": 0,
                    "all_infinite_generation_count": 0,
                },
            }
        },
        "performance": {
            "interpretation_policy": "descriptive only",
            "arm_roles": {"real": "real", "surrogate": "surrogate"},
            "arm_labels": {"real": "NSGA-III", "surrogate": "GPSAF + conditional-INR"},
            "included_pairs": [
                {
                    "case": "case-a",
                    "seed": 1,
                    "attempted_real_evaluations": {"real": 8, "surrogate": 8},
                    "initial_population_fingerprints": {
                        "real": "secretly-long-fingerprint",
                        "surrogate": "secretly-long-fingerprint",
                    },
                    "raw": {
                        "final_cumulative_hypervolume": {"real": 0.2, "surrogate": 0.3},
                        "evaluator_elapsed_sec_sum": {"real": 5.0, "surrogate": 4.0},
                        "finite_objective_rows": {"real": 8, "surrogate": 8},
                        "invalid_objective_rows": {"real": 0, "surrogate": 0},
                        "surrogate_training_duration_sec": 1.0,
                    },
                    "differences": {
                        "surrogate_minus_real": {
                            "final_cumulative_hypervolume": 0.1,
                            "evaluator_elapsed_sec_sum": -1.0,
                        }
                    },
                }
            ],
            "excluded_pairs_retained": [],
            "descriptive_aggregate_by_case": {"case-a": {"metric": {"count": 1}}},
        },
    }
    summary = core.summarize_report(report)
    encoded = json.dumps(summary)
    pair = summary["performance"]["pairs"][0]
    assert pair["metrics"]["final_cumulative_hypervolume"]["surrogate_minus_real"] == 0.1
    assert summary["validity"]["evaluation_totals"]["attempted"] == 8
    assert summary["performance"]["arm_labels"]["real"] == "NSGA-III"
    table = core.format_hypervolume_table(report)
    assert table is not None
    assert "| Case | Seed | NSGA-III | GPSAF + conditional-INR |" in table
    assert "| case-a | 1 | 0.2 | 0.3 |" in table
    assert "secretly-long-fingerprint" not in encoded
    assert len(encoded) < 7000


def test_cli_defaults_to_bounded_output_and_quiet_children() -> None:
    parser = benchmark._parser()
    plan = parser.parse_args(["plan", "--suite", "performance"])
    run = parser.parse_args(["run", "--suite", "performance-pilot"])
    report = parser.parse_args(["report", "--run-id", "fixture"])
    assert plan.full_json is False
    assert run.stream_output is False
    assert report.full_json is False
    assert parser.parse_args(["plan", "--suite", "performance", "--full-json"]).full_json
    assert parser.parse_args(
        ["run", "--suite", "performance-pilot", "--stream-output"]
    ).stream_output
    runs_dir = Path("temp") / "benchmark" / "task-id"
    parsed = parser.parse_args(
        ["--runs-dir", str(runs_dir), "inspect", "--run-id", "fixture"]
    )
    assert parsed.runs_dir == runs_dir


def test_interactive_run_pause_waits_for_enter(monkeypatch) -> None:
    class TtyInput(io.StringIO):
        def isatty(self) -> bool:
            return True

    stdin = TtyInput("\n")
    stderr = io.StringIO()
    monkeypatch.setattr(benchmark.sys, "stdin", stdin)
    monkeypatch.setattr(benchmark.sys, "stderr", stderr)
    benchmark._pause_after_run()
    assert stdin.tell() == 1
    assert "Press Enter" in stderr.getvalue()


def test_run_summary_propagates_runs_dir_to_next_command(tmp_path: Path) -> None:
    run_root = tmp_path / "agent outputs" / "fixture"
    state = {
        "schema_version": 1,
        "status": "completed",
        "updated_utc": "2026-08-23T00:00:00Z",
        "cells": {},
    }
    summary = core.summarize_run_state(run_root, "fixture", state)
    assert summary["runs_dir"] == str(run_root.parent.resolve())
    assert summary["run_root"] == str(run_root.resolve())
    assert summary["next_command"] == [
        "--runs-dir",
        str(run_root.parent.resolve()),
        "collect",
        "--run-id",
        "fixture",
    ]
