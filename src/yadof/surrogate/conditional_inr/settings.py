"""Immutable conditional-INR settings with no optional-backend imports."""

from __future__ import annotations

from dataclasses import dataclass

from ..._component_settings import boolean, integer, real, text


@dataclass(frozen=True, slots=True)
class ConditionalINRSettings:
    constant_atol: float
    target_scale_floor: float
    device: str
    epochs: int
    ensemble_size: int
    batch_size: int
    learning_rate: float
    weight_decay: float
    loss_beta: float
    max_nonfinite_fraction: float
    x_latent_dim: int
    field_embedding_dim: int
    coordinate_fourier_features: int
    hidden_dim: int
    hidden_layers: int
    train_query_chunk: int
    train_query_sample_count: int
    sample_batch_eval: int
    query_batch_eval: int
    bootstrap_members: bool
    bootstrap_fraction: float

    def semantic_parameters(self) -> dict[str, object]:
        return {
            "constant_atol": self.constant_atol,
            "target_scale_floor": self.target_scale_floor,
            "device": self.device,
            "epochs": self.epochs,
            "ensemble_size": self.ensemble_size,
            "batch_size": self.batch_size,
            "learning_rate": self.learning_rate,
            "weight_decay": self.weight_decay,
            "loss_beta": self.loss_beta,
            "max_nonfinite_fraction": self.max_nonfinite_fraction,
            "x_latent_dim": self.x_latent_dim,
            "field_embedding_dim": self.field_embedding_dim,
            "coordinate_fourier_features": self.coordinate_fourier_features,
            "hidden_dim": self.hidden_dim,
            "hidden_layers": self.hidden_layers,
            "train_query_chunk": self.train_query_chunk,
            "train_query_sample_count": self.train_query_sample_count,
            "sample_batch_eval": self.sample_batch_eval,
            "query_batch_eval": self.query_batch_eval,
            "bootstrap_members": self.bootstrap_members,
            "bootstrap_fraction": self.bootstrap_fraction,
        }


def create_settings(
    factory: str,
    *,
    constant_atol: float,
    target_scale_floor: float,
    device: str,
    epochs: int,
    ensemble_size: int,
    batch_size: int,
    learning_rate: float,
    weight_decay: float,
    loss_beta: float,
    max_nonfinite_fraction: float,
    x_latent_dim: int,
    field_embedding_dim: int,
    coordinate_fourier_features: int,
    hidden_dim: int,
    hidden_layers: int,
    train_query_chunk: int,
    train_query_sample_count: int,
    sample_batch_eval: int,
    query_batch_eval: int,
    bootstrap_members: bool,
    bootstrap_fraction: float,
) -> ConditionalINRSettings:
    positive_ints = {
        "epochs": epochs,
        "ensemble_size": ensemble_size,
        "batch_size": batch_size,
        "x_latent_dim": x_latent_dim,
        "field_embedding_dim": field_embedding_dim,
        "coordinate_fourier_features": coordinate_fourier_features,
        "hidden_dim": hidden_dim,
        "hidden_layers": hidden_layers,
        "train_query_chunk": train_query_chunk,
        "train_query_sample_count": train_query_sample_count,
        "sample_batch_eval": sample_batch_eval,
        "query_batch_eval": query_batch_eval,
    }
    validated_ints = {
        name: integer(factory, name, value, minimum=1)
        for name, value in positive_ints.items()
    }
    return ConditionalINRSettings(
        constant_atol=real(factory, "constant_atol", constant_atol, minimum=0.0),
        target_scale_floor=real(
            factory, "target_scale_floor", target_scale_floor,
            minimum=0.0, minimum_open=True,
        ),
        device=text(factory, "device", device),
        epochs=validated_ints["epochs"],
        ensemble_size=validated_ints["ensemble_size"],
        batch_size=validated_ints["batch_size"],
        learning_rate=real(
            factory, "learning_rate", learning_rate, minimum=0.0, minimum_open=True
        ),
        weight_decay=real(factory, "weight_decay", weight_decay, minimum=0.0),
        loss_beta=real(factory, "loss_beta", loss_beta, minimum=0.0),
        max_nonfinite_fraction=real(
            factory, "max_nonfinite_fraction", max_nonfinite_fraction,
            minimum=0.0, maximum=1.0,
        ),
        x_latent_dim=validated_ints["x_latent_dim"],
        field_embedding_dim=validated_ints["field_embedding_dim"],
        coordinate_fourier_features=validated_ints["coordinate_fourier_features"],
        hidden_dim=validated_ints["hidden_dim"],
        hidden_layers=validated_ints["hidden_layers"],
        train_query_chunk=validated_ints["train_query_chunk"],
        train_query_sample_count=validated_ints["train_query_sample_count"],
        sample_batch_eval=validated_ints["sample_batch_eval"],
        query_batch_eval=validated_ints["query_batch_eval"],
        bootstrap_members=boolean(factory, "bootstrap_members", bootstrap_members),
        bootstrap_fraction=real(
            factory, "bootstrap_fraction", bootstrap_fraction,
            minimum=0.0, minimum_open=True, maximum=1.0,
        ),
    )


DEFAULT_CONDITIONAL_INR_SETTINGS = create_settings(
    "conditional_inr",
    constant_atol=1.0e-12,
    target_scale_floor=1.0e-6,
    device="auto",
    epochs=32,
    ensemble_size=3,
    batch_size=16,
    learning_rate=1.0e-3,
    weight_decay=1.0e-5,
    loss_beta=0.05,
    max_nonfinite_fraction=0.20,
    x_latent_dim=96,
    field_embedding_dim=12,
    coordinate_fourier_features=24,
    hidden_dim=192,
    hidden_layers=3,
    train_query_chunk=4096,
    train_query_sample_count=8192,
    sample_batch_eval=64,
    query_batch_eval=8192,
    bootstrap_members=False,
    bootstrap_fraction=1.0,
)


__all__ = [
    "ConditionalINRSettings",
    "DEFAULT_CONDITIONAL_INR_SETTINGS",
    "create_settings",
]
