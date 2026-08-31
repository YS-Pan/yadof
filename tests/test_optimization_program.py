from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from yadof.cli import main as cli_main
from yadof.config import load_config
from yadof.optimize import run_generations
from yadof.optimize.program import (
    ProgramGenerationScope,
    execute_frozen_program,
    freeze_workspace_program,
    inspect_workspace_optimization,
)
from yadof.optimize.state import read_program_completion_state
from yadof.recorded_data import api as recorded_api
from yadof.recorded_data.session import CampaignSession, RecordingError
from yadof.workspace.check import check_workspace
from yadof.workspace.init import init_workspace


FAST_EVALUATION = '''\
from __future__ import annotations
import json
import numpy as np

def evaluate_rawdata(parameters, context):
    del context
    value = float(parameters["input_value"])
    response = np.asarray(value * value, dtype=float)
    return {
        "response.npz": {
            "values": response,
            "metadata": json.dumps({
                "schema_version": 1,
                "rawdata_name": "response",
                "shape": [],
            }),
        }
    }
'''


OPTIMIZATION_PROGRAM_EXAMPLES = (
    "overlapped_surrogate",
    "posterior_assisted_fallback",
    "real_only",
    "sequential_surrogate",
    "split_cost_surrogate_data",
)


def test_retained_source_programs_have_no_legacy_loop_or_callback_edge() -> None:
    repository = Path(__file__).resolve().parents[1]
    relative_paths = (
        "src/yadof/_resources/templates/default/workspace/submit/optimization.py",
        "examples/hfss-newchoke/submit/optimization.py",
        "yadof-benchmark/baselines/chrono/trebuchet/workspace/submit/optimization.py",
        "yadof-benchmark/baselines/ngspice/saw-ladder/workspace/submit/optimization.py",
        "yadof-benchmark/baselines/test-com/synthetic-antenna/workspace/submit/optimization.py",
        *(
            f"examples/optimization-programs/{stem}.py"
            for stem in OPTIMIZATION_PROGRAM_EXAMPLES
        ),
    )
    for relative_path in relative_paths:
        source_path = repository / relative_path
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(source_path))
        function_names = {
            node.name for node in tree.body if isinstance(node, ast.FunctionDef)
        }
        assignments = {
            target.id
            for node in tree.body
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        assert "YADOF_OPTIMIZATION_PROGRAM" in assignments
        assert "optimization_program" in function_names
        assert "build_optimization" not in source
        assert "run_generation" not in source
        assert "after_jobs_submitted" not in source

    signature = inspect.signature(ProgramGenerationScope.prepare_evaluation)
    assert "after_jobs_submitted" not in signature.parameters
    surrogate_api = (
        repository / "src/yadof/surrogate/api.py"
    ).read_text(encoding="utf-8")
    assert "training_data_from_session(" not in surrogate_api
    import yadof.optimize as optimize_api

    for removed in (
        "OptimizationStrategy",
        "OptimizationDefinition",
        "GPSAFStrategy",
        "RealSearchStrategy",
        "load_workspace_strategy",
        "real_search",
    ):
        assert not hasattr(optimize_api, removed)
    assert "gpsaf" not in optimize_api.__all__
    assert not callable(getattr(optimize_api, "gpsaf", None))
    assert "posterior_assisted" not in optimize_api.__all__
    assert not callable(getattr(optimize_api, "posterior_assisted", None))


def _real_program(*, close_handle: bool = True, identity: str = "real-pilot") -> str:
    close_line = "                handle.close()\n" if close_handle else ""
    return f'''\
from yadof.evaluate_manager import start_evaluation
from yadof.optimize import full_real_search, pymoo_ga

YADOF_OPTIMIZATION_PROGRAM = {{
    "api": "yadof.optimize.program/v1",
    "entry": "optimization_program",
    "helpers": (),
    "identity": {{"program": {identity!r}, "version": 1}},
    "capabilities": ("real-evaluation",),
}}

def optimization_program(context):
    search = pymoo_ga()
    with context.run_scope() as run:
        for generation_index in run.generations():
            with run.generation(generation_index) as step:
                selected = full_real_search(
                    step.context,
                    search,
                    origin_prefix="program-real",
                )
                handle = start_evaluation(step.prepare_evaluation(selected.population))
                evaluation = handle.wait()
{close_line}                diagnostics = dict(selected.state.diagnostics)
                diagnostics.update(dict(selected.diagnostics))
                step.commit(step.result(
                    population=selected.population,
                    costs=evaluation.costs,
                    source=selected.source,
                    diagnostics=diagnostics,
                ))
'''


def _workspace(root: Path, *, program: str | None = None, mode: str = "fast") -> Path:
    init_workspace(root)
    (root / "config.py").write_text(
        f'EVALUATION_MODE = {mode!r}\n'
        "OPTIMIZE_POPULATION_SIZE = 2\n"
        "OPTIMIZE_RANDOM_SEED = 101\n"
        "OPTIMIZE_SMOKE_TEST_ENABLED = False\n"
        "FAST_RESOURCE_AUTODETECT_ENABLED = False\n"
        "FAST_EVALUATION_MAX_WORKERS = 2\n",
        encoding="utf-8",
        newline="\n",
    )
    (root / "job_template/evaluation.py").write_text(
        FAST_EVALUATION,
        encoding="utf-8",
        newline="\n",
    )
    if program is not None:
        (root / "submit/optimization.py").write_text(
            program,
            encoding="utf-8",
            newline="\n",
        )
    return root


def _files(root: Path) -> tuple[str, ...]:
    return tuple(
        sorted(
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file()
        )
    )


def test_optimization_program_examples_are_paired_indexed_and_static(
    tmp_path: Path,
) -> None:
    repository = Path(__file__).resolve().parents[1]
    examples = repository / "examples/optimization-programs"
    python_stems = tuple(sorted(path.stem for path in examples.glob("*.py")))
    markdown_stems = tuple(sorted(path.stem for path in examples.glob("*.md")))
    assert python_stems == OPTIMIZATION_PROGRAM_EXAMPLES
    assert markdown_stems == OPTIMIZATION_PROGRAM_EXAMPLES

    index = (repository / "user_doc/optimization_program_examples.md").read_text(
        encoding="utf-8"
    )
    for stem in OPTIMIZATION_PROGRAM_EXAMPLES:
        guide = (examples / f"{stem}.md").read_text(encoding="utf-8")
        for heading in (
            "## Workspace dependencies",
            "## Data flow",
            "## Concurrency and resources",
            "## Adoption",
        ):
            assert heading in guide
        assert f"../examples/optimization-programs/{stem}.py" in index
        root = _workspace(
            tmp_path / stem,
            program=(examples / f"{stem}.py").read_text(encoding="utf-8"),
        )
        inspection = inspect_workspace_optimization(root)
        assert inspection.kind == "explicit-program"
        assert inspection.program is not None


def test_real_only_source_example_runs_one_fast_generation(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[1]
    program = (
        repository / "examples/optimization-programs/real_only.py"
    ).read_text(encoding="utf-8")
    root = _workspace(tmp_path / "real-example", program=program)

    results = run_generations(root, 1, start_generation=0)

    assert len(results) == 1
    assert results[0].generation_index == 0
    assert len(results[0].population) == 2
    assert results[0].surrogate_used is False
    assert results[0].diagnostics["program_api"] == "yadof.optimize.program/v1"


def test_check_statically_validates_program_without_execution_or_runtime_writes(
    tmp_path: Path,
) -> None:
    root = _workspace(tmp_path / "static", mode="local")
    sentinel = root / "program-ran.txt"
    program = f'''\
from pathlib import Path

YADOF_OPTIMIZATION_PROGRAM = {{
    "api": "yadof.optimize.program/v1",
    "entry": "optimization_program",
    "helpers": (),
    "identity": {{"program": "static-check", "version": 1}},
    "capabilities": ("real-evaluation",),
}}

def optimization_program(context):
    Path({str(sentinel)!r}).write_text("ran", encoding="utf-8")
'''
    (root / "submit/optimization.py").write_text(program, encoding="utf-8")
    before = _files(root)

    report = check_workspace(root)

    assert report.ok, report.format()
    assert "program code was not imported or executed" in report.format()
    assert _files(root) == before
    assert not sentinel.exists()
    assert not (root / ".yadof/optimization").exists()


def test_static_declaration_and_helper_validation_fail_closed(tmp_path: Path) -> None:
    root = _workspace(tmp_path / "invalid", program=_real_program())
    sentinel = root / "top-level-ran.txt"
    (root / "submit/optimization.py").write_text(
        "from pathlib import Path\n"
        f"SIDE_EFFECT = Path({str(sentinel)!r}).write_text('ran')\n"
        + _real_program(),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="top-level assignments must contain literal"):
        inspect_workspace_optimization(root)
    assert not sentinel.exists()

    (root / "submit/optimization.py").write_text(
        _real_program().replace(
            '"helpers": (),',
            '"helpers": ("../escape.py",),',
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="relative .py path"):
        inspect_workspace_optimization(root)


def test_real_program_runs_commits_metadata_and_resumes_strictly(
    tmp_path: Path,
) -> None:
    root = _workspace(tmp_path / "real", program=_real_program())

    first = run_generations(root, 1, start_generation=0)
    completion = read_program_completion_state(root)
    metadata = recorded_api.list_optimization_metadata(root)

    assert len(first) == 1
    assert first[0].generation_index == 0
    assert len(first[0].population) == 2
    assert all(len(row) == 1 for row in first[0].costs)
    assert first[0].diagnostics["program_api"] == "yadof.optimize.program/v1"
    assert completion is not None
    assert completion.generation_index == 0
    assert completion.task_snapshot_id == first[0].diagnostics["task_snapshot_id"]
    assert metadata[-1]["generation_index"] == 0
    assert metadata[-1]["strategy_signature"] == first[0].diagnostics[
        "strategy_signature"
    ]

    with pytest.raises(RuntimeError, match="next incomplete generation 1"):
        run_generations(root, 1, start_generation=0)

    optimization = root / "submit/optimization.py"
    optimization.write_text(
        optimization.read_text(encoding="utf-8") + "\n# provenance-only edit\n",
        encoding="utf-8",
    )
    second = run_generations(root, 1, start_generation=1)
    next_completion = read_program_completion_state(root)

    assert second[0].generation_index == 1
    assert second[0].diagnostics["strategy_signature"] == first[0].diagnostics[
        "strategy_signature"
    ]
    assert second[0].diagnostics["program_source_fingerprint"] != first[0].diagnostics[
        "program_source_fingerprint"
    ]
    assert next_completion is not None and next_completion.generation_index == 1

    (root / ".yadof/optimization/program-completion.json").write_text(
        "{}\n",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="invalid explicit program completion pointer"):
        run_generations(root, 1, start_generation=2)


def test_cli_freezes_explicit_program_before_optional_smoke(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from yadof.cli import run as run_command

    root = _workspace(tmp_path / "cli-freeze", program=_real_program())
    optimization = root / "submit/optimization.py"
    captured: dict[str, object] = {}

    def smoke(*_args, **_kwargs):
        optimization.write_text(
            _real_program(identity="edited-during-smoke"),
            encoding="utf-8",
        )
        return ((0.1,),)

    def fake_generations(*_args, **kwargs):
        frozen = kwargs["_frozen_program"]
        assert frozen is not None
        captured["source_root"] = frozen.source_root
        captured["source"] = (
            frozen.source_root / "optimization.py"
        ).read_text(encoding="utf-8")
        return (
            SimpleNamespace(
                generation_index=0,
                source="frozen-cli",
                surrogate_used=False,
                history_count=0,
                costs=((0.1,),),
            ),
        )

    monkeypatch.setattr(run_command, "run_smoke_test", smoke)
    monkeypatch.setattr(run_command, "run_generations", fake_generations)

    assert cli_main(
        [
            "run",
            "--workspace",
            str(root),
            "--generations",
            "1",
            "--smoke-test",
        ]
    ) == 0
    capsys.readouterr()

    assert '"program": \'real-pilot\'' in str(captured["source"])
    assert "edited-during-smoke" not in str(captured["source"])
    assert not Path(captured["source_root"]).exists()


FREEZE_PROGRAM = '''\
from pathlib import Path
from yadof.evaluate_manager import start_evaluation
from yadof.optimize import full_real_search, pymoo_ga
from optimization_helpers import source_label

YADOF_OPTIMIZATION_PROGRAM = {
    "api": "yadof.optimize.program/v1",
    "entry": "optimization_program",
    "helpers": ("optimization_helpers.py",),
    "identity": {"program": "freeze-reload", "version": 1},
    "capabilities": ("real-evaluation", "program-freeze", "task-reload"),
}

def optimization_program(context):
    search = pymoo_ga()
    with context.run_scope() as run:
        for generation_index in run.generations():
            with run.generation(generation_index) as step:
                selected = full_real_search(step.context, search, origin_prefix="freeze")
                handle = start_evaluation(step.prepare_evaluation(selected.population))
                try:
                    evaluation = handle.wait()
                finally:
                    handle.close()
                step.commit(step.result(
                    population=selected.population,
                    costs=evaluation.costs,
                    source=selected.source,
                    diagnostics={"helper_label": source_label()},
                ))
            if generation_index == context.start_generation:
                (context.workspace.submit_dir / "optimization_helpers.py").write_text(
                    "def source_label():\\n    return 'live-edited'\\n",
                    encoding="utf-8",
                )
                (context.workspace.submit_dir / "calc_cost.py").write_text(
                    "def calculate_cost(sample_rawdata, raw_variables=None):\\n"
                    "    return (2.0,)\\n"
                    "def get_objective_names():\\n"
                    "    return ('constant',)\\n",
                    encoding="utf-8",
                )
'''


def test_program_helpers_freeze_once_while_cost_policy_reloads_per_generation(
    tmp_path: Path,
) -> None:
    root = _workspace(tmp_path / "freeze", program=FREEZE_PROGRAM)
    (root / "submit/optimization_helpers.py").write_text(
        "def source_label():\n    return 'frozen'\n",
        encoding="utf-8",
    )
    (root / "submit/calc_cost.py").write_text(
        "def calculate_cost(sample_rawdata, raw_variables=None):\n"
        "    return (1.0,)\n"
        "def get_objective_names():\n"
        "    return ('constant',)\n",
        encoding="utf-8",
    )

    results = run_generations(root, 2, start_generation=0)

    assert [result.diagnostics["helper_label"] for result in results] == [
        "frozen",
        "frozen",
    ]
    assert results[0].costs == ((1.0,), (1.0,))
    assert results[1].costs == ((2.0,), (2.0,))
    assert results[0].diagnostics["program_source_fingerprint"] == results[1].diagnostics[
        "program_source_fingerprint"
    ]
    assert results[0].diagnostics["optimization_fingerprint"] == results[1].diagnostics[
        "optimization_fingerprint"
    ]
    assert results[0].diagnostics["interpretation_fingerprint"] != results[1].diagnostics[
        "interpretation_fingerprint"
    ]
    assert "live-edited" in (
        root / "submit/optimization_helpers.py"
    ).read_text(encoding="utf-8")


def test_program_sources_are_classified_out_of_generation_task_copy(
    tmp_path: Path,
) -> None:
    root = _workspace(tmp_path / "classified", program=FREEZE_PROGRAM)
    (root / "submit/optimization_helpers.py").write_text(
        "def source_label():\n    return 'frozen'\n",
        encoding="utf-8",
    )
    frozen = freeze_workspace_program(root)
    assert frozen is not None
    session = CampaignSession(load_config(root))
    try:
        snapshot = session.begin_generation(
            load_config(root),
            program_source_hashes=frozen.source_hashes,
            program_fingerprint=frozen.source_fingerprint,
        )
        assert not (snapshot.submit_directory / "optimization.py").exists()
        assert not (snapshot.submit_directory / "optimization_helpers.py").exists()
        assert (snapshot.submit_directory / "calc_cost.py").is_file()
        assert snapshot.config.workspace.requires_optimization_source is False
        assert "submit/optimization.py" in snapshot.source_hashes
        assert "submit/optimization_helpers.py" in snapshot.source_hashes
        assert snapshot.optimization_fingerprint == frozen.source_fingerprint
    finally:
        session.close()
        frozen.close()


def test_open_evaluation_and_metadata_failure_do_not_publish_completion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    open_root = _workspace(
        tmp_path / "open-handle",
        program=_real_program(close_handle=False, identity="open-handle"),
    )
    with pytest.raises(RuntimeError, match="evaluation handles remain open"):
        run_generations(open_root, 1, start_generation=0)
    assert read_program_completion_state(open_root) is None
    assert recorded_api.list_optimization_metadata(open_root) == ()
    CampaignSession(load_config(open_root)).close()

    metadata_root = _workspace(
        tmp_path / "metadata-failure",
        program=_real_program(identity="metadata-failure"),
    )

    def fail_metadata(*_args, **_kwargs):
        raise OSError("injected metadata failure")

    monkeypatch.setattr(recorded_api, "record_optimization_metadata", fail_metadata)
    with pytest.raises(OSError, match="injected metadata failure"):
        run_generations(metadata_root, 1, start_generation=0)
    assert read_program_completion_state(metadata_root) is None
    CampaignSession(load_config(metadata_root)).close()


def test_recorder_failure_leaves_generation_incomplete_and_releases_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from yadof.recorded_data import session as session_module

    root = _workspace(
        tmp_path / "recording-failure",
        program=_real_program(identity="recording-failure"),
    )

    def fail_publish(*_args, **_kwargs):
        raise OSError("injected program recorder failure")

    monkeypatch.setattr(session_module, "publish_segment", fail_publish)

    with pytest.raises(RecordingError, match="campaign evidence writer failed"):
        run_generations(root, 1, start_generation=0)

    assert read_program_completion_state(root) is None
    assert recorded_api.list_optimization_metadata(root) == ()
    CampaignSession(load_config(root)).close()


def test_keyboard_interrupt_closes_program_snapshot_session_and_lock(
    tmp_path: Path,
) -> None:
    program = '''\
YADOF_OPTIMIZATION_PROGRAM = {
    "api": "yadof.optimize.program/v1",
    "entry": "optimization_program",
    "helpers": (),
    "identity": {"program": "interrupt", "version": 1},
    "capabilities": ("cleanup",),
}

def optimization_program(context):
    with context.run_scope() as run:
        for generation_index in run.generations():
            with run.generation(generation_index):
                raise KeyboardInterrupt("injected interrupt")
'''
    root = _workspace(tmp_path / "interrupt", program=program)
    frozen = freeze_workspace_program(root)
    assert frozen is not None
    source_root = frozen.source_root

    with pytest.raises(KeyboardInterrupt, match="injected interrupt"):
        execute_frozen_program(frozen, 1)

    assert not source_root.exists()
    assert read_program_completion_state(root) is None
    CampaignSession(load_config(root)).close()


def test_undeclared_program_sibling_import_fails_closed(tmp_path: Path) -> None:
    program = _real_program(identity="undeclared-import").replace(
        "from yadof.evaluate_manager import start_evaluation\n",
        "from yadof.evaluate_manager import start_evaluation\n"
        "from undeclared_helper import marker\n",
    )
    root = _workspace(tmp_path / "undeclared", program=program)
    (root / "submit/undeclared_helper.py").write_text(
        "marker = 'live-only'\n",
        encoding="utf-8",
    )

    with pytest.raises(ImportError, match="undeclared_helper"):
        run_generations(root, 1, start_generation=0)

    assert read_program_completion_state(root) is None


def test_program_evaluation_order_is_user_owned_and_backend_invariant(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import yadof.evaluate_manager as evaluate_manager
    from yadof.optimize import program as program_module

    events: list[tuple[str, str]] = []

    def fake_prepare(_workspace, population, *, mode, **_kwargs):
        selected = str(mode)
        events.append(("prepare", selected))
        return SimpleNamespace(population=tuple(population), mode=selected)

    class FakeHandle:
        def __init__(self, batch) -> None:
            self.batch = batch

        def wait(self):
            events.append(("wait", self.batch.mode))
            return SimpleNamespace(
                costs=tuple((float(index),) for index, _ in enumerate(self.batch.population))
            )

        def close(self) -> None:
            events.append(("close", self.batch.mode))

    def fake_start(batch):
        events.append(("start", batch.mode))
        return FakeHandle(batch)

    monkeypatch.setattr(program_module.evaluate_api, "prepare_evaluation", fake_prepare)
    monkeypatch.setattr(evaluate_manager, "start_evaluation", fake_start)

    for mode in ("fast", "local", "distributed"):
        root = _workspace(
            tmp_path / mode,
            program=_real_program(identity=f"order-{mode}"),
            mode=mode,
        )
        events.clear()
        result = run_generations(root, 1, start_generation=0)
        assert len(result) == 1
        assert events == [
            ("prepare", mode),
            ("start", mode),
            ("wait", mode),
            ("close", mode),
        ]


def test_program_can_choose_explicit_evaluation_overlap_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import yadof.evaluate_manager as evaluate_manager
    from yadof.optimize import program as program_module

    program = '''\
from yadof.evaluate_manager import start_evaluation
from yadof.optimize import full_real_search, pymoo_ga

YADOF_OPTIMIZATION_PROGRAM = {
    "api": "yadof.optimize.program/v1",
    "entry": "optimization_program",
    "helpers": (),
    "identity": {"program": "explicit-overlap", "version": 1},
    "capabilities": ("real-evaluation", "explicit-overlap"),
}

def optimization_program(context):
    search = pymoo_ga()
    with context.run_scope() as run:
        for generation_index in run.generations():
            with run.generation(generation_index) as step:
                selected = full_real_search(step.context, search, origin_prefix="overlap")
                first = start_evaluation(step.prepare_evaluation(selected.population))
                second = start_evaluation(step.prepare_evaluation(selected.population))
                second_result = second.wait()
                second.close()
                first.wait()
                first.close()
                step.commit(step.result(
                    population=selected.population,
                    costs=second_result.costs,
                    source=selected.source,
                ))
'''
    root = _workspace(tmp_path / "overlap", program=program, mode="local")
    events: list[str] = []
    counter = iter(("first", "second"))

    def fake_prepare(_workspace, population, **_kwargs):
        name = next(counter)
        events.append(f"prepare:{name}")
        return SimpleNamespace(name=name, population=tuple(population))

    class FakeHandle:
        def __init__(self, batch) -> None:
            self.batch = batch

        def wait(self):
            events.append(f"wait:{self.batch.name}")
            return SimpleNamespace(
                costs=tuple((0.25,) for _ in self.batch.population)
            )

        def close(self) -> None:
            events.append(f"close:{self.batch.name}")

    def fake_start(batch):
        events.append(f"start:{batch.name}")
        return FakeHandle(batch)

    monkeypatch.setattr(program_module.evaluate_api, "prepare_evaluation", fake_prepare)
    monkeypatch.setattr(evaluate_manager, "start_evaluation", fake_start)

    results = run_generations(root, 1, start_generation=0)

    assert len(results) == 1
    assert events == [
        "prepare:first",
        "start:first",
        "prepare:second",
        "start:second",
        "wait:second",
        "close:second",
        "wait:first",
        "close:first",
    ]


PCA_PROGRAM = '''\
from yadof.evaluate_manager import start_evaluation
from yadof.optimize import pymoo_ga
from yadof.surrogate import pca_svd
from optimization_helpers import select_population, transformed_training_data

YADOF_OPTIMIZATION_PROGRAM = {
    "api": "yadof.optimize.program/v1",
    "entry": "optimization_program",
    "helpers": ("optimization_helpers.py",),
    "identity": {
        "program": "pca-svd-gpsaf-pilot",
        "version": 1,
        "alpha": 2,
        "beta": 1,
        "gamma": 0.5,
        "exploration_fraction": 0.25,
    },
    "capabilities": ("real-evaluation", "pca-svd", "gpsaf"),
}

def optimization_program(context):
    search = pymoo_ga()
    surrogate = pca_svd(rank=2, device="cpu", seed=20260828)
    with context.run_scope() as run:
        for generation_index in run.generations():
            with run.generation(generation_index) as step:
                selected, selection_diagnostics = select_population(
                    step,
                    search,
                    surrogate,
                    alpha=2,
                    beta=1,
                    gamma=0.5,
                    exploration_fraction=0.25,
                )
                handle = start_evaluation(step.prepare_evaluation(selected.population))
                try:
                    evaluation = handle.wait()
                finally:
                    handle.close()
                training = transformed_training_data(step, surrogate)
                fitted = surrogate.fit(
                    step.context.config.workspace,
                    training,
                    generation_index=generation_index,
                    session=step.context.session,
                    snapshot=step.context.snapshot,
                )
                diagnostics = dict(selection_diagnostics)
                diagnostics.update({
                    "training_content_digest": training.content_digest,
                    "training_provenance_digest": training.provenance_digest,
                    "training_transform_id": training.transform_id,
                    "training_row_ids": training.row_ids,
                    "fitted_state_signature": fitted.state_signature,
                    "surrogate_gamma": 0.5,
                })
                step.commit(step.result(
                    population=selected.population,
                    costs=evaluation.costs,
                    source=selected.source,
                    surrogate_used=bool(diagnostics["surrogate_selected"]),
                    diagnostics=diagnostics,
                ))
'''


PCA_HELPER = '''\
import numpy as np

from yadof.optimize import (
    advance_search,
    bind_surrogate_prediction,
    combine_candidate_pools,
    combine_predicted_cost_rows,
    compose_real_population,
    continue_search_from,
    fork_search_state,
    full_real_search,
    prepare_search,
    search_candidates,
    select_candidates,
)

def transformed_training_data(step, surrogate):
    dataset = step.evidence_dataset()
    table = step.cost_table()
    successful = tuple(
        row.row_id
        for row in table.rows
        if str(row.status.value) == "succeeded"
    )
    order = np.arange(len(successful), dtype=int)[::-1].copy()
    row_ids = tuple(successful[int(index)] for index in order)
    return surrogate.training_data(
        dataset,
        table,
        row_ids=row_ids,
        transform_id="numpy-reverse-v1",
    )

def _predicted(surrogate, context, pool, training):
    return bind_surrogate_prediction(
        pool,
        surrogate.predict_for_selection(context, pool.population, training),
    )

def select_population(
    step,
    search,
    surrogate,
    *,
    alpha,
    beta,
    gamma,
    exploration_fraction,
):
    context = step.context
    diagnostics = {
        "surrogate_alpha": int(alpha),
        "surrogate_beta": int(beta),
        "surrogate_gamma": float(gamma),
        "exploration_fraction": float(exploration_fraction),
        "surrogate_selected": False,
    }
    training = None
    if context.history:
        training = transformed_training_data(step, surrogate)
    if training is None or not surrogate.has_trained_state(context, training):
        selected = full_real_search(context, search, origin_prefix="program-gpsaf")
        diagnostics.update(dict(selected.state.diagnostics))
        diagnostics.update(dict(selected.diagnostics))
        diagnostics["selection_mode"] = "full-real-warmup"
        return selected, diagnostics

    state = prepare_search(
        context,
        search,
        population_size=context.population_size,
        algorithm_seed=context.random_seed,
        random_seed=context.random_seed + context.generation_index * 1009 + 17,
        history_policy="survivor",
    )
    exploration_count = min(
        context.population_size,
        max(1, int(round(context.population_size * float(exploration_fraction)))),
    )
    target = context.population_size - exploration_count
    exploration = search_candidates(
        fork_search_state(state),
        exploration_count,
        origin="program-gpsaf-exploration",
    )
    current = continue_search_from(state, exploration.state)
    alpha_pools = []
    alpha_predictions = []
    for index in range(int(alpha)):
        pool = search_candidates(current, target, origin=f"program-gpsaf-alpha-{index}")
        current = pool.state
        alpha_pools.append(pool)
        alpha_predictions.append(_predicted(surrogate, context, pool, training))
    combined_alpha = combine_candidate_pools(current, tuple(alpha_pools))
    combined_alpha_prediction = combine_predicted_cost_rows(
        combined_alpha,
        tuple(alpha_predictions),
        source="program-gpsaf-alpha-prediction",
    )
    anchors = select_candidates(
        current,
        combined_alpha,
        combined_alpha_prediction,
        target,
        source="program-gpsaf-alpha-selection",
    )

    beta_state = fork_search_state(anchors.state)
    beta_pools = []
    beta_predictions = []
    for index in range(int(beta)):
        pool = search_candidates(beta_state, target, origin=f"program-gpsaf-beta-{index}")
        prediction = _predicted(surrogate, context, pool, training)
        beta_pools.append(pool)
        beta_predictions.append(prediction)
        beta_state = advance_search(pool.state, pool, prediction)
    combined_beta = combine_candidate_pools(beta_state, (anchors, *beta_pools))
    combined_beta_prediction = combine_predicted_cost_rows(
        combined_beta,
        (combined_alpha_prediction, *beta_predictions),
        source="program-gpsaf-beta-prediction",
    )
    selected_surrogate = select_candidates(
        beta_state,
        combined_beta,
        combined_beta_prediction,
        target,
        source="program-gpsaf-beta-selection",
    )
    selected = compose_real_population(
        selected_surrogate.state,
        (selected_surrogate, exploration),
        size=context.population_size,
        source="program-gpsaf-selection",
        refill_origin="program-gpsaf-refill",
    )
    diagnostics.update(dict(selected.state.diagnostics))
    diagnostics.update({
        "selection_mode": "explicit-pca-svd-gpsaf",
        "surrogate_selected": True,
        "alpha_batches": len(alpha_pools),
        "beta_batches": len(beta_pools),
        "exploration_count": len(exploration.candidates),
        "selected_candidate_ids": tuple(row.candidate_id for row in selected.candidates),
    })
    return selected, diagnostics
'''


def test_pca_svd_gpsaf_program_owns_data_selection_evaluation_and_fit(
    tmp_path: Path,
) -> None:
    root = _workspace(tmp_path / "pca", program=PCA_PROGRAM)
    (root / "config.py").write_text(
        (root / "config.py").read_text(encoding="utf-8").replace(
            "OPTIMIZE_POPULATION_SIZE = 2",
            "OPTIMIZE_POPULATION_SIZE = 4",
        ),
        encoding="utf-8",
    )
    (root / "submit/optimization_helpers.py").write_text(
        PCA_HELPER,
        encoding="utf-8",
        newline="\n",
    )

    results = run_generations(root, 2, start_generation=0)

    assert len(results) == 2
    assert results[0].diagnostics["selection_mode"] == "full-real-warmup"
    assert results[0].surrogate_used is False
    assert results[1].diagnostics["selection_mode"] == "explicit-pca-svd-gpsaf"
    assert results[1].surrogate_used is True
    assert results[1].diagnostics["surrogate_gamma"] == 0.5
    assert results[1].diagnostics["alpha_batches"] == 2
    assert results[1].diagnostics["beta_batches"] == 1
    assert results[1].diagnostics["exploration_count"] == 1
    assert results[1].diagnostics["training_transform_id"] == "numpy-reverse-v1"
    assert len(results[1].diagnostics["training_row_ids"]) == 8
    assert all(len(result.population) == 4 for result in results)
    assert all(len(result.costs) == 4 for result in results)
    assert tuple(root.glob(".yadof/surrogate/checkpoints/runs/*/components/pca-svd/*.json"))
    completion = read_program_completion_state(root)
    assert completion is not None and completion.generation_index == 1
    surrogate_metadata = recorded_api.list_surrogate_metadata(root)
    assert any(row.get("record_type") == "surrogate_training" for row in surrogate_metadata)
