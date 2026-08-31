"""Static workspace-program declaration, frozen loading, and lifecycle scopes."""

from __future__ import annotations

import ast
from contextlib import contextmanager
from dataclasses import dataclass, replace
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from types import MappingProxyType
from typing import Iterator, Mapping, Sequence

from ..config import LoadedConfig, load_config
from ..evaluate_manager import api as evaluate_api
from ..job_template import api as job_template_api
from ..recorded_data.session import CampaignSession
from ..task_loader import load_task_module
from ..workspace import WorkspaceContext, resolve_workspace
from .runner import new_run_id, next_optimization_index, now_text, record_generation_metadata
from .state import (
    activate_strategy_state,
    read_program_completion_state,
    write_program_completion_state,
)
from .strategy import (
    GenerationContext,
    OptimizationResult,
    history_records,
    resolve_problem_info,
    semantic_strategy_signature,
)


PROGRAM_DECLARATION_NAME = "YADOF_OPTIMIZATION_PROGRAM"
PROGRAM_API = "yadof.optimize.program/v1"
_PROGRAM_KEYS = frozenset(
    {"api", "entry", "helpers", "identity", "capabilities"}
)
_PRIVATE_TOKEN = object()


@dataclass(frozen=True, slots=True)
class OptimizationProgramSpec:
    api: str
    entry: str
    helpers: tuple[str, ...]
    identity: Mapping[str, object]
    capabilities: tuple[str, ...]
    source_path: Path


@dataclass(frozen=True, slots=True)
class OptimizationSourceInspection:
    kind: str
    source_path: Path
    program: OptimizationProgramSpec | None = None


@dataclass(frozen=True, slots=True)
class FrozenOptimizationProgram:
    workspace: WorkspaceContext
    spec: OptimizationProgramSpec
    source_root: Path
    source_hashes: Mapping[str, str]
    source_fingerprint: str

    def close(self) -> None:
        shutil.rmtree(self.source_root, ignore_errors=True)


def inspect_workspace_optimization(
    workspace: WorkspaceContext | str | os.PathLike[str],
) -> OptimizationSourceInspection:
    """Statically inspect optimization.py without importing or executing it."""

    context = resolve_workspace(workspace)
    source_path = context.submit_dir / "optimization.py"
    if source_path.is_symlink() or not source_path.is_file():
        raise ValueError(f"optimization source must be a regular file: {source_path}")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(source_path))
    declaration = _declaration_node(tree)
    if declaration is None:
        if not _top_level_function(tree, "build_optimization"):
            raise TypeError(
                f"{source_path} must define build_optimization() or literal "
                f"{PROGRAM_DECLARATION_NAME}"
            )
        return OptimizationSourceInspection("legacy-strategy", source_path)

    raw = ast.literal_eval(declaration)
    if not isinstance(raw, dict):
        raise TypeError(f"{PROGRAM_DECLARATION_NAME} must be a literal mapping")
    if any(not isinstance(key, str) for key in raw):
        raise TypeError(f"{PROGRAM_DECLARATION_NAME} keys must be strings")
    keys = set(raw)
    if keys != _PROGRAM_KEYS:
        missing = sorted(_PROGRAM_KEYS - keys)
        unexpected = sorted(keys - _PROGRAM_KEYS)
        raise ValueError(
            f"{PROGRAM_DECLARATION_NAME} keys must be exactly "
            f"{sorted(_PROGRAM_KEYS)!r}; missing={missing!r}, "
            f"unexpected={unexpected!r}"
        )
    api = str(raw["api"]).strip()
    if api != PROGRAM_API:
        raise ValueError(
            f"{PROGRAM_DECLARATION_NAME} api must be {PROGRAM_API!r}"
        )
    entry = str(raw["entry"]).strip()
    if not entry.isidentifier() or not _top_level_function(tree, entry):
        raise TypeError(
            f"{source_path} must define synchronous entry function {entry!r}"
        )
    _validate_entry_signature(tree, entry, source_path)
    helpers = _helper_names(raw["helpers"])
    identity = _json_mapping(raw["identity"], label="program identity")
    capabilities = _capabilities(raw["capabilities"])
    _validate_static_module(tree, source_path, declaration_name=PROGRAM_DECLARATION_NAME)
    for helper in helpers:
        helper_path = _helper_path(context.submit_dir, helper)
        helper_tree = ast.parse(
            helper_path.read_text(encoding="utf-8"),
            filename=str(helper_path),
        )
        _validate_static_module(helper_tree, helper_path, declaration_name=None)
    return OptimizationSourceInspection(
        "explicit-program",
        source_path,
        OptimizationProgramSpec(
            api=api,
            entry=entry,
            helpers=helpers,
            identity=identity,
            capabilities=capabilities,
            source_path=source_path,
        ),
    )


