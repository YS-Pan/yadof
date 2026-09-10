"""Immutable explicit controls for the experimental retrieval response model."""
from dataclasses import asdict, dataclass
import math
from numbers import Integral, Real

@dataclass(frozen=True, slots=True)
class RetrievalResponseSettings:
    random_seed: int = 20260909
    neighbors: int = 8
    shape_rank: int = 16
    hidden_width: int = 96
    members: int = 2
    steps: int = 96
    validation_steps: int = 8
    validation_fraction: float = 0.2
    batch_size: int = 128
    learning_rate: float = 0.002
    weight_decay: float = 0.0001
    gradient_clip: float = 1.0
    minimum_training_samples: int = 8
    prediction_chunk: int = 128
    constant_tolerance: float = 1e-12
    numerical_floor: float = 1e-12
    span_floor_relative: float = 1e-06

    def __post_init__(self):
        for name, lower in (("random_seed", 0), ("neighbors", 1), ("shape_rank", 1),
                            ("hidden_width", 1), ("members", 1), ("steps", 1),
                            ("validation_steps", 1), ("batch_size", 1),
                            ("minimum_training_samples", 3), ("prediction_chunk", 1)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, Integral) or value < lower:
                raise ValueError(f"retrieval_response {name} must be an integer >= {lower}")
            object.__setattr__(self, name, int(value))
        if self.random_seed > 2**32 - 9001 or self.members > 3 or self.neighbors > 8:
            raise ValueError("retrieval_response requires a bounded seed, <=3 members and <=8 neighbors")
        for name in ("validation_fraction", "learning_rate", "weight_decay", "gradient_clip",
                     "constant_tolerance", "numerical_floor", "span_floor_relative"):
            value = getattr(self, name)
            if (isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value)
                    or value < 0 or (value == 0 and name not in ("weight_decay", "constant_tolerance"))):
                raise ValueError(f"retrieval_response invalid {name}")
            object.__setattr__(self, name, float(value))
        if not 0 < self.validation_fraction < 1:
            raise ValueError("retrieval_response validation_fraction must be between 0 and 1")

    def semantic_parameters(self):
        return {**asdict(self), "variant": "n02-joint-retrieval-response-delta-v1",
                "device": "cpu", "cpu_threads": 1}

    @classmethod
    def from_parameters(cls, values):
        values = dict(values)
        for key, expected in (("variant", "n02-joint-retrieval-response-delta-v1"),
                              ("device", "cpu"), ("cpu_threads", 1)):
            if values.pop(key) != expected:
                raise ValueError(f"retrieval_response unsupported {key}")
        return cls(**values)

DEFAULT_RETRIEVAL_RESPONSE_SETTINGS = RetrievalResponseSettings()
