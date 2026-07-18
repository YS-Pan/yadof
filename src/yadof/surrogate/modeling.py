from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


MEMBER_SEED_STRIDE = 1009


@dataclass(frozen=True)
class INRTrainConfig:
    epochs: int = 32
    ensemble_size: int = 3
    batch_size: int = 16
    lr: float = 1e-3
    weight_decay: float = 1e-5
    loss_beta: float = 0.05
    relative_loss_weight: float = 0.15
    relative_loss_eps: float = 0.05
    x_latent_dim: int = 96
    field_emb_dim: int = 12
    coord_fourier_features: int = 24
    hidden_dim: int = 192
    hidden_layers: int = 3
    train_query_chunk: int = 4096
    train_query_sample_count: int = 8192
    sample_batch_eval: int = 64
    query_batch_eval: int = 8192
    bootstrap_members: bool = True
    bootstrap_fraction: float = 1.0


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


def _nonnegative_float(name: str, value: float) -> float:
    value = float(value)
    if value < 0.0:
        raise ValueError(f"{name} must be non-negative but got {value}")
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

    def encode_x(self, x: torch.Tensor) -> torch.Tensor:
        return self.x_encoder(x)

    def decode(self, z: torch.Tensor, coords: torch.Tensor, field_ids: torch.Tensor) -> torch.Tensor:
        batch_size, n_queries, _coord_width = coords.shape
        z_expanded = z[:, None, :].expand(batch_size, n_queries, -1)
        coord_feat = self.coord_embed(coords.reshape(-1, 3)).reshape(batch_size, n_queries, -1)
        field_feat = self.field_emb(field_ids.reshape(-1)).reshape(batch_size, n_queries, -1)
        hidden = torch.cat((z_expanded, coord_feat, field_feat), dim=-1)
        values = self.decoder(hidden.reshape(batch_size * n_queries, -1)).reshape(batch_size, n_queries)
        return torch.sigmoid(values)

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
        "model": "conditional_inr_rawdata_deep_ensemble",
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


def _weighted_smooth_l1(
    pred: torch.Tensor,
    target: torch.Tensor,
    *,
    beta: float,
    query_weights: torch.Tensor | None,
) -> torch.Tensor:
    loss = F.smooth_l1_loss(pred, target, beta=float(beta), reduction="none")
    if query_weights is None:
        return loss.mean()
    weights = query_weights.to(dtype=loss.dtype, device=loss.device).reshape(1, -1)
    return (loss * weights).mean() / weights.mean().clamp_min(1e-12)


def _normalized_query_indices(indices: np.ndarray | None, n_queries: int) -> np.ndarray:
    if indices is None:
        return np.zeros((0,), dtype=np.int64)
    values = np.asarray(indices, dtype=np.int64).reshape(-1)
    if values.size == 0:
        return np.zeros((0,), dtype=np.int64)
    values = values[(values >= 0) & (values < int(n_queries))]
    if values.size == 0:
        return np.zeros((0,), dtype=np.int64)
    return np.unique(values).astype(np.int64, copy=False)


def _query_subset_indices(
    *,
    n_queries: int,
    sample_count: int,
    rng: np.random.Generator,
    sampling_probabilities: np.ndarray | None,
    always_include_indices: np.ndarray | None = None,
) -> np.ndarray | None:
    n_queries = _positive_int("n_queries", n_queries)
    sample_count = _positive_int("train_query_sample_count", sample_count)
    always = _normalized_query_indices(always_include_indices, n_queries)
    if always.size == n_queries:
        return None

    if always.size:
        sampleable_mask = np.ones((n_queries,), dtype=bool)
        sampleable_mask[always] = False
        sampleable = np.flatnonzero(sampleable_mask)
    else:
        sampleable = np.arange(n_queries, dtype=np.int64)

    if sample_count >= sampleable.size:
        return None

    if sampling_probabilities is not None:
        probabilities = np.asarray(sampling_probabilities, dtype=np.float64).reshape(-1)
        if probabilities.size != n_queries:
            raise ValueError("query sampling probabilities must align with query dimension")
        pool_probabilities = probabilities[sampleable]
        total = float(np.sum(pool_probabilities))
        pool_probabilities = None if total <= 0.0 else pool_probabilities / total
        choice = rng.choice(sampleable, size=sample_count, replace=False, p=pool_probabilities)
    else:
        choice = rng.choice(sampleable, size=sample_count, replace=False)
    choice = np.concatenate((always, np.asarray(choice, dtype=np.int64))) if always.size else np.asarray(choice, dtype=np.int64)
    choice = np.unique(choice)
    choice.sort()
    return np.ascontiguousarray(choice, dtype=np.int64)