def freeze_workspace_program(
    workspace: WorkspaceContext | str | os.PathLike[str],
) -> FrozenOptimizationProgram | None:
    """Freeze declared program sources once; return None for the legacy path."""

    context = resolve_workspace(workspace)
    inspection = inspect_workspace_optimization(context)
    if inspection.kind != "explicit-program":
        return None
    spec = inspection.program
    assert spec is not None
    sources = ("optimization.py", *spec.helpers)
    source_hashes: dict[str, str] = {}
    source_root = Path(tempfile.mkdtemp(prefix="yadof-program-snapshot-"))
    try:
        for relative in sources:
            source = (
                spec.source_path
                if relative == "optimization.py"
                else _helper_path(context.submit_dir, relative)
            )
            destination = source_root.joinpath(*PurePosixPath(relative).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            source_hashes[f"submit/{relative}"] = hashlib.sha256(
                destination.read_bytes()
            ).hexdigest()
        frozen_context = replace(
            context,
            submit_dir=source_root,
            requires_optimization_source=True,
        )
        frozen_inspection = inspect_workspace_optimization(frozen_context)
        frozen_spec = frozen_inspection.program
        if (
            frozen_inspection.kind != "explicit-program"
            or frozen_spec is None
            or _spec_semantics(frozen_spec) != _spec_semantics(spec)
        ):
            raise RuntimeError(
                "optimization program changed while its run snapshot was being "
                "frozen; retry from a stable generation boundary"
            )
        fingerprint = _hash_json(
            {
                "api": spec.api,
                "sources": source_hashes,
            }
        )
        return FrozenOptimizationProgram(
            workspace=context,
            spec=spec,
            source_root=source_root,
            source_hashes=MappingProxyType(dict(source_hashes)),
            source_fingerprint=fingerprint,
        )
    except BaseException:
        shutil.rmtree(source_root, ignore_errors=True)
        raise


@contextmanager
def frozen_program_entry(
    frozen: FrozenOptimizationProgram,
) -> Iterator[object]:
    """Load one entry from only the frozen source root for the complete run."""

    module = load_task_module(
        frozen.workspace,
        "optimization",
        source_root=frozen.source_root,
    )
    entry = getattr(module, frozen.spec.entry, None)
    if not callable(entry) or getattr(entry, "__module__", None) != module.__name__:
        raise TypeError(
            f"frozen optimization program must define {frozen.spec.entry}()"
        )
    yield entry


def execute_frozen_program(
    frozen: FrozenOptimizationProgram,
    generations: int,
    *,
    start_generation: int = 0,
    population_size: int | None = None,
    variable_count: int | None = None,
    random_seed: int | None = None,
    run_id: str | None = None,
    optimization_index: int | None = None,
    config_overrides: Mapping[str, object] | None = None,
    fail_on_all_infinite: bool = False,
) -> tuple[OptimizationResult, ...]:
    """Execute one frozen explicit program and always release its source snapshot."""

    try:
        initial_config = load_config(
            frozen.workspace,
            overrides=config_overrides,
        )
        problem = resolve_problem_info(
            initial_config.workspace,
            variable_count,
            (),
        )
        parameter_names = tuple(
            job_template_api.get_parameter_names(initial_config.workspace)
        )
        identity = _program_identity(frozen.spec)
        signature = semantic_strategy_signature(
            identity,
            parameter_names=parameter_names,
            objective_names=problem.objective_names,
        )
        selected_run_id = new_run_id() if run_id is None else str(run_id)
        selected_optimization_index = (
            next_optimization_index(initial_config.workspace)
            if optimization_index is None
            else int(optimization_index)
        )
        context = OptimizationProgramContext(
            initial_config=initial_config,
            frozen=frozen,
            program_identity=identity,
            program_signature=signature,
            parameter_names=parameter_names,
            objective_names=tuple(problem.objective_names),
            generations=max(0, int(generations)),
            start_generation=int(start_generation),
            population_size=population_size,
            variable_count=variable_count,
            random_seed=random_seed,
            run_id=selected_run_id,
            optimization_index=selected_optimization_index,
            config_overrides=config_overrides,
            fail_on_all_infinite=fail_on_all_infinite,
            _token=_PRIVATE_TOKEN,
        )
        with frozen_program_entry(frozen) as entry:
            returned = entry(context)
        if returned is not None:
            raise TypeError("optimization_program(context) must return None")
        return context._completed_results()
    finally:
        frozen.close()


class OptimizationProgramContext:
    """Framework-created owner from which a workspace opens exactly one run scope."""

    def __init__(
        self,
        *,
        initial_config: LoadedConfig,
        frozen: FrozenOptimizationProgram,
        program_identity: Mapping[str, object],
        program_signature: str,
        parameter_names: tuple[str, ...],
        objective_names: tuple[str, ...],
        generations: int,
        start_generation: int,
        population_size: int | None,
        variable_count: int | None,
        random_seed: int | None,
        run_id: str,
        optimization_index: int,
        config_overrides: Mapping[str, object] | None,
        fail_on_all_infinite: bool,
        _token: object,
    ) -> None:
        if _token is not _PRIVATE_TOKEN:
            raise TypeError("OptimizationProgramContext is framework-created")
        if int(start_generation) < 0:
            raise ValueError("start_generation must be non-negative")
        self.workspace = initial_config.workspace
        self.program_signature = str(program_signature)
        self.program_identity = MappingProxyType(dict(program_identity))
        self.program_source_fingerprint = frozen.source_fingerprint
        self.program_capabilities = frozen.spec.capabilities
        self.max_generations = int(generations)
        self.start_generation = int(start_generation)
        self._initial_config = initial_config
        self._frozen = frozen
        self._parameter_names = parameter_names
        self._objective_names = objective_names
        self._population_size = population_size
        self._variable_count = variable_count
        self._random_seed = random_seed
        self._run_id = run_id
        self._optimization_index = optimization_index
        self._config_overrides = (
            None if config_overrides is None else dict(config_overrides)
        )
        self._fail_on_all_infinite = bool(fail_on_all_infinite)
        self._scope: OptimizationRunScope | None = None

    def run_scope(self) -> OptimizationRunScope:
        if self._scope is not None:
            raise RuntimeError("optimization program can create only one run scope")
        self._scope = OptimizationRunScope(self, _token=_PRIVATE_TOKEN)
        return self._scope

    def _completed_results(self) -> tuple[OptimizationResult, ...]:
        if self._scope is None or not self._scope.closed:
            raise RuntimeError(
                "optimization program must enter and close context.run_scope()"
            )
        if self._scope.failed:
            raise RuntimeError("optimization program swallowed a generation failure")
        return tuple(self._scope.results)


class OptimizationRunScope:
    """Campaign-session owner and bounded generation-range coordinator."""

    def __init__(self, context: OptimizationProgramContext, *, _token: object) -> None:
        if _token is not _PRIVATE_TOKEN:
            raise TypeError("OptimizationRunScope is framework-created")
        self.context = context
        self.results: list[OptimizationResult] = []
        self.closed = False
        self.failed = False
        self._entered = False
        self._iterated = False
        self._active: ProgramGenerationScope | None = None
        self._next_generation = context.start_generation
        self._session: CampaignSession | None = None

    def __enter__(self) -> OptimizationRunScope:
        if self._entered or self.closed:
            raise RuntimeError("optimization run scope cannot be re-entered")
        completion = read_program_completion_state(self.context.workspace)
        if (
            completion is not None
            and completion.program_signature == self.context.program_signature
        ):
            expected = completion.generation_index + 1
            if self.context.start_generation != expected:
                raise RuntimeError(
                    "explicit program resume must start at the next incomplete "
                    f"generation {expected}, got {self.context.start_generation}"
                )
        activate_strategy_state(
            self.context.workspace,
            strategy_signature=self.context.program_signature,
            strategy_identity=self.context.program_identity,
            optimization_source_hash=self.context.program_source_fingerprint,
        )
        self._session = CampaignSession(self.context._initial_config)
        self._entered = True
        return self

    def generations(self) -> range:
        self._require_entered()
        if self._iterated:
            raise RuntimeError("run.generations() may be iterated only once")
        self._iterated = True
        return range(
            self.context.start_generation,
            self.context.start_generation + self.context.max_generations,
        )

    def generation(self, generation_index: int) -> ProgramGenerationScope:
        self._require_entered()
        if self.failed:
            raise RuntimeError("optimization run cannot continue after a failed generation")
        selected = int(generation_index)
        end = self.context.start_generation + self.context.max_generations
        if selected != self._next_generation or selected >= end:
            raise ValueError(
                "program generation must be the next bounded index "
                f"{self._next_generation}, got {selected}"
            )
        if self._active is not None:
            raise RuntimeError("only one program generation scope may be active")
        self._active = ProgramGenerationScope(
            self,
            selected,
            _token=_PRIVATE_TOKEN,
        )
        return self._active

    def _generation_finished(
        self,
        scope: ProgramGenerationScope,
        result: OptimizationResult | None,
        *,
        failed: bool,
    ) -> None:
        if self._active is not scope:
            raise RuntimeError("program generation scope ownership mismatch")
        self._active = None
        if failed:
            self.failed = True
            return
        assert result is not None
        self.results.append(result)
        self._next_generation += 1

    def __exit__(self, exc_type, exc, traceback) -> bool:
        close_error: BaseException | None = None
        try:
            if self._active is not None:
                self.failed = True
            if self._session is not None:
                final_counters = self._session.close()
                if self.results:
                    diagnostics = dict(self.results[-1].diagnostics)
                    diagnostics["recording"] = final_counters
                    self.results[-1] = replace(
                        self.results[-1],
                        diagnostics=diagnostics,
                    )
        except BaseException as cleanup_error:
            close_error = cleanup_error
        finally:
            self.closed = True
            self._entered = False
        if close_error is not None:
            if exc is None:
                raise close_error
            add_note = getattr(exc, "add_note", None)
            if callable(add_note):
                add_note(f"optimization run cleanup also failed: {close_error}")
        return False

    @property
    def session(self) -> CampaignSession:
        self._require_entered()
        assert self._session is not None
        return self._session

    def _require_entered(self) -> None:
        if not self._entered or self.closed:
            raise RuntimeError("optimization run scope is not active")


class ProgramGenerationScope:
    """One generation's task snapshot, explicit operations, and commit boundary."""

    def __init__(
        self,
        run: OptimizationRunScope,
        generation_index: int,
        *,
        _token: object,
    ) -> None:
        if _token is not _PRIVATE_TOKEN:
            raise TypeError("ProgramGenerationScope is framework-created")
        self.run = run
        self.generation_index = int(generation_index)
        self._entered = False
        self._committed: OptimizationResult | None = None
        self._context: GenerationContext | None = None
        self._started_at = ""
        self._jobs_before: tuple[str, ...] = ()

    def __enter__(self) -> ProgramGenerationScope:
        if self._entered:
            raise RuntimeError("program generation scope cannot be re-entered")
        try:
            live_config = load_config(
                self.run.context.workspace,
                overrides=self.run.context._config_overrides,
            )
            snapshot = self.run.session.begin_generation(
                live_config,
                program_source_hashes=self.run.context._frozen.source_hashes,
                program_fingerprint=self.run.context.program_source_fingerprint,
            )
            if snapshot.parameter_names != self.run.context._parameter_names:
                raise ValueError(
                    "program parameter names changed during one frozen run"
                )
            if snapshot.objective_names != self.run.context._objective_names:
                raise ValueError(
                    "program objective names changed during one frozen run"
                )
            history = history_records(
                snapshot.config.workspace,
                session=self.run.session,
                snapshot=snapshot,
            )
            problem = resolve_problem_info(
                snapshot.config.workspace,
                self.run.context._variable_count,
                history,
            )
            selected_population_size = (
                int(snapshot.config.OPTIMIZE_POPULATION_SIZE)
                if self.run.context._population_size is None
                else int(self.run.context._population_size)
            )
            if selected_population_size <= 0:
                raise ValueError("population_size must be positive")
            selected_seed = (
                int(snapshot.config.OPTIMIZE_RANDOM_SEED)
                if self.run.context._random_seed is None
                else int(self.run.context._random_seed)
            )
            self._context = GenerationContext(
                config=snapshot.config,
                generation_index=self.generation_index,
                population_size=selected_population_size,
                random_seed=selected_seed,
                run_id=self.run.context._run_id,
                optimization_index=self.run.context._optimization_index,
                session=self.run.session,
                snapshot=snapshot,
                history=history,
                problem=problem,
                strategy_signature=self.run.context.program_signature,
                strategy_identity=self.run.context.program_identity,
            )
            self._started_at = now_text()
            self._jobs_before = _session_job_names(self.run.session)
            self._entered = True
            return self
        except BaseException:
            self.run._generation_finished(self, None, failed=True)
            raise

    @property
    def context(self) -> GenerationContext:
        self._require_entered()
        assert self._context is not None
        return self._context

    def evidence_dataset(self):
        self._require_entered()
        return self.run.session.evidence_dataset()

    def cost_table(self):
        self._require_entered()
        return self.run.session.cost_table(self.context.snapshot)

    def prepare_evaluation(
        self,
        population: Sequence[Sequence[float]],
    ):
        self._require_entered()
        return evaluate_api.prepare_evaluation(
            self.context.config.workspace,
            population,
            mode=str(self.context.config.EVALUATION_MODE),
            run_id=self.context.run_id,
            optimization_index=self.context.optimization_index,
            generation_index=self.context.generation_index,
            _campaign_session=self.context.session,
            _task_snapshot=self.context.snapshot,
        )

    def result(
        self,
        *,
        population: Sequence[Sequence[float]],
        costs: Sequence[Sequence[float]],
        source: str,
        surrogate_used: bool = False,
        diagnostics: Mapping[str, object] | None = None,
    ) -> OptimizationResult:
        self._require_entered()
        return OptimizationResult(
            generation_index=self.generation_index,
            population=tuple(tuple(float(value) for value in row) for row in population),
            costs=tuple(tuple(float(value) for value in row) for row in costs),
            history_count=len(self.context.history),
            source=str(source),
            surrogate_used=bool(surrogate_used),
            diagnostics={} if diagnostics is None else dict(diagnostics),
        )

    def commit(self, result: OptimizationResult) -> None:
        self._require_entered()
        if self._committed is not None:
            raise RuntimeError("program generation result may be committed only once")
        _validate_result(result, self.context)
        self._committed = result

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if exc is not None:
            self.run._generation_finished(self, None, failed=True)
            return False
        if self._committed is None:
            self.run._generation_finished(self, None, failed=True)
            raise RuntimeError(
                f"program generation {self.generation_index} exited without step.commit()"
            )
        open_handles = dict(self.run.session.generation_handle_counts())
        try:
            self.run.session.finish_generation()
            if int(open_handles.get("cancel", 0)):
                raise RuntimeError(
                    "program generation cannot commit while evaluation handles remain "
                    "open; wait and close each handle explicitly"
                )
            self.run.session.flush_boundary()
            result = _program_diagnostics(
                self._committed,
                self.run.context,
                self.context,
                self.run.session,
            )
            ended_at = now_text()
            jobs_after = _session_job_names(self.run.session)
            record_generation_metadata(
                self.context.config.workspace,
                run_id=self.context.run_id,
                optimization_index=self.context.optimization_index,
                result=result,
                started_at=self._started_at,
                ended_at=ended_at,
                jobs_before=self._jobs_before,
                jobs_after=jobs_after,
                session=self.run.session,
                snapshot=self.context.snapshot,
                strict=True,
            )
            write_program_completion_state(
                self.run.context.workspace,
                program_signature=self.run.context.program_signature,
                generation_index=self.generation_index,
                program_source_fingerprint=(
                    self.run.context.program_source_fingerprint
                ),
                task_snapshot_id=self.context.snapshot.task_snapshot_id,
            )
            self.run._generation_finished(self, result, failed=False)
            if self.run.context._fail_on_all_infinite and _all_infinite(result.costs):
                from .api import AllInfiniteGenerationError

                raise AllInfiniteGenerationError(result)
        except BaseException:
            if self.run._active is self:
                self.run._generation_finished(self, None, failed=True)
            raise
        finally:
            self._entered = False
        return False

    def _require_entered(self) -> None:
        if not self._entered or self._context is None:
            raise RuntimeError("program generation scope is not active")


def _program_diagnostics(
    result: OptimizationResult,
    program: OptimizationProgramContext,
    generation: GenerationContext,
    session: CampaignSession,
) -> OptimizationResult:
    diagnostics = dict(result.diagnostics)
    diagnostics.update(
        {
            "strategy_signature": program.program_signature,
            "strategy_identity": dict(program.program_identity),
            "program_api": PROGRAM_API,
            "program_entry": program._frozen.spec.entry,
            "program_capabilities": program.program_capabilities,
            "program_source_fingerprint": program.program_source_fingerprint,
            "recording": session.counters(),
            "history_reinterpretation_sec": session.last_reinterpretation_sec,
            "interpretation_fingerprint": (
                generation.snapshot.interpretation_fingerprint
            ),
            "evaluation_fingerprint": generation.snapshot.evaluation_fingerprint,
            "optimization_fingerprint": (
                generation.snapshot.optimization_fingerprint
            ),
            "task_snapshot_id": generation.snapshot.task_snapshot_id,
        }
    )
    return replace(result, diagnostics=diagnostics)


def _validate_result(result: OptimizationResult, context: GenerationContext) -> None:
    if not isinstance(result, OptimizationResult):
        raise TypeError("step.commit() requires OptimizationResult")
    if int(result.generation_index) != int(context.generation_index):
        raise ValueError("committed result generation does not match the active step")
    population = tuple(result.population)
    costs = tuple(result.costs)
    if len(population) != context.population_size or len(costs) != len(population):
        raise ValueError(
            "committed population/cost count must equal the configured population size"
        )
    for row in population:
        if len(row) != context.problem.variable_count or any(
            not math.isfinite(float(value))
            or float(value) < -1.0e-9
            or float(value) > 1.0 + 1.0e-9
            for value in row
        ):
            raise ValueError("committed normalized population has invalid shape/value")
    for row in costs:
        if len(row) != context.problem.objective_count or any(
            math.isnan(float(value)) for value in row
        ):
            raise ValueError("committed costs have invalid objective shape/value")
    source = str(result.source).strip()
    if not source:
        raise ValueError("committed result source must be non-empty")


def _declaration_node(tree: ast.Module) -> ast.AST | None:
    values: list[ast.AST] = []
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name)
            and target.id == PROGRAM_DECLARATION_NAME
            for target in statement.targets
        ):
            values.append(statement.value)
        elif (
            isinstance(statement, ast.AnnAssign)
            and isinstance(statement.target, ast.Name)
            and statement.target.id == PROGRAM_DECLARATION_NAME
            and statement.value is not None
        ):
            values.append(statement.value)
    if len(values) > 1:
        raise ValueError(f"{PROGRAM_DECLARATION_NAME} must be assigned exactly once")
    return None if not values else values[0]


