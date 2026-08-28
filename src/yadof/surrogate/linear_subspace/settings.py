"""Task-owned settings for the opt-in PCA/SVD rawData component."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math


@dataclass(frozen=True, slots=True)
class LinearSubspaceSettings:
    decomposition: str = "pca"
    rank: int = 16
    predictor: str = "ridge"
    ridge_alpha: float = 1e-6
    field_mode: str = "per-field"
    rank_policy: str = "clamp"
    solver: str = "torch-lowrank"
    dtype: str = "float32"
    seed: int = 20260828
    power_iterations: int = 3
    fit_intercept: bool = True
    device: str = "cpu"
    constant_atol: float = 1e-12

    def __post_init__(self) -> None:
        decomposition = str(self.decomposition).strip().lower()
        if decomposition not in {"pca", "svd"}:
            raise ValueError("pca_svd(): decomposition must be 'pca' or 'svd'")
        if isinstance(self.rank, bool) or not isinstance(self.rank, int):
            raise TypeError("pca_svd(): rank must be an integer")
        if self.rank < 1:
            raise ValueError("pca_svd(): rank must be at least one")
        if str(self.predictor).strip().lower() != "ridge":
            raise ValueError("pca_svd(): predictor must be 'ridge'")
        alpha = float(self.ridge_alpha)
        if not math.isfinite(alpha) or alpha < 0:
            raise ValueError("pca_svd(): ridge_alpha must be finite and non-negative")
        if str(self.field_mode).strip().lower() != "per-field":
            raise ValueError("pca_svd(): field_mode must be 'per-field'")
        if str(self.rank_policy).strip().lower() != "clamp":
            raise ValueError("pca_svd(): rank_policy must be 'clamp'")
        if str(self.solver).strip().lower() != "torch-lowrank":
            raise ValueError("pca_svd(): solver must be 'torch-lowrank'")
        dtype = str(self.dtype).strip().lower()
        if dtype not in {"float32", "float64"}:
            raise ValueError("pca_svd(): dtype must be 'float32' or 'float64'")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise TypeError("pca_svd(): seed must be an integer")
        if (
            isinstance(self.power_iterations, bool)
            or not isinstance(self.power_iterations, int)
            or self.power_iterations < 0
        ):
            raise ValueError("pca_svd(): power_iterations must be a non-negative integer")
        if not isinstance(self.fit_intercept, bool):
            raise TypeError("pca_svd(): fit_intercept must be a boolean")
        device = str(self.device).strip().lower()
        if device not in {"cpu", "cuda", "auto"}:
            raise ValueError("pca_svd(): device must be 'cpu', 'cuda', or 'auto'")
        constant_atol = float(self.constant_atol)
        if not math.isfinite(constant_atol) or constant_atol < 0:
            raise ValueError("pca_svd(): constant_atol must be finite and non-negative")
        object.__setattr__(self, "decomposition", decomposition)
        object.__setattr__(self, "predictor", "ridge")
        object.__setattr__(self, "ridge_alpha", alpha)
        object.__setattr__(self, "field_mode", "per-field")
        object.__setattr__(self, "rank_policy", "clamp")
        object.__setattr__(self, "solver", "torch-lowrank")
        object.__setattr__(self, "dtype", dtype)
        object.__setattr__(self, "device", device)
        object.__setattr__(self, "constant_atol", constant_atol)

    def semantic_parameters(self) -> dict[str, object]:
        payload = asdict(self)
        payload.update(
            {
                "centering": "coordinate-wise-training-mean" if self.decomposition == "pca" else "none",
                "parameter_scaling": "caller-owned-normalized-unit-interval",
                "coefficient_scaling": "none",
                "intercept_penalty": "unpenalized" if self.fit_intercept else "not-present",
                "basis_sign": "largest-absolute-loading-positive",
            }
        )
        return payload


DEFAULT_LINEAR_SUBSPACE_SETTINGS = LinearSubspaceSettings()
DEFAULT_PCA_SVD_SETTINGS = DEFAULT_LINEAR_SUBSPACE_SETTINGS
PCASVDSettings = LinearSubspaceSettings


__all__ = [
    "DEFAULT_LINEAR_SUBSPACE_SETTINGS",
    "DEFAULT_PCA_SVD_SETTINGS",
    "LinearSubspaceSettings",
    "PCASVDSettings",
]
