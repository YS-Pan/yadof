"""Public backend API for the integrated surrogate viewer tool."""

from .checkpoints import CheckpointPredictor, discover_checkpoints
from .hierarchical_checkpoints import (
    HierarchicalCAECheckpointPredictor,
    discover_hierarchical_cae_checkpoints,
)
from .rawdata import (
    extract_curve,
    extract_plot,
    finite_curve_bounds,
    finite_plot_bounds,
    plot_from_coordinate_grid,
    rawdata_dimensions,
    rawdata_names,
)
from .types import (
    AuditCancelled,
    CheckpointInfo,
    CrossGenerationErrorAudit,
    CurveData,
    DimensionSpec,
    ErrorMatrix,
    ParameterSpec,
    PlotData,
    PlotRequest,
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
    "HierarchicalCAECheckpointPredictor",
    "CrossGenerationErrorAudit",
    "CurveData",
    "DimensionSpec",
    "ErrorMatrix",
    "ParameterSpec",
    "PlotData",
    "PlotRequest",
    "PredictionResult",
    "RealResult",
    "SurrogateWorkspace",
    "_check_cancelled",
    "discover_checkpoints",
    "discover_hierarchical_cae_checkpoints",
    "extract_curve",
    "extract_plot",
    "finite_curve_bounds",
    "finite_plot_bounds",
    "plot_from_coordinate_grid",
    "rawdata_dimensions",
    "rawdata_names",
    "sample_real_results_by_generation",
]
