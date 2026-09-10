"""N02: joint neural correction of retrieved complete-response representations.

Independent experimental package component. No GP, objective head, external labels, history lookup,
checkpoint publication, or simulator execution is implemented here.
"""

from contextlib import ExitStack
import hashlib
import json
import time
import threading

import numpy as np
from scipy.spatial import cKDTree
from sklearn.decomposition import PCA
from threadpoolctl import threadpool_limits
import torch
from torch import nn
from torch.nn import functional as F

from ...job_template.rawdata_template import RawDataSchemaTemplate
from ..training import TrainingCancelledError

_NUMERICAL_LOCK = threading.RLock()


def check_cancelled(event):
    if event is not None and event.is_set():
        raise TrainingCancelledError("retrieval_response training cancelled")





def _split(values):
    low = np.min(values, axis=1, keepdims=True)
    span = np.max(values, axis=1, keepdims=True)-low
    values -= low
    np.divide(values, span, out=values, where=span > 0)
    return low, span, values


def _matrix(samples, field_index, field):
    values = np.empty((len(samples), int(np.prod(field.main_shape))), dtype=np.float64)
    for target, sample in zip(values, samples, strict=True):
        target[:] = np.asarray(sample.items[field_index].payload[field.main_key]).reshape(-1)
    return values


class FieldCodec:
    """A field's amplitude and full-grid shape codec, fitted only on owned rows."""

    def __init__(self, field, low_center, low_scale, span_floor, log_center,
                 log_scale, components, shape_mean, shape_scale):
        self.field = field
        self.low_center, self.low_scale = low_center, low_scale
        self.span_floor, self.log_center, self.log_scale = span_floor, log_center, log_scale
        self.components, self.shape_mean, self.shape_scale = components, shape_mean, shape_scale
        self.rank = 0 if components is None else len(components)
        self.width = 1 + int(span_floor is not None) + self.rank

    # Called through the class; task helpers prohibit import-time decorators.
    def fit(values, field, settings):
        low, span, shape = _split(values)
        center = float(np.median(low))
        scale = max(float(np.quantile(np.abs(low-center), 0.75)),
                    0.05*float(np.std(low)), settings["numerical_floor"])
        pieces = [np.arcsinh((low-center)/scale)]
        if np.max(span) == 0:
            floor, log_center, log_scale = None, 0.0, 1.0
        else:
            floor = max(float(np.median(span[span > 0]))*settings["span_floor_relative"],
                        settings["numerical_floor"])
            logs = np.log(np.maximum(span, floor))
            log_center, log_scale = float(np.mean(logs)), max(float(np.std(logs)), 0.1)
            pieces.append((logs-log_center)/log_scale)
        if values.shape[1] == 1 or np.max(np.ptp(shape, axis=0)) <= settings["constant_tolerance"]:
            components, mean, shape_scale = None, shape.mean(axis=0), 1.0
        else:
            rank = min(settings["shape_rank"], len(values)-1, values.shape[1])
            pca = PCA(n_components=rank, svd_solver="randomized",
                      random_state=settings["random_seed"], copy=False)
            coefficients = pca.fit_transform(shape)
            components, mean = pca.components_, pca.mean_
            shape_scale = max(float(np.sqrt(np.mean(coefficients**2))), settings["numerical_floor"])
            pieces.append(coefficients/shape_scale)
        for array in (components, mean):
            if array is not None:
                array.setflags(write=False)
        return FieldCodec(field, center, scale, floor, log_center, log_scale,
                          components, mean, shape_scale), np.concatenate(pieces, axis=1)

    def encode(self, values):
        low, span, shape = _split(values)
        pieces = [np.arcsinh((low-self.low_center)/self.low_scale)]
        if self.span_floor is not None:
            pieces.append((np.log(np.maximum(span, self.span_floor))-self.log_center)/self.log_scale)
        if self.components is not None:
            pieces.append(((shape-self.shape_mean) @ self.components.T)/self.shape_scale)
        return np.concatenate(pieces, axis=1)

    def loss_weights(self):
        # Equal field weight, then equal minimum/span/shape-group weight.
        groups = 1 + int(self.span_floor is not None) + int(self.rank > 0)
        weights = [1.0/groups]
        if self.span_floor is not None:
            weights.append(1.0/groups)
        if self.rank:
            weights.extend([1.0/(groups*self.rank)]*self.rank)
        return weights

    def decode(self, z):
        low = self.low_center+self.low_scale*np.sinh(z[:, :1])
        start = 1
        if self.span_floor is None:
            span = np.zeros_like(low)
        else:
            span = np.exp(self.log_center+self.log_scale*z[:, 1:2])
            start = 2
        shape = (np.tile(self.shape_mean, (len(z), 1)) if self.components is None
                 else (z[:, start:]*self.shape_scale) @ self.components + self.shape_mean)
        _, decoded_span, shape = _split(shape)
        collapsed = int(np.sum((decoded_span <= 0) & (span > 0)))
        return low+span*shape, collapsed


