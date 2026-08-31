"""Opt-in per-field PCA/SVD rawData surrogate implementation."""

from .model import (
    fit_linear_subspace,
    fit_multioutput_ridge,
    predict_raw_data,
    reconstruction_oracle,
)
from .settings import (
    DEFAULT_LINEAR_SUBSPACE_SETTINGS,
    LinearSubspaceSettings,
)
from .types import (
    FieldBasis,
    LinearSubspaceModel,
    LinearSubspaceCodec,
    LinearSubspaceState,
    OracleReconstruction,
)
from ..training import SurrogateTrainingData


__all__ = [
    "DEFAULT_LINEAR_SUBSPACE_SETTINGS",
    "FieldBasis",
    "LinearSubspaceModel",
    "LinearSubspaceCodec",
    "LinearSubspaceSettings",
    "LinearSubspaceState",
    "OracleReconstruction",
    "SurrogateTrainingData",
    "fit_linear_subspace",
    "fit_multioutput_ridge",
    "predict_raw_data",
    "reconstruction_oracle",
]
