"""Immutable, explicit parameters for the amplitude/shape GP."""

from dataclasses import asdict, dataclass
import math
from numbers import Integral, Real


@dataclass(frozen=True, slots=True)
class AmplitudeGPSettings:
    shape_rank: int = 16
    gp_max_rows: int = 512
    elite_fraction: float = 0.5
    minimum_training_samples: int = 64
    random_seed: int = 20260905
    optimizer_iterations: int = 60
    optimizer_factr: float = 1e8
    kernel_amplitude: float = 1.0
    kernel_amplitude_bounds: tuple[float, float] = (1e-3, 1e3)
    length_scale: float = 0.5
    length_scale_bounds: tuple[float, float] = (0.02, 30.0)
    matern_nu: float = 2.5
    noise_level: float = 1e-3
    noise_level_bounds: tuple[float, float] = (1e-8, 0.3)
    alpha: float = 1e-9
    constant_tolerance: float = 1e-12
    numerical_floor: float = 1e-12
    span_floor_relative: float = 1e-6
    minimum_scale_quantile: float = 0.75
    minimum_scale_std_fraction: float = 0.05

    def __post_init__(self):
        for name, lower in (("shape_rank", 1), ("gp_max_rows", 2),
                            ("minimum_training_samples", 2), ("optimizer_iterations", 1),
                            ("random_seed", 0)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, Integral) or value < lower:
                raise ValueError(f"amplitude_gp {name} must be an integer >= {lower}")
            object.__setattr__(self, name, int(value))
        if self.random_seed > 2**32 - 1:
            raise ValueError("amplitude_gp random_seed must fit uint32")
        for name in ("elite_fraction", "optimizer_factr", "kernel_amplitude", "length_scale",
                     "matern_nu", "noise_level", "alpha", "numerical_floor",
                     "span_floor_relative", "minimum_scale_quantile", "minimum_scale_std_fraction",
                     "constant_tolerance"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
                raise ValueError(f"amplitude_gp {name} must be a finite real number")
            if value < 0 or (value == 0 and name != "constant_tolerance"):
                raise ValueError(f"amplitude_gp {name} must be positive")
            object.__setattr__(self, name, float(value))
        if not 0 < self.elite_fraction < 1 or not 0 < self.minimum_scale_quantile <= 1:
            raise ValueError("amplitude_gp fractions must be in their unit intervals")
        if self.matern_nu not in (0.5, 1.5, 2.5):
            raise ValueError("amplitude_gp matern_nu must be 0.5, 1.5 or 2.5")
        for name, initial in (("kernel_amplitude_bounds", self.kernel_amplitude),
                              ("length_scale_bounds", self.length_scale),
                              ("noise_level_bounds", self.noise_level)):
            bounds = getattr(self, name)
            if not isinstance(bounds, (tuple, list)) or len(bounds) != 2:
                raise ValueError(f"amplitude_gp {name} requires two bounds")
            if any(isinstance(v, bool) or not isinstance(v, Real) or not math.isfinite(v)
                   for v in bounds):
                raise ValueError(f"amplitude_gp {name} requires finite real bounds")
            low, high = map(float, bounds)
            if not 0 < low < high or not low <= initial <= high:
                raise ValueError(f"amplitude_gp {name} must bracket its positive initial value")
            object.__setattr__(self, name, (low, high))

    def semantic_parameters(self):
        return asdict(self)


DEFAULT_AMPLITUDE_GP_SETTINGS = AmplitudeGPSettings()