class ResponseCodec:
    def __init__(self, schema, fields):
        self.schema, self.fields = schema, tuple(fields)
        self.width = sum(field.width for field in fields)
        self.weights = np.asarray([weight/len(fields) for field in fields
                                   for weight in field.loss_weights()], dtype=np.float32)

    # Called through the class; task helpers prohibit import-time decorators.
    def fit(samples, settings, cancel_event=None):
        schema = RawDataSchemaTemplate.from_items(samples[0])
        fields, pieces = [], []
        for index, field in enumerate(schema.fields):
            check_cancelled(cancel_event)
            codec, targets = FieldCodec.fit(_matrix(samples, index, field), field, settings)
            fields.append(codec)
            pieces.append(targets)
        return ResponseCodec(schema, fields), np.asarray(np.concatenate(pieces, axis=1), dtype=np.float32)

    def encode(self, samples):
        pieces = [codec.encode(_matrix(samples, index, codec.field))
                  for index, codec in enumerate(self.fields)]
        return np.asarray(np.concatenate(pieces, axis=1), dtype=np.float32)

    def decode(self, latent):
        arrays, collapsed, start = [], 0, 0
        with np.errstate(over="ignore", invalid="ignore"):
            for codec in self.fields:
                values, count = codec.decode(latent[:, start:start+codec.width])
                arrays.append(values)
                collapsed += count
                start += codec.width
        samples = []
        for row in range(len(latent)):
            main = {}
            for codec, values in zip(self.fields, arrays, strict=True):
                field = codec.field
                value, dtype = values[row], np.dtype(field.main_dtype)
                if not np.all(np.isfinite(value)):
                    break
                if dtype.kind in "iu" and (np.any(value < np.iinfo(dtype).min)
                                           or np.any(value > np.iinfo(dtype).max)):
                    break
                with np.errstate(over="ignore", invalid="ignore"):
                    cast = value.reshape(field.main_shape).astype(dtype)
                if not np.all(np.isfinite(cast)):
                    break
                main[field.selector] = cast
            samples.append(self.schema.reconstruct(main) if len(main) == len(self.fields) else None)
        return tuple(samples), collapsed


class NeighborIndex:
    """Parameter-only retrieval; query identity exclusion is explicit."""

    def __init__(self, x, neighbors):
        self.x = np.asarray(x, dtype=np.float64)
        self.neighbors = neighbors
        self.tree = cKDTree(self.x)

    def query(self, queries, *, self_positions=None):
        excluded = self_positions is not None
        k = min(self.neighbors, len(self.x)-int(excluded))
        if k < 1:
            raise ValueError("Retrieval needs a distinct context observation")
        distances, indices = self.tree.query(np.asarray(queries, dtype=np.float64),
                                            k=k+int(excluded), workers=1)
        distances = np.asarray(distances).reshape(len(queries), -1)
        indices = np.asarray(indices).reshape(len(queries), -1)
        output = np.empty((len(queries), k), dtype=np.int64)
        for row in range(len(queries)):
            order = np.lexsort((indices[row], distances[row]))
            choices = indices[row, order]
            if excluded:
                choices = choices[choices != self_positions[row]]
            output[row] = choices[:k]
        if excluded and np.any(output == np.asarray(self_positions)[:, None]):
            raise RuntimeError("Training query leaked into its retrieval context")
        return output


