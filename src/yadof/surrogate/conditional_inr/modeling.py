from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from .settings import DEFAULT_CONDITIONAL_INR_SETTINGS


MEMBER_SEED_STRIDE = 1009
BOOTSTRAP_MIN_SAMPLES_PER_INPUT = 2
MODEL_ARCHITECTURE_VERSION = 2
MODEL_NAME = "conditional_inr_rawdata_deep_ensemble"


@dataclass(frozen=True)
class INRTrainConfig:
    epochs: int = DEFAULT_CONDITIONAL_INR_SETTINGS.epochs
    ensemble_size: int = DEFAULT_CONDITIONAL_INR_SETTINGS.ensemble_size
    batch_size: int = DEFAULT_CONDITIONAL_INR_SETTINGS.batch_size
    lr: float = DEFAULT_CONDITIONAL_INR_SETTINGS.learning_rate
    weight_decay: float = DEFAULT_CONDITIONAL_INR_SETTINGS.weight_decay
    loss_beta: float = DEFAULT_CONDITIONAL_INR_SETTINGS.loss_beta
    x_latent_dim: int = DEFAULT_CONDITIONAL_INR_SETTINGS.x_latent_dim
    field_emb_dim: int = DEFAULT_CONDITIONAL_INR_SETTINGS.field_embedding_dim
    coord_fourier_features: int = DEFAULT_CONDITIONAL_INR_SETTINGS.coordinate_fourier_features
    hidden_dim: int = DEFAULT_CONDITIONAL_INR_SETTINGS.hidden_dim
    hidden_layers: int = DEFAULT_CONDITIONAL_INR_SETTINGS.hidden_layers
    train_query_chunk: int = DEFAULT_CONDITIONAL_INR_SETTINGS.train_query_chunk
    train_query_sample_count: int = DEFAULT_CONDITIONAL_INR_SETTINGS.train_query_sample_count
    sample_batch_eval: int = DEFAULT_CONDITIONAL_INR_SETTINGS.sample_batch_eval
    query_batch_eval: int = DEFAULT_CONDITIONAL_INR_SETTINGS.query_batch_eval
    bootstrap_members: bool = DEFAULT_CONDITIONAL_INR_SETTINGS.bootstrap_members
    bootstrap_fraction: float = DEFAULT_CONDITIONAL_INR_SETTINGS.bootstrap_fraction


def _positive_int(name: str, value: int) -> int:
    value = int(value)
    if value <= 0:
        raise ValueError(f"{name} must be positive but got {value}")
    return value


def _positive_float(name: str, value: float) -> float:
    value = float(value)
    if value <= 0.0:
        raise ValueError(f"{name} must be positive but got {value}")
    return value


class MLP(nn.Module):
    def __init__(self, in_dim: int, hidden_dim: int, hidden_layers: int, out_dim: int) -> None:
        super().__init__()
        layers: list[nn.Module] = []
        prev = int(in_dim)
        for _idx in range(max(0, int(hidden_layers))):
            layers.append(nn.Linear(prev, int(hidden_dim)))
            layers.append(nn.GELU())
            prev = int(hidden_dim)
        layers.append(nn.Linear(prev, int(out_dim)))
        self.net = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class FourierFeatures(nn.Module):
    def __init__(self, in_dim: int, n_features: int, sigma: float = 8.0) -> None:
        super().__init__()
        n_features = _positive_int("coord_fourier_features", n_features)
        self.register_buffer("basis", torch.randn(int(in_dim), n_features) * float(sigma))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        projected = 2.0 * math.pi * (x @ self.basis)
        return torch.cat((x, torch.sin(projected), torch.cos(projected)), dim=-1)