def _top_level_function(tree: ast.Module, name: str) -> bool:
    return sum(
        isinstance(statement, ast.FunctionDef) and statement.name == name
        for statement in tree.body
    ) == 1


def _validate_entry_signature(tree: ast.Module, name: str, source_path: Path) -> None:
    entry = next(
        statement
        for statement in tree.body
        if isinstance(statement, ast.FunctionDef) and statement.name == name
    )
    positional = (*entry.args.posonlyargs, *entry.args.args)
    if (
        len(positional) != 1
        or entry.args.defaults
        or entry.args.vararg is not None
        or entry.args.kwonlyargs
        or entry.args.kwarg is not None
    ):
        raise TypeError(
            f"{source_path} entry {name!r} must have exact signature "
            f"{name}(context)"
        )


def _validate_static_module(
    tree: ast.Module,
    source_path: Path,
    *,
    declaration_name: str | None,
) -> None:
    for index, statement in enumerate(tree.body):
        if (
            index == 0
            and isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        ):
            continue
        if isinstance(statement, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(statement, (ast.FunctionDef, ast.ClassDef)):
            _validate_definition_expressions(statement, source_path)
            continue
        if isinstance(statement, ast.Assign):
            _literal_value(statement.value, source_path)
            continue
        if isinstance(statement, ast.AnnAssign) and statement.value is not None:
            _literal_value(statement.value, source_path)
            continue
        raise ValueError(
            f"{source_path} has executable top-level {type(statement).__name__}; "
            "put all program execution inside the declared entry"
        )
    if declaration_name is not None and _declaration_node(tree) is None:
        raise ValueError(f"{source_path} is missing {declaration_name}")


def _validate_definition_expressions(
    statement: ast.FunctionDef | ast.ClassDef,
    source_path: Path,
) -> None:
    if statement.decorator_list:
        raise ValueError(
            f"{source_path} definition {statement.name!r} cannot use decorators; "
            "decorators execute at import time"
        )
    expressions: list[ast.AST] = []
    if isinstance(statement, ast.FunctionDef):
        expressions.extend(statement.args.defaults)
        expressions.extend(
            item for item in statement.args.kw_defaults if item is not None
        )
        expressions.extend(
            annotation
            for annotation in (
                statement.returns,
                *(
                    argument.annotation
                    for argument in (
                        *statement.args.posonlyargs,
                        *statement.args.args,
                        *statement.args.kwonlyargs,
                    )
                ),
                (
                    None
                    if statement.args.vararg is None
                    else statement.args.vararg.annotation
                ),
                (
                    None
                    if statement.args.kwarg is None
                    else statement.args.kwarg.annotation
                ),
            )
            if annotation is not None
        )
    else:
        expressions.extend(statement.bases)
        expressions.extend(keyword.value for keyword in statement.keywords)
        _validate_class_body(statement, source_path)
    if any(
        isinstance(node, (ast.Call, ast.Await, ast.Yield, ast.YieldFrom))
        for expression in expressions
        for node in ast.walk(expression)
    ):
        raise ValueError(
            f"{source_path} definition {statement.name!r} executes a call at import time"
        )


def _validate_class_body(statement: ast.ClassDef, source_path: Path) -> None:
    for item in statement.body:
        if (
            isinstance(item, ast.Expr)
            and isinstance(item.value, ast.Constant)
            and isinstance(item.value.value, str)
        ):
            continue
        if isinstance(item, (ast.FunctionDef, ast.ClassDef)):
            _validate_definition_expressions(item, source_path)
            continue
        if isinstance(item, ast.Assign):
            _literal_value(item.value, source_path)
            continue
        if isinstance(item, ast.AnnAssign) and item.value is not None:
            _literal_value(item.value, source_path)
            continue
        if isinstance(item, ast.Pass):
            continue
        raise ValueError(
            f"{source_path} class {statement.name!r} has executable "
            f"{type(item).__name__} at import time"
        )


def _literal_value(value: ast.AST, source_path: Path) -> object:
    try:
        return ast.literal_eval(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{source_path} top-level assignments must contain literal values"
        ) from exc


def _helper_names(value: object) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)):
        raise TypeError("program helpers must be a literal tuple/list")
    output: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise TypeError("program helper paths must be strings")
        text = item
        if "\\" in text:
            raise ValueError("program helper paths must use forward slashes")
        path = PurePosixPath(text)
        if (
            not text
            or path.is_absolute()
            or path.suffix != ".py"
            or any(part in {"", ".", ".."} for part in path.parts)
            or text == "optimization.py"
            or path.as_posix() != text
        ):
            raise ValueError(
                f"program helper must be a relative .py path below submit/: {text!r}"
            )
        key = text.casefold()
        if key in seen:
            raise ValueError(f"program helper path is duplicated: {text!r}")
        seen.add(key)
        output.append(path.as_posix())
    return tuple(output)