class NeighborDeltaNet(nn.Module):
    """One shared cross-field correction and small attention adjustment."""

    def __init__(self, parameter_width, response_width, hidden_width):
        super().__init__()
        self.hidden = nn.Sequential(nn.Linear(2*parameter_width+response_width, hidden_width),
            nn.SiLU(), nn.Linear(hidden_width, hidden_width), nn.SiLU())
        self.delta = nn.Linear(hidden_width, response_width)
        self.attention = nn.Linear(hidden_width, 1)
        nn.init.zeros_(self.delta.weight)
        nn.init.zeros_(self.delta.bias)
        nn.init.zeros_(self.attention.weight)
        nn.init.zeros_(self.attention.bias)

    def forward(self, query, neighbor_x, neighbor_z):
        difference = query[:, None, :]-neighbor_x
        query_features = (2*query[:, None, :]-1).expand(-1, neighbor_x.shape[1], -1)
        hidden = self.hidden(torch.cat((query_features, 2*difference, neighbor_z), dim=-1))
        distance_sq = difference.square().mean(dim=-1, keepdim=True)
        prior = -torch.log(distance_sq+1e-6)
        weights = torch.softmax(prior+0.25*torch.tanh(self.attention(hidden)), dim=1)
        # Zero heads start at an inverse-distance response interpolation.
        # Scaling by distance avoids a free discontinuous correction at an anchor.
        correction = distance_sq.sqrt()*2*torch.tanh(self.delta(hidden)/2)
        return (weights*(neighbor_z+correction)).sum(dim=1)


class _RuntimeScope:
    def __init__(self, settings, cancel_event=None):
        self.settings, self.stack = settings, None
        self.cancel_event = cancel_event

    def __enter__(self):
        if self.settings["device"] != "cpu" or self.settings["cpu_threads"] != 1:
            raise ValueError("N02 v1 freezes a uniform single-thread CPU runtime")
        while not _NUMERICAL_LOCK.acquire(timeout=0.05):
            check_cancelled(self.cancel_event)
        self.stack = ExitStack()
        self.stack.callback(_NUMERICAL_LOCK.release)
        self.stack.callback(torch.set_num_threads, torch.get_num_threads())
        try:
            check_cancelled(self.cancel_event)
            torch.set_num_threads(1)
            self.stack.enter_context(threadpool_limits(limits=1))
            self.stack.enter_context(torch.random.fork_rng(devices=[]))
        except BaseException:
            self.stack.close()
            raise
        return self

    def __exit__(self, exc_type, exc, traceback):
        return self.stack.__exit__(exc_type, exc, traceback)


def _runtime(settings, cancel_event=None):
    return _RuntimeScope(settings, cancel_event)


