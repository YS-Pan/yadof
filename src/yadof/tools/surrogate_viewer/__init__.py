"""Optional read-only surrogate checkpoint viewer integrated with yadof.

Backend exports are loaded lazily so importing :mod:`yadof.tools` or constructing
the main CLI does not require the viewer's optional Torch and Matplotlib
dependencies.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "AuditCancelled",
    "CheckpointInfo",
    "CrossGenerationErrorAudit",
    "ErrorMatrix",
    "ParameterSpec",
    "PredictionResult",
    "RealResult",
    "SurrogateWorkspace",
    "extract_curve",
    "sample_real_results_by_generation",
]


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(name)
    from . import backend

    value = getattr(backend, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted((*globals(), *__all__))