def _helper_path(submit_root: Path, relative: str) -> Path:
    root = submit_root.resolve()
    source = root.joinpath(*PurePosixPath(relative).parts)
    current = root
    for part in PurePosixPath(relative).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"program helper cannot use a symlink: {relative!r}")
    resolved = source.resolve(strict=True)
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError(f"program helper escapes submit/ or is not a file: {relative!r}")
    return resolved


def _capabilities(value: object) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)):
        raise TypeError("program capabilities must be a literal tuple/list")
    if any(not isinstance(item, str) for item in value):
        raise TypeError("program capabilities must contain strings")
    output = tuple(item.strip() for item in value)
    if any(not item for item in output) or len(set(output)) != len(output):
        raise ValueError("program capabilities must be unique non-empty strings")
    return output


def _program_identity(spec: OptimizationProgramSpec) -> Mapping[str, object]:
    return _json_mapping(
        {
            "program_api": spec.api,
            "program": dict(spec.identity),
            "capabilities": list(spec.capabilities),
        },
        label="program semantic identity",
    )


def _spec_semantics(spec: OptimizationProgramSpec) -> object:
    return (
        spec.api,
        spec.entry,
        spec.helpers,
        json.dumps(dict(spec.identity), sort_keys=True, separators=(",", ":")),
        spec.capabilities,
    )


def _json_mapping(value: object, *, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    output = {str(key): item for key, item in value.items()}
    try:
        encoded = json.dumps(
            output,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{label} must contain deterministic JSON values: {exc}") from exc
    return MappingProxyType(json.loads(encoded))


def _hash_json(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _session_job_names(session: CampaignSession) -> tuple[str, ...]:
    return tuple(str(row.get("job_name", "")) for row in session.records())


def _all_infinite(costs: Sequence[Sequence[float]]) -> bool:
    rows = tuple(tuple(float(value) for value in row) for row in costs)
    return bool(rows) and not any(
        math.isfinite(value) for row in rows for value in row
    )


__all__ = [
    "FrozenOptimizationProgram",
    "OptimizationProgramContext",
    "OptimizationProgramSpec",
    "OptimizationRunScope",
    "OptimizationSourceInspection",
    "PROGRAM_API",
    "PROGRAM_DECLARATION_NAME",
    "ProgramGenerationScope",
    "execute_frozen_program",
    "freeze_workspace_program",
    "frozen_program_entry",
    "inspect_workspace_optimization",
]