def _train_member(x, z, indices, weights, settings, *, steps, seed, cancel_event=None):
    # Seed the CPU generator only; torch.manual_seed also mutates accelerator RNGs.
    torch.random.default_generator.manual_seed(seed)
    model = NeighborDeltaNet(x.shape[1], z.shape[1], settings["hidden_width"])
    optimizer = torch.optim.AdamW(model.parameters(), lr=settings["learning_rate"],
                                  weight_decay=settings["weight_decay"])
    x_tensor, z_tensor = torch.tensor(x, dtype=torch.float32), torch.tensor(z, dtype=torch.float32)
    ids_tensor = torch.tensor(indices, dtype=torch.long)
    weight_tensor = torch.tensor(weights, dtype=torch.float32)
    rng = np.random.default_rng(seed)
    last_loss = None
    for _step in range(steps):
        check_cancelled(cancel_event)
        batch = torch.as_tensor(rng.choice(len(x), size=min(settings["batch_size"], len(x)), replace=False))
        neighbor_ids = ids_tensor[batch]
        estimate = model(x_tensor[batch], x_tensor[neighbor_ids], z_tensor[neighbor_ids])
        loss = (F.smooth_l1_loss(estimate, z_tensor[batch], reduction="none")*weight_tensor).sum(dim=1).mean()
        if not torch.isfinite(loss):
            raise FloatingPointError("N02 neural training became nonfinite")
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), settings["gradient_clip"])
        optimizer.step()
        last_loss = float(loss.detach())
    model.eval()
    return model, last_loss


def _predict_latent(model, queries, context_x, context_z, neighbors):
    with torch.no_grad():
        output = model(torch.tensor(queries, dtype=torch.float32),
            torch.tensor(context_x[neighbors], dtype=torch.float32),
            torch.tensor(context_z[neighbors], dtype=torch.float32))
    return output.numpy().astype(np.float64)


class RetrievalResponseModel:
    def __init__(self, codec, x, z, members, settings, diagnostics):
        self.codec, self.schema = codec, codec.schema
        self.x, self.z = np.array(x, copy=True), np.array(z, copy=True)
        self.x.setflags(write=False)
        self.z.setflags(write=False)
        self.index = NeighborIndex(self.x, settings["neighbors"])
        self.members, self.settings, self.diagnostics = tuple(members), dict(settings), diagnostics

    def predict(self, x):
        queries = np.asarray(x, dtype=np.float64)
        if queries.ndim != 2 or queries.shape[1] != self.x.shape[1]:
            raise ValueError("N02 query parameter width differs from its fitted context")
        if not np.all(np.isfinite(queries)) or np.any(queries < 0) or np.any(queries > 1):
            raise ValueError("N02 requires finite normalized parameters in [0, 1]")
        if len(queries) == 0:
            return (), 0
        samples, collapsed = [], 0
        with _runtime(self.settings):
            for start in range(0, len(queries), self.settings["prediction_chunk"]):
                block = queries[start:start+self.settings["prediction_chunk"]]
                neighbors = self.index.query(block)
                latent = np.zeros((len(block), self.z.shape[1]), dtype=np.float64)
                for member in self.members:
                    latent += _predict_latent(member, block, self.x, self.z, neighbors)
                latent /= len(self.members)
                decoded, count = self.codec.decode(latent)
                samples.extend(decoded)
                collapsed += count
        return tuple(samples), collapsed