def _slice_targets(
    matrix: np.ndarray,
    row_indices: np.ndarray,
    query_indices: np.ndarray | None,
) -> np.ndarray:
    if query_indices is None:
        return np.ascontiguousarray(matrix[row_indices], dtype=np.float32)
    return np.ascontiguousarray(matrix[np.ix_(row_indices, query_indices)], dtype=np.float32)


def _sampling_probabilities_from_weights(weights_np: np.ndarray | None) -> np.ndarray | None:
    if weights_np is None:
        return None
    probabilities = np.asarray(weights_np, dtype=np.float64).reshape(-1)
    probabilities = np.where(np.isfinite(probabilities), probabilities, 0.0)
    probabilities = np.maximum(probabilities, 0.0)
    total = float(np.sum(probabilities))
    if total <= 0.0:
        return None
    return np.ascontiguousarray(probabilities / total, dtype=np.float64)


def _train_one_member(
    model: ConditionalRawDataINR,
    *,
    X_train: np.ndarray,
    Y_train: np.ndarray,
    coords_device: torch.Tensor,
    fields_device: torch.Tensor,
    query_weights_device: torch.Tensor | None,
    query_sampling_probabilities: np.ndarray | None,
    always_include_query_indices: np.ndarray | None,
    device: torch.device,
    cfg: INRTrainConfig,
    shuffle_seed: int,
) -> dict[str, float]:
    epochs = _positive_int("epochs", cfg.epochs)
    batch_size = _positive_int("batch_size", cfg.batch_size)
    train_query_sample_count = _positive_int("train_query_sample_count", cfg.train_query_sample_count)
    relative_weight = _nonnegative_float("relative_loss_weight", cfg.relative_loss_weight)
    n_queries = _positive_int("query_count", Y_train.shape[1])

    optimizer = torch.optim.AdamW(model.parameters(), lr=float(cfg.lr), weight_decay=float(cfg.weight_decay))
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(1, epochs))
    model.to(device)

    final_terms: dict[str, list[float]] | None = None
    for epoch in range(1, epochs + 1):
        model.train()
        order = np.random.default_rng(int(shuffle_seed) + epoch).permutation(X_train.shape[0])
        terms = {"loss": [], "value": [], "relative": [], "mixup": []}

        for start in range(0, X_train.shape[0], batch_size):
            idx = order[start : start + batch_size]
            query_rng = np.random.default_rng(int(shuffle_seed) + epoch * 1000003 + start)
            query_idx = _query_subset_indices(
                n_queries=n_queries,
                sample_count=train_query_sample_count,
                rng=query_rng,
                sampling_probabilities=query_sampling_probabilities,
                always_include_indices=always_include_query_indices,
            )
            if query_idx is None:
                coords_batch = coords_device
                fields_batch = fields_device
                weights_batch = query_weights_device
            else:
                query_idx_device = torch.as_tensor(query_idx, dtype=torch.long, device=device)
                coords_batch = coords_device.index_select(0, query_idx_device)
                fields_batch = fields_device.index_select(0, query_idx_device)
                weights_batch = (
                    None
                    if query_sampling_probabilities is not None or query_weights_device is None
                    else query_weights_device.index_select(0, query_idx_device)
                )

            x_batch = torch.from_numpy(np.ascontiguousarray(X_train[idx], dtype=np.float32)).to(device)
            y_batch = torch.from_numpy(_slice_targets(Y_train, idx, query_idx)).to(device)

            pred = _predict_train_batch(
                model=model,
                x_batch=x_batch,
                coords=coords_batch,
                fields=fields_batch,
                query_chunk=cfg.train_query_chunk,
            )
            value_loss = _weighted_smooth_l1(
                pred,
                y_batch,
                beta=float(cfg.loss_beta),
                query_weights=weights_batch,
            )
            loss_terms = [value_loss]
            coeff_sum = 1.0
            rel_loss = torch.zeros((), dtype=value_loss.dtype, device=value_loss.device)
            if relative_weight > 0.0:
                denom = y_batch.abs().clamp_min(float(cfg.relative_loss_eps))
                rel_loss = _weighted_smooth_l1(
                    pred / denom,
                    y_batch / denom,
                    beta=float(cfg.loss_beta),
                    query_weights=weights_batch,
                )
                loss_terms.append(relative_weight * rel_loss)
                coeff_sum += relative_weight

            mix_loss = torch.zeros((), dtype=value_loss.dtype, device=value_loss.device)
            if X_train.shape[0] >= 2:
                rng = np.random.default_rng(int(shuffle_seed) + epoch * 104729 + start)
                other_idx = rng.integers(0, X_train.shape[0], size=idx.size)
                lam_np = rng.uniform(0.10, 0.90, size=(idx.size, 1)).astype(np.float32)
                lam = torch.from_numpy(lam_np).to(device)
                x_other = torch.from_numpy(np.ascontiguousarray(X_train[other_idx], dtype=np.float32)).to(device)
                y_other = torch.from_numpy(_slice_targets(Y_train, other_idx, query_idx)).to(device)
                x_mix = lam * x_batch + (1.0 - lam) * x_other
                y_mix = lam * y_batch + (1.0 - lam) * y_other
                pred_mix = _predict_train_batch(
                    model=model,
                    x_batch=x_mix,
                    coords=coords_batch,
                    fields=fields_batch,
                    query_chunk=cfg.train_query_chunk,
                )
                mix_loss = _weighted_smooth_l1(
                    pred_mix,
                    y_mix,
                    beta=float(cfg.loss_beta),
                    query_weights=weights_batch,
                )
                loss_terms.append(mix_loss)
                coeff_sum += 1.0

            loss = torch.stack(loss_terms).sum() / coeff_sum

            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()

            terms["loss"].append(float(loss.detach().cpu()))
            terms["value"].append(float(value_loss.detach().cpu()))
            terms["relative"].append(float(rel_loss.detach().cpu()))
            terms["mixup"].append(float(mix_loss.detach().cpu()))

        scheduler.step()
        final_terms = terms

    if final_terms is None:
        raise ValueError("surrogate training produced no epochs")
    return {name: _mean(values) for name, values in final_terms.items()}


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
    query_weights: np.ndarray | None = None,
    always_include_query_indices: np.ndarray | None = None,
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
    always_include_query_indices = _normalized_query_indices(always_include_query_indices, Y_train.shape[1])
    sampleable_query_count = int(Y_train.shape[1] - always_include_query_indices.size)
    sampled_query_count = int(min(sampleable_query_count, train_cfg.train_query_sample_count))
    train_query_count_per_step = int(
        Y_train.shape[1]
        if sampled_query_count >= sampleable_query_count
        else always_include_query_indices.size + sampled_query_count
    )
    query_weights_device = None
    query_sampling_probabilities = None
    query_weight_stats: dict[str, float] | None = None
    if query_weights is not None:
        weights_np = np.asarray(query_weights, dtype=np.float32).reshape(-1)
        if weights_np.size != Y_train.shape[1]:
            raise ValueError("query_weights must align with Y_train query dimension")
        weights_np = np.where(np.isfinite(weights_np), weights_np, 0.0)
        weights_np = np.maximum(weights_np, 0.0)
        if float(np.max(weights_np, initial=0.0)) <= 0.0:
            weights_np = np.ones_like(weights_np, dtype=np.float32)
        query_weight_stats = {
            "query_weight_min": float(np.min(weights_np)),
            "query_weight_mean": float(np.mean(weights_np)),
            "query_weight_max": float(np.max(weights_np)),
        }
        query_weights_device = torch.from_numpy(np.ascontiguousarray(weights_np, dtype=np.float32)).to(device)
        query_sampling_probabilities = _sampling_probabilities_from_weights(weights_np)

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
        if bool(train_cfg.bootstrap_members) and X_train.shape[0] >= 4:
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
            query_weights_device=query_weights_device,
            query_sampling_probabilities=query_sampling_probabilities,
            always_include_query_indices=always_include_query_indices,
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
        "model": "conditional_inr_rawdata_deep_ensemble",
        "member_count": int(member_count),
        "member_seeds": [int(value) for value in member_seeds],
        "epochs": int(train_cfg.epochs),
        "batch_size": int(train_cfg.batch_size),
        "train_sample_count": int(X_train.shape[0]),
        "query_count": int(Y_train.shape[1]),
        "train_query_count_per_step": int(train_query_count_per_step),
        "train_query_sampled_count_per_step": int(sampled_query_count),
        "train_query_always_included_count": int(always_include_query_indices.size),
        "train_query_sampleable_count": int(sampleable_query_count),
        "train_query_subsampled": bool(sampled_query_count < sampleable_query_count),
        "device": str(device),
        "members": records,
        "loss": _mean([float(item["loss"]) for item in records]),
        "value": _mean([float(item["value"]) for item in records]),
        "relative": _mean([float(item["relative"]) for item in records]),
        "mixup": _mean([float(item["mixup"]) for item in records]),
    }
    if query_weight_stats is not None:
        history.update(query_weight_stats)
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