class ConditionalRawDataINR(nn.Module):
    def __init__(
        self,
        input_dim: int,
        n_fields: int,
        cfg: INRTrainConfig,
    ) -> None:
        super().__init__()
        input_dim = _positive_int("input_dim", input_dim)
        n_fields = _positive_int("n_fields", n_fields)
        self.x_encoder = MLP(input_dim, cfg.hidden_dim, cfg.hidden_layers, cfg.x_latent_dim)
        self.coord_embed = FourierFeatures(3, cfg.coord_fourier_features, sigma=8.0)
        self.field_emb = nn.Embedding(n_fields, cfg.field_emb_dim)
        coord_dim = 3 + 2 * int(cfg.coord_fourier_features)
        decoder_in = int(cfg.x_latent_dim) + coord_dim + int(cfg.field_emb_dim)
        self.decoder = MLP(decoder_in, cfg.hidden_dim, cfg.hidden_layers, 1)
        output_layer = self.decoder.net[-1]
        if not isinstance(output_layer, nn.Linear):
            raise TypeError("conditional INR decoder must end with a linear layer")
        nn.init.normal_(output_layer.weight, mean=0.0, std=1.0e-3)
        nn.init.zeros_(output_layer.bias)

    def encode_x(self, x: torch.Tensor) -> torch.Tensor:
        return self.x_encoder(2.0 * x - 1.0)

    def decode(self, z: torch.Tensor, coords: torch.Tensor, field_ids: torch.Tensor) -> torch.Tensor:
        batch_size, n_queries, _coord_width = coords.shape
        z_expanded = z[:, None, :].expand(batch_size, n_queries, -1)
        coord_feat = self.coord_embed(coords.reshape(-1, 3)).reshape(batch_size, n_queries, -1)
        field_feat = self.field_emb(field_ids.reshape(-1)).reshape(batch_size, n_queries, -1)
        hidden = torch.cat((z_expanded, coord_feat, field_feat), dim=-1)
        values = self.decoder(hidden.reshape(batch_size * n_queries, -1)).reshape(batch_size, n_queries)
        return values

    def forward(self, x: torch.Tensor, coords: torch.Tensor, field_ids: torch.Tensor) -> torch.Tensor:
        return self.decode(self.encode_x(x), coords, field_ids)


class DeepEnsembleINR(nn.Module):
    def __init__(self, members: list[ConditionalRawDataINR]) -> None:
        super().__init__()
        if not members:
            raise ValueError("deep ensemble needs at least one member")
        self.members = nn.ModuleList(members)

    def forward(self, x: torch.Tensor, coords: torch.Tensor, field_ids: torch.Tensor) -> torch.Tensor:
        return torch.stack([member(x, coords, field_ids) for member in self.members], dim=0).mean(dim=0)


def member_list(model_or_models) -> list[ConditionalRawDataINR]:
    if isinstance(model_or_models, DeepEnsembleINR):
        return list(model_or_models.members)
    if isinstance(model_or_models, (list, tuple)):
        return list(model_or_models)
    return [model_or_models]


def build_inr_model(input_dim: int, n_fields: int, cfg: INRTrainConfig) -> ConditionalRawDataINR:
    return ConditionalRawDataINR(input_dim=input_dim, n_fields=n_fields, cfg=cfg)