def fit_model(data, ordering, *, settings, cancel_event=None):
    """Fit the caller-owned prior rows, without consulting objective costs."""
    started = time.perf_counter()
    settings = settings.semantic_parameters()
    check_cancelled(cancel_event)
    if not 1 <= settings["members"] <= 3 or not 1 <= settings["neighbors"] <= 8:
        raise ValueError("N02 permits at most three members and eight neighbors")
    if settings["steps"] < 1 or settings["validation_steps"] < 1:
        raise ValueError("N02 requires positive final and validation training steps")
    order = tuple(int(index) for index in ordering)
    if len(set(order)) != len(order) or len(order) < settings["minimum_training_samples"]:
        raise ValueError("N02 needs unique, sufficient supplied training rows")
    if any(index < 0 or index >= len(data.row_ids) or not data.valid_mask[index] for index in order):
        raise ValueError("N02 ordering contains an invalid supplied row")
    # Costs have no role in representation, retrieval, neural loss, or prediction.
    x = np.asarray([data.normalized_variables[index] for index in order], dtype=np.float64)
    samples = tuple(data.raw_data[index] for index in order)
    row_ids = tuple(data.row_ids[index] for index in order)
    rng = np.random.default_rng(settings["random_seed"])
    permutation = rng.permutation(len(x))
    validation_count = max(1, min(len(x)-2, int(len(x)*settings["validation_fraction"])))
    validation_ids = np.sort(permutation[:validation_count])
    training_ids = np.sort(permutation[validation_count:])
    timings = {}
    with _runtime(settings, cancel_event):
        begin = time.perf_counter()
        context_samples = tuple(samples[index] for index in training_ids)
        probe_codec, context_z = ResponseCodec.fit(context_samples, settings, cancel_event)
        validation_z = probe_codec.encode(tuple(samples[index] for index in validation_ids))
        context_x, validation_x = x[training_ids], x[validation_ids]
        probe_index = NeighborIndex(context_x, settings["neighbors"])
        training_neighbors = probe_index.query(context_x, self_positions=np.arange(len(context_x)))
        validation_neighbors = probe_index.query(validation_x)
        timings["validation_codec_and_neighbors"] = time.perf_counter()-begin
        begin = time.perf_counter()
        probe, _ = _train_member(context_x, context_z, training_neighbors, probe_codec.weights,
            settings, steps=settings["validation_steps"], seed=settings["random_seed"]+9000, cancel_event=cancel_event)
        validation_prediction = _predict_latent(probe, validation_x, context_x, context_z, validation_neighbors)
        validation_mse = float(np.mean(np.sum((validation_prediction-validation_z)**2*probe_codec.weights, axis=1)))
        timings["validation_network"] = time.perf_counter()-begin
        # Validation is diagnostic only. Its outcome never chooses final settings,
        # stopping, members, rows, or checkpoints. Final fitting starts afresh.
        del probe, probe_codec, context_samples, context_z, validation_z, probe_index
        begin = time.perf_counter()
        codec, z = ResponseCodec.fit(samples, settings, cancel_event)
        index = NeighborIndex(x, settings["neighbors"])
        neighbors = index.query(x, self_positions=np.arange(len(x)))
        timings["final_codec_and_neighbors"] = time.perf_counter()-begin
        members, losses = [], []
        begin = time.perf_counter()
        for member_index in range(settings["members"]):
            member, loss = _train_member(x, z, neighbors, codec.weights, settings,
                steps=settings["steps"], seed=settings["random_seed"]+member_index, cancel_event=cancel_event)
            members.append(member)
            losses.append(loss)
        timings["final_networks"] = time.perf_counter()-begin
    settings_hash = hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()
    diagnostics = {
        "model": settings["variant"], "settings": settings, "settings_sha256": settings_hash,
        "training_rows": len(x), "training_row_ids": list(row_ids), "context_row_ids": list(row_ids),
        "training_data_digest": data.content_digest, "representation_width": codec.width,
        "field_ranks": [field.rank for field in codec.fields], "members": len(members),
        "field_selectors": [list(field.field.selector) for field in codec.fields],
        "neighbors": neighbors.shape[1], "self_retrieval_excluded_rows": len(x),
        "validation_context_row_ids": [row_ids[index] for index in training_ids],
        "validation_query_row_ids": [row_ids[index] for index in validation_ids],
        "validation_codec_fit_row_ids": [row_ids[index] for index in training_ids],
        "validation_context_is_train_only": True, "validation_latent_weighted_mse": validation_mse,
        "validation_used_for_selection": False, "final_training_losses": losses,
        "total_gradient_steps": settings["validation_steps"]+settings["members"]*settings["steps"],
        "phase_wall_sec": timings, "model_fit_wall_sec": time.perf_counter()-started,
        "cost_use": "none", "prediction_rule": "mean corrected latent, then complete rawData decode",
    }
    return RetrievalResponseModel(codec, x, z, members, settings, diagnostics)
