"""Public backend API for the integrated surrogate viewer tool."""

from .checkpoints import CheckpointPredictor, discover_checkpoints
from .rawdata import (
    extract_curve,
    finite_curve_statistics,
    rawdata_names,
)
from .types import (
    AuditCancelled,
    CheckpointInfo,
    CrossGenerationErrorAudit,
    CurveData,
    ErrorMatrix,
    ParameterSpec,
    PredictionResult,
    RealResult,
    _check_cancelled,
)
from .workspace import (
    SurrogateWorkspace,
    sample_real_results_by_generation,
)

__all__ = [
    "AuditCancelled",
    "CheckpointInfo",
    "CheckpointPredictor",
    "CrossGenerationErrorAudit",
    "CurveData",
    "ErrorMatrix",
    "ParameterSpec",
    "PredictionResult",
    "RealResult",
    "SurrogateWorkspace",
    "_check_cancelled",
    "discover_checkpoints",
    "extract_curve",
    "finite_curve_statistics",
    "rawdata_names",
    "sample_real_results_by_generation",
]