def save_inr_artifacts(
    model_or_models,
    artifact_dir: Path,
    *,
    input_dim: int,
    n_fields: int,
    train_cfg: INRTrainConfig,
) -> None:
    members = member_list(model_or_models)
    if not members:
        raise ValueError("cannot save an empty ensemble")

    artifact_dir = Path(artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    for stale in artifact_dir.glob("member_*.pt"):
        stale.unlink()

    meta = {
        "model": MODEL_NAME,
        "architecture_version": MODEL_ARCHITECTURE_VERSION,
        "input_dim": int(input_dim),
        "n_fields": int(n_fields),
        "member_count": int(len(members)),
        "train_cfg": asdict(train_cfg),
    }
    (artifact_dir / "inr_meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False),
        encoding="utf-8",
        newline="\n",
    )
    for member_idx, member in enumerate(members):
        torch.save(member.state_dict(), artifact_dir / f"member_{member_idx:03d}.pt")


def load_inr_artifacts(artifact_dir: Path, device: torch.device):
    artifact_dir = Path(artifact_dir)
    meta = json.loads((artifact_dir / "inr_meta.json").read_text(encoding="utf-8"))
    architecture_version = int(meta.get("architecture_version", 0))
    if architecture_version != MODEL_ARCHITECTURE_VERSION:
        raise ValueError(
            "conditional INR artifact architecture version "
            f"{architecture_version} is incompatible with expected "
            f"version {MODEL_ARCHITECTURE_VERSION}"
        )
    input_dim = _positive_int("input_dim", meta["input_dim"])
    n_fields = _positive_int("n_fields", meta["n_fields"])
    train_cfg = INRTrainConfig(**dict(meta["train_cfg"]))
    member_count = _positive_int("member_count", meta.get("member_count", 1))

    members = []
    for member_idx in range(member_count):
        model = build_inr_model(input_dim, n_fields, train_cfg)
        state = torch.load(artifact_dir / f"member_{member_idx:03d}.pt", map_location=device)
        model.load_state_dict(state)
        model.to(device)
        model.eval()
        members.append(model)
    out = members[0] if len(members) == 1 else DeepEnsembleINR(members).to(device)
    out.eval()
    return out, input_dim, n_fields, train_cfg


def _predict_train_batch(
    model: ConditionalRawDataINR,
    x_batch: torch.Tensor,
    coords: torch.Tensor,
    fields: torch.Tensor,
    query_chunk: int,
) -> torch.Tensor:
    z = model.encode_x(x_batch)
    batch_size = int(x_batch.shape[0])
    query_chunk = max(1, int(query_chunk))
    if coords.shape[0] <= query_chunk:
        return model.decode(
            z,
            coords.unsqueeze(0).expand(batch_size, -1, -1),
            fields.unsqueeze(0).expand(batch_size, -1),
        )

    chunks = []
    for start in range(0, int(coords.shape[0]), query_chunk):
        end = min(int(coords.shape[0]), start + query_chunk)
        chunks.append(
            model.decode(
                z,
                coords[start:end].unsqueeze(0).expand(batch_size, -1, -1),
                fields[start:end].unsqueeze(0).expand(batch_size, -1),
            )
        )
    return torch.cat(chunks, dim=1)


def _bootstrap_indices(n_samples: int, fraction: float, rng: np.random.Generator) -> np.ndarray:
    n_samples = _positive_int("n_samples", n_samples)
    fraction = _positive_float("bootstrap_fraction", fraction)
    size = max(1, int(round(n_samples * fraction)))
    return np.asarray(rng.integers(0, n_samples, size=size), dtype=np.int64)


def _mean(values: list[float]) -> float:
    return float(np.mean(values)) if values else float("nan")


def _field_macro_smooth_l1(
    pred: torch.Tensor,
    target: torch.Tensor,
    *,
    beta: float,
    field_ids: torch.Tensor,
) -> torch.Tensor:
    """Average pointwise loss within fields, then equally across fields."""

    if pred.shape != target.shape or pred.ndim != 2:
        raise ValueError("field-macro loss expects matching [sample, query] tensors")
    fields = field_ids.to(dtype=torch.long, device=pred.device).reshape(-1)
    if fields.numel() != pred.shape[1]:
        raise ValueError("field ids must align with the query dimension")
    pointwise = F.smooth_l1_loss(
        pred,
        target,
        beta=float(beta),
        reduction="none",
    )
    field_losses = [
        pointwise[:, fields == field_id].mean()
        for field_id in torch.unique(fields, sorted=True)
    ]
    if not field_losses:
        raise ValueError("field-macro loss needs at least one active field")
    return torch.stack(field_losses).mean()


def _field_balanced_query_indices(
    *,
    field_ids: np.ndarray,
    sample_count: int,
    seed: int,
    step_index: int,
) -> np.ndarray | None:
    """Select a seeded, field-balanced query subset with rotating coverage."""

    fields = np.asarray(field_ids, dtype=np.int64).reshape(-1)
    n_queries = _positive_int("n_queries", fields.size)
    sample_count = _positive_int("train_query_sample_count", sample_count)
    if np.any(fields < 0):
        raise ValueError("field ids must be non-negative")
    budget = min(n_queries, sample_count)
    if budget >= n_queries:
        return None

    unique_fields = np.unique(fields)
    field_count = int(unique_fields.size)
    if field_count == 0:
        raise ValueError("query sampling needs at least one active field")
    base_order = np.random.default_rng(int(seed)).permutation(unique_fields)
    groups = {
        int(field_id): np.flatnonzero(fields == field_id).astype(np.int64, copy=False)
        for field_id in unique_fields
    }
    step = max(0, int(step_index))

    def counts_for(selected_step: int) -> dict[int, int]:
        counts = {int(field_id): 0 for field_id in unique_fields}
        if budget < field_count:
            start = (int(selected_step) * budget) % field_count
            for offset in range(budget):
                counts[int(base_order[(start + offset) % field_count])] = 1
            return counts

        start = int(selected_step) % field_count
        rotated = [
            int(base_order[(start + offset) % field_count])
            for offset in range(field_count)
        ]
        remaining = int(budget)
        while remaining > 0:
            available = [
                field_id
                for field_id in rotated
                if counts[field_id] < int(groups[field_id].size)
            ]
            if not available:
                break
            share = max(1, remaining // len(available))
            for field_id in available:
                increment = min(
                    share,
                    remaining,
                    int(groups[field_id].size) - counts[field_id],
                )
                counts[field_id] += increment
                remaining -= increment
                if remaining == 0:
                    break
        return counts

    counts = counts_for(step)
    period = (
        field_count // math.gcd(field_count, budget)
        if budget < field_count
        else field_count
    )
    period_counts = [counts_for(period_step) for period_step in range(period)]
    complete_periods, partial_steps = divmod(step, period)
    selected: list[np.ndarray] = []
    for field_id in base_order:
        selected_field = int(field_id)
        count = counts[selected_field]
        if count <= 0:
            continue
        group = groups[selected_field]
        prior_count = complete_periods * sum(
            item[selected_field] for item in period_counts
        ) + sum(
            period_counts[period_step][selected_field]
            for period_step in range(partial_steps)
        )
        field_order = np.random.default_rng(
            int(seed) + (selected_field + 1) * 1_000_003
        ).permutation(group)
        positions = (
            prior_count + np.arange(count, dtype=np.int64)
        ) % int(group.size)
        selected.append(field_order[positions])
    if not selected:
        raise ValueError("field-balanced query sampling produced no queries")
    output = np.concatenate(selected).astype(np.int64, copy=False)
    output.sort()
    if output.size != budget:
        raise ValueError(
            f"field-balanced query sampling selected {output.size} queries; expected {budget}"
        )
    return np.ascontiguousarray(output, dtype=np.int64)

def _slice_targets(
    matrix: np.ndarray,
    row_indices: np.ndarray,
    query_indices: np.ndarray | None,
) -> np.ndarray:
    if query_indices is None:
        return np.ascontiguousarray(matrix[row_indices], dtype=np.float32)
    return np.ascontiguousarray(matrix[np.ix_(row_indices, query_indices)], dtype=np.float32)


def _train_one_member(
    model: ConditionalRawDataINR,
    *,
    X_train: np.ndarray,
    Y_train: np.ndarray,
    coords_device: torch.Tensor,
    fields_device: torch.Tensor,
    field_ids: np.ndarray,
    device: torch.device,
    cfg: INRTrainConfig,
    shuffle_seed: int,
) -> dict[str, float]:
    configured_epochs = _positive_int("epochs", cfg.epochs)
    batch_size = _positive_int("batch_size", cfg.batch_size)
    train_query_sample_count = _positive_int("train_query_sample_count", cfg.train_query_sample_count)
    n_queries = _positive_int("query_count", Y_train.shape[1])

    steps_per_epoch = max(1, math.ceil(X_train.shape[0] / batch_size))
    active_field_count = int(np.unique(field_ids).size)
    query_budget = min(n_queries, train_query_sample_count)
    coverage_steps = (
        active_field_count // math.gcd(active_field_count, query_budget)
        if query_budget < active_field_count
        else 1
    )
    configured_steps = configured_epochs * steps_per_epoch
    effective_steps = math.ceil(configured_steps / coverage_steps) * coverage_steps
    epochs = math.ceil(effective_steps / steps_per_epoch)

    optimizer = torch.optim.AdamW(model.parameters(), lr=float(cfg.lr), weight_decay=float(cfg.weight_decay))
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(1, epochs))
    model.to(device)

    final_terms: dict[str, list[float]] | None = None
    for epoch in range(1, epochs + 1):
        model.train()
        order = np.random.default_rng(int(shuffle_seed) + epoch).permutation(X_train.shape[0])
        terms = {"loss": []}

        for start in range(0, X_train.shape[0], batch_size):
            step_index = (epoch - 1) * steps_per_epoch + start // batch_size
            if step_index >= effective_steps:
                break
            idx = order[start : start + batch_size]
            query_idx = _field_balanced_query_indices(
                field_ids=field_ids,
                sample_count=train_query_sample_count,
                seed=int(shuffle_seed),
                step_index=step_index,
            )
            if query_idx is None:
                coords_batch = coords_device
                fields_batch = fields_device
            else:
                query_idx_device = torch.as_tensor(query_idx, dtype=torch.long, device=device)
                coords_batch = coords_device.index_select(0, query_idx_device)
                fields_batch = fields_device.index_select(0, query_idx_device)

            x_batch = torch.from_numpy(np.ascontiguousarray(X_train[idx], dtype=np.float32)).to(device)
            y_batch = torch.from_numpy(_slice_targets(Y_train, idx, query_idx)).to(device)

            pred = _predict_train_batch(
                model=model,
                x_batch=x_batch,
                coords=coords_batch,
                fields=fields_batch,
                query_chunk=cfg.train_query_chunk,
            )
            loss = _field_macro_smooth_l1(
                pred,
                y_batch,
                beta=float(cfg.loss_beta),
                field_ids=fields_batch,
            )

            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()

            terms["loss"].append(float(loss.detach().cpu()))

        scheduler.step()
        final_terms = terms

    if final_terms is None:
        raise ValueError("surrogate training produced no epochs")
    return {
        **{name: _mean(values) for name, values in final_terms.items()},
        "configured_epochs": float(configured_epochs),
        "effective_epochs": float(epochs),
        "effective_training_steps": float(effective_steps),
        "field_coverage_steps": float(coverage_steps),
    }


def fit_deep_ensemble_conditional_inr(
    *,
    input_dim: int,
    n_fields: int,
    X_train: np.ndarray,
    Y_train: np.ndarray,
    coord_table: np.ndarray,
    field_ids: np.ndarray,
    device: torch.device,
    train_cfg: INRTrainConfig,
    artifact_dir: Path | None = None,
    seed: int = 0,
):
    input_dim = _positive_int("input_dim", input_dim)
    n_fields = _positive_int("n_fields", n_fields)
    X_train = np.ascontiguousarray(X_train, dtype=np.float32)
    Y_train = np.ascontiguousarray(Y_train, dtype=np.float32)
    coord_table = np.ascontiguousarray(coord_table, dtype=np.float32)
    field_ids = np.ascontiguousarray(field_ids, dtype=np.int64)

    if X_train.ndim != 2 or X_train.shape[1] != int(input_dim):
        raise ValueError(f"X_train must have shape [N, {int(input_dim)}]")
    if Y_train.ndim != 2 or Y_train.shape[0] != X_train.shape[0]:
        raise ValueError("Y_train must have shape [N, Q] with the same sample count as X_train")
    if coord_table.ndim != 2 or coord_table.shape[1] != 3:
        raise ValueError("coord_table must have shape [Q, 3]")
    if field_ids.ndim != 1 or field_ids.size != coord_table.shape[0]:
        raise ValueError("field_ids must align with coord_table")
    if Y_train.shape[1] != coord_table.shape[0]:
        raise ValueError("Y_train must be sampled on coord_table")
    if X_train.shape[0] == 0 or Y_train.shape[1] == 0:
        raise ValueError("surrogate training needs at least one sample and one query")
    if np.any(field_ids < 0) or int(np.max(field_ids, initial=-1)) >= n_fields:
        raise ValueError("field_ids must refer to configured fields")
    active_field_count = int(np.unique(field_ids).size)
    sampled_query_count = int(min(Y_train.shape[1], train_cfg.train_query_sample_count))
    train_query_count_per_step = sampled_query_count
    # Sparse high-dimensional histories cannot afford the roughly 37% unique-row
    # loss of an ordinary size-N bootstrap. Independent initialization still
    # diversifies the ensemble until there are enough rows to resample safely.
    bootstrap_min_sample_count = max(
        4,
        BOOTSTRAP_MIN_SAMPLES_PER_INPUT * input_dim,
    )
    bootstrap_applied = bool(
        train_cfg.bootstrap_members
        and X_train.shape[0] >= bootstrap_min_sample_count
    )

    if hasattr(torch, "set_float32_matmul_precision"):
        torch.set_float32_matmul_precision("high")

    coords_device = torch.from_numpy(coord_table).to(device)
    fields_device = torch.from_numpy(field_ids).to(device)
    member_count = _positive_int("ensemble_size", train_cfg.ensemble_size)
    member_seeds = [int(seed) + MEMBER_SEED_STRIDE * idx for idx in range(member_count)]

    members: list[ConditionalRawDataINR] = []
    records = []
    for member_idx, member_seed in enumerate(member_seeds):
        torch.manual_seed(member_seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(member_seed)
        if hasattr(torch, "xpu") and torch.xpu.is_available():
            torch.xpu.manual_seed_all(member_seed)

        model = build_inr_model(input_dim, n_fields, train_cfg)
        visible_x = X_train
        visible_y = Y_train
        unique_samples = int(X_train.shape[0])
        if bootstrap_applied:
            bootstrap_idx = _bootstrap_indices(
                X_train.shape[0],
                train_cfg.bootstrap_fraction,
                np.random.default_rng(member_seed + 31337),
            )
            visible_x = np.ascontiguousarray(X_train[bootstrap_idx], dtype=np.float32)
            visible_y = np.ascontiguousarray(Y_train[bootstrap_idx], dtype=np.float32)
            unique_samples = int(np.unique(bootstrap_idx).size)

        record = _train_one_member(
            model,
            X_train=visible_x,
            Y_train=visible_y,
            coords_device=coords_device,
            fields_device=fields_device,
            field_ids=field_ids,
            device=device,
            cfg=train_cfg,
            shuffle_seed=member_seed,
        )
        record["member"] = int(member_idx)
        record["visible_samples"] = int(visible_x.shape[0])
        record["bootstrap_unique_samples"] = int(unique_samples)
        records.append(record)
        members.append(model)

    if artifact_dir is not None:
        save_inr_artifacts(
            members,
            Path(artifact_dir),
            input_dim=input_dim,
            n_fields=n_fields,
            train_cfg=train_cfg,
        )

    model = members[0] if len(members) == 1 else DeepEnsembleINR(members).to(device)
    model.eval()
    history = {
        "model": MODEL_NAME,
        "architecture_version": MODEL_ARCHITECTURE_VERSION,
        "normalized_input_domain": "[-1, 1]",
        "decoder_output": "linear_standard_score",
        "member_count": int(member_count),
        "member_seeds": [int(value) for value in member_seeds],
        "epochs": int(train_cfg.epochs),
        "effective_epochs": int(
            max(int(item["effective_epochs"]) for item in records)
        ),
        "effective_training_steps": int(
            max(int(item["effective_training_steps"]) for item in records)
        ),
        "batch_size": int(train_cfg.batch_size),
        "train_sample_count": int(X_train.shape[0]),
        "query_count": int(Y_train.shape[1]),
        "train_query_count_per_step": int(train_query_count_per_step),
        "active_field_count": int(active_field_count),
        "train_query_subsampled": bool(sampled_query_count < Y_train.shape[1]),
        "field_rotation_required": bool(sampled_query_count < active_field_count),
        "bootstrap_requested": bool(train_cfg.bootstrap_members),
        "bootstrap_applied": bool(bootstrap_applied),
        "bootstrap_min_sample_count": int(bootstrap_min_sample_count),
        "training_policy": "real_field_balanced",
        "device": str(device),
        "members": records,
        "loss": _mean([float(item["loss"]) for item in records]),
    }
    return model, history


@torch.no_grad()
def _predict_single_model(
    model: ConditionalRawDataINR,
    X: np.ndarray,
    coord_table: np.ndarray,
    field_ids: np.ndarray,
    device: torch.device,
    sample_batch: int,
    query_batch: int,
) -> np.ndarray:
    model.eval()
    X_cpu = torch.from_numpy(np.ascontiguousarray(X, dtype=np.float32))
    coords_cpu = torch.from_numpy(np.ascontiguousarray(coord_table, dtype=np.float32))
    fields_cpu = torch.from_numpy(np.ascontiguousarray(field_ids, dtype=np.int64))
    sample_batch = max(1, int(sample_batch))
    query_batch = max(1, int(query_batch))

    out = np.empty((X_cpu.shape[0], coords_cpu.shape[0]), dtype=np.float32)
    for sample_start in range(0, X_cpu.shape[0], sample_batch):
        x_batch = X_cpu[sample_start : sample_start + sample_batch].to(device)
        batch_size = int(x_batch.shape[0])
        if coords_cpu.shape[0] == 0:
            out[sample_start : sample_start + batch_size] = np.zeros((batch_size, 0), dtype=np.float32)
            continue

        z = model.encode_x(x_batch)
        chunks = []
        for query_start in range(0, coords_cpu.shape[0], query_batch):
            query_end = min(int(coords_cpu.shape[0]), query_start + query_batch)
            coords = coords_cpu[query_start:query_end].to(device).unsqueeze(0).expand(batch_size, -1, -1)
            fields = fields_cpu[query_start:query_end].to(device).unsqueeze(0).expand(batch_size, -1)
            chunks.append(model.decode(z, coords, fields).cpu().numpy())
        out[sample_start : sample_start + batch_size] = np.concatenate(chunks, axis=1)
    return out.astype(np.float32)


@torch.no_grad()
def predict_conditional_inr_members(
    model,
    X: np.ndarray,
    coord_table: np.ndarray,
    field_ids: np.ndarray,
    device: torch.device,
    sample_batch: int = 64,
    query_batch: int = 8192,
) -> np.ndarray:
    members = member_list(model)
    if not members:
        raise ValueError("prediction needs at least one model")
    predictions = [
        _predict_single_model(
            member,
            X=X,
            coord_table=coord_table,
            field_ids=field_ids,
            device=device,
            sample_batch=sample_batch,
            query_batch=query_batch,
        )
        for member in members
    ]
    return np.stack(predictions, axis=0).astype(np.float32)


@torch.no_grad()
def predict_conditional_inr(
    model,
    X: np.ndarray,
    coord_table: np.ndarray,
    field_ids: np.ndarray,
    device: torch.device,
    sample_batch: int = 64,
    query_batch: int = 8192,
    return_std: bool = False,
):
    member_predictions = predict_conditional_inr_members(
        model=model,
        X=X,
        coord_table=coord_table,
        field_ids=field_ids,
        device=device,
        sample_batch=sample_batch,
        query_batch=query_batch,
    )
    mean = np.mean(member_predictions, axis=0).astype(np.float32)
    if return_std:
        std = np.std(member_predictions, axis=0).astype(np.float32)
        if member_predictions.shape[0] == 1:
            std = np.zeros_like(mean)
        return mean, std
    return mean
