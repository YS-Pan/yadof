"""Resident external-PyChrono session shared by all execution modes."""

from pathlib import Path
import numpy as np
from chrono_com import PyChronoSession, PyChronoSimulationError

YADOF_FAST_API = "yadof.fast.session/v1"
PHYSICAL_FAILURE_TYPES = (PyChronoSimulationError,)
DEFAULT_CHILD_TIMEOUT_SEC = 120.0


class _EvaluationSession:
    def __init__(self, context):
        self.runtime = PyChronoSession(
            Path(__file__).with_name("chrono_worker.py"),
            scratch_root=Path(context["session_dir"]) / "pychrono",
            environment=context.get("environment"),
        )

    def evaluate_rawdata(self, parameters, context):
        timeout = context.get("timeout_sec")
        return self.runtime.evaluate_rawdata(
            parameters, timeout=DEFAULT_CHILD_TIMEOUT_SEC if timeout is None else float(timeout),
            evaluation_id=str(context["evaluation_name"]), backend=str(context.get("backend", "fast")),
        )

    def close(self):
        self.runtime.close()


def create_evaluation_session(context):
    return _EvaluationSession(context)


def evaluate_prepared(parameters, context):
    """One session/one evaluation for a prepared job, using the identical kernel."""

    if context["backend"] not in {"local", "distributed"}:
        raise ValueError("prepared backend must be local or distributed")
    session = create_evaluation_session({
        "session_dir": Path(context["scratch_dir"]) / "session",
        "environment": context.get("environment"),
    })
    try:
        payloads, diagnostics = session.evaluate_rawdata(parameters, context)
        for filename, payload in payloads.items():
            np.savez_compressed(Path(context["rawdata_dir"]) / filename, **payload)
        return diagnostics
    finally:
        session.close()
