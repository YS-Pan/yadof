"""Versioned task-session lifecycle shared by real and transient evaluation."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
import os
from types import MappingProxyType, ModuleType
from typing import Any

from ..task_loader import task_module
from ..workspace import WorkspaceContext

WorkspaceLike = WorkspaceContext | str | os.PathLike[str]


FAST_SESSION_API = "yadof.fast.session/v1"


def validate_session_module(module: ModuleType) -> tuple[type[Exception], ...]:
    """Check declarations without constructing a session or launching a solver."""

    if getattr(module, "YADOF_FAST_API", None) != FAST_SESSION_API or not callable(
        getattr(module, "create_evaluation_session", None)
    ):
        raise TypeError(
            f"{module.__file__}: fast requires YADOF_FAST_API = {FAST_SESSION_API!r} "
            "and create_evaluation_session(context), returning an object with "
            "evaluate_rawdata(parameters, context) and close(). The old module-level "
            "evaluate_rawdata contract was removed; see yadof docs show user migration_0_6.md."
        )
    failures = getattr(module, "PHYSICAL_FAILURE_TYPES", ())
    if not isinstance(failures, tuple) or any(
        not isinstance(kind, type) or not issubclass(kind, Exception)
        or kind in (Exception, BaseException) for kind in failures
    ):
        raise TypeError("PHYSICAL_FAILURE_TYPES must explicitly list specific exception types")
    return failures


@dataclass(frozen=True)
class TaskEvaluationSession:
    """An opened task object and its explicit physical-failure classification."""

    kernel: Any
    physical_failure_types: tuple[type[Exception], ...]

    def evaluate_rawdata(self, parameters: Mapping[str, float], context: Mapping[str, object]):
        return self.kernel.evaluate_rawdata(parameters, context)


@contextmanager
def open_evaluation_session(
    workspace: WorkspaceLike, context: Mapping[str, object]
) -> Iterator[TaskEvaluationSession]:
    """Load once, create once, evaluate many times, and close before unloading.

    The caller owns a dedicated process and a session directory. Candidate scratch
    and context are supplied separately on every evaluation. A session must rebuild
    physical state for each candidate and must not retain candidate outputs.
    """

    with task_module(workspace, "evaluation") as module:
        failures = validate_session_module(module)
        kernel = module.create_evaluation_session(MappingProxyType(dict(context)))
        close = getattr(kernel, "close", None)
        try:
            if not callable(close) or not callable(getattr(kernel, "evaluate_rawdata", None)):
                raise TypeError("create_evaluation_session() must return evaluate_rawdata() and close() methods")
            yield TaskEvaluationSession(kernel, failures)
        finally:
            if callable(close):
                close()


__all__ = ["FAST_SESSION_API", "TaskEvaluationSession", "open_evaluation_session"]
