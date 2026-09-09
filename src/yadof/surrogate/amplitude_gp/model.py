"""Field-wise amplitude and shape GP mathematics, independent of workspace IO."""
from __future__ import annotations

import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import nullcontext
import threading
import numpy as np
from scipy.optimize import fmin_l_bfgs_b
from sklearn.decomposition import PCA
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel
from threadpoolctl import threadpool_limits
from ...job_template.rawdata_template import RawDataSchemaTemplate
from ..training import TrainingCancelledError
from .settings import DEFAULT_AMPLITUDE_GP_SETTINGS


def check_cancelled(cancel_event):
    if cancel_event is not None and cancel_event.is_set():
        raise TrainingCancelledError("amplitude_gp training cancelled")


def subset(x, y, limit, elite_fraction=0.5):
    if len(x) <= limit:
        return np.arange(len(x))
    elite_count = max(1, min(limit - 1, int(limit * elite_fraction)))
    elite = np.argsort(np.mean(y, axis=1), kind="stable")[:elite_count]
    available = np.ones(len(x), dtype=bool)
    available[elite] = False
    candidates = np.flatnonzero(available)
    selected = list(elite)
    nearest = np.min(np.sum((x[candidates, None, :]-x[elite][None, :, :])**2, axis=2), axis=1)
    while len(selected) < limit:
        pos = int(np.argmax(nearest))
        chosen = int(candidates[pos])
        selected.append(chosen)
        nearest = np.minimum(nearest, np.sum((x[candidates]-x[chosen])**2, axis=1))
        nearest[pos] = -1.
    return np.asarray(sorted(selected), dtype=np.int64)


def make_kernel(width, settings):
    return ConstantKernel(settings.kernel_amplitude, settings.kernel_amplitude_bounds)*Matern(
        np.full(width, settings.length_scale), settings.length_scale_bounds,
        nu=settings.matern_nu) + WhiteKernel(settings.noise_level, settings.noise_level_bounds)


class GaussianMean:
    """Fitted GPR mean stored as numeric arrays, without executable pickle."""

    def __init__(self, kernel, x_train, alpha, mean, std):
        self.kernel = kernel
        self.x_train = x_train
        self.alpha = alpha
        self.mean = mean
        self.std = std

    def predict(self, x):
        values = self.kernel(x, self.x_train) @ self.alpha
        values = self.std * values + self.mean
        if values.ndim > 1 and values.shape[1] == 1:
            values = np.squeeze(values, axis=1)
        return values


class ShapeCodec:
    """PCA inverse transform; whitening is never used by this component."""

    def __init__(self, components, mean):
        self.components = components
        self.mean = mean

    def inverse_transform(self, values):
        return values @ self.components + self.mean


def split_amplitude(values, *, out=None):
    low = np.min(values, axis=1, keepdims=True)
    span = np.max(values, axis=1, keepdims=True)-low
    shape = np.subtract(values, low, out=out)
    np.divide(shape, span, out=shape, where=span > 0)
    return low, span, shape


def restore_amplitude(shape, low, span):
    _, decoded_span, normalized = split_amplitude(shape)
    collapsed = int(sum(((decoded_span <= 0) & (span > 0)).ravel()))
    return low+span*normalized, collapsed


class ResponseMap:
    def __init__(self, model, constant, scale, diagnostics):
        self.model = model
        self.constant = constant
        self.scale = scale
        self.diagnostics = diagnostics

    def predict(self, x):
        if self.model is None:
            return np.tile(self.constant, (len(x), 1))
        values = np.asarray(self.model.predict(x))*self.scale
        return values[:, None] if values.ndim == 1 else values


def fit_map(x, target, rows, *, scalar, settings, cancel_event=None, capture_warnings=True):
    check_cancelled(cancel_event)
    target = np.asarray(target)
    if np.max(np.ptp(target, axis=0)) <= settings.constant_tolerance:
        return ResponseMap(None, target.mean(axis=0), 1., {"constant": True})
    scale = 1. if scalar else max(float(np.sqrt(np.mean(target**2))), settings.numerical_floor)
    kernel = make_kernel(x.shape[1], settings)
    def optimizer(fn, theta, bounds):
        def objective(values):
            check_cancelled(cancel_event)
            return fn(values)
        result, value, _ = fmin_l_bfgs_b(objective, theta, bounds=bounds,
            maxiter=settings.optimizer_iterations, factr=settings.optimizer_factr)
        return result, value
    # Python warning filters are process-global on supported runtimes. Parallel
    # fields emit normal stderr warnings instead of racing nested catch contexts.
    with warnings.catch_warnings(record=True) if capture_warnings else nullcontext(()) as caught:
        if capture_warnings:
            warnings.simplefilter("always")
        model = GaussianProcessRegressor(kernel=kernel, alpha=settings.alpha, normalize_y=scalar,
            optimizer=optimizer, random_state=settings.random_seed).fit(x[rows], target[rows]/scale)
    diagnostics = {"kernel": str(model.kernel_),
        "warnings": list(dict.fromkeys(str(w.message) for w in caught))[:20]}
    if not capture_warnings:
        diagnostics["warning_capture"] = "process-stderr"
    check_cancelled(cancel_event)
    mean = GaussianMean(model.kernel_, model.X_train_, model.alpha_,
                        model._y_train_mean, model._y_train_std)
    return ResponseMap(mean, None, scale, diagnostics)


class FieldModel:
    def __init__(self, minimum, low_center, low_scale, span, shape, constant_shape, codec, diagnostics):
        self.minimum = minimum
        self.low_center = low_center
        self.low_scale = low_scale
        self.span = span
        self.shape = shape
        self.constant_shape = constant_shape
        self.codec = codec
        self.diagnostics = diagnostics

    def predict(self, x):
        low = self.low_center+self.low_scale*np.sinh(self.minimum.predict(x))
        span = np.zeros((len(x), 1)) if self.span is None else np.exp(self.span.predict(x))
        shape = (np.tile(self.constant_shape, (len(x), 1)) if self.codec is None
                 else self.codec.inverse_transform(self.shape.predict(x)))
        return restore_amplitude(shape, low, span)


def fit_field(x, target, rows, *, settings=DEFAULT_AMPLITUDE_GP_SETTINGS, cancel_event=None,
              capture_warnings=True):
    """Consume the caller-owned writable float64 target as the shape/PCA buffer."""
    low, span, shape = split_amplitude(target, out=target)
    center = float(np.median(low))
    scale = max(float(np.quantile(np.abs(low-center), settings.minimum_scale_quantile)),
                settings.minimum_scale_std_fraction*float(np.std(low)), settings.numerical_floor)
    low_z = np.arcsinh((low-center)/scale)
    kwargs = {"settings": settings, "cancel_event": cancel_event, "capture_warnings": capture_warnings}
    minimum = fit_map(x, low_z, rows, scalar=True, **kwargs)
    if np.max(span) == 0:
        span_map = None
        span_info = {"constant_zero": True}
    else:
        floor = max(float(np.median(span[span > 0]))*settings.span_floor_relative, settings.numerical_floor)
        span_map = fit_map(x, np.log(np.maximum(span, floor)), rows, scalar=True, **kwargs)
        span_info = {**span_map.diagnostics, "log_floor": floor}
    rank = min(settings.shape_rank, len(x)-1, target.shape[1])
    if target.shape[1] == 1 or np.max(np.ptp(shape, axis=0)) <= settings.constant_tolerance:
        codec = None
        shape_map = None
        constant_shape = shape.mean(axis=0)
        shape_info = {"constant": True}
    else:
        check_cancelled(cancel_event)
        pca = PCA(n_components=rank, svd_solver="randomized", random_state=settings.random_seed, copy=False)
        coefficients = pca.fit_transform(shape)
        codec = ShapeCodec(pca.components_, pca.mean_)
        shape_map = fit_map(x, coefficients, rows, scalar=False, **kwargs)
        constant_shape = None
        shape_info = shape_map.diagnostics
    diagnostics = {"minimum": minimum.diagnostics, "span": span_info,
        "shape": shape_info, "rank": rank}
    return FieldModel(minimum, center, scale, span_map, shape_map, constant_shape, codec, diagnostics)


class AmplitudeModel:
    def __init__(self, schema, fields, diagnostics):
        self.schema = schema
        self.fields = fields
        self.diagnostics = diagnostics

    def predict(self, x):
        with threadpool_limits(limits=1), np.errstate(over="ignore", invalid="ignore"):
            predicted = [field.predict(x) for field in self.fields]
        samples = []
        for i in range(len(x)):
            if any(not np.all(np.isfinite(values[i])) for values, _ in predicted):
                samples.append(None)
                continue
            if any(np.dtype(field.main_dtype).kind in "iu" and (
                np.any(values[i] < np.iinfo(field.main_dtype).min)
                or np.any(values[i] > np.iinfo(field.main_dtype).max))
                for field, (values, _) in zip(self.schema.fields, predicted, strict=True)):
                samples.append(None)
                continue
            arrays = {field.selector: values[i].reshape(field.main_shape).astype(field.main_dtype)
                      for field, (values, _) in zip(self.schema.fields, predicted, strict=True)}
            # An overflow is invalid, never replaced with another design's rawData.
            samples.append(self.schema.reconstruct(arrays)
                           if all(np.all(np.isfinite(value)) for value in arrays.values()) else None)
        return tuple(samples), sum(collapsed for _, collapsed in predicted)


def fit_amplitude_model(data, ordering, costs, *, settings=DEFAULT_AMPLITUDE_GP_SETTINGS,
                        cancel_event=None):
    start = time.perf_counter()
    check_cancelled(cancel_event)
    x = np.asarray([data.normalized_variables[i] for i in ordering], dtype=float)
    samples = tuple(data.raw_data[i] for i in ordering)
    rows = subset(x, costs, settings.gp_max_rows, settings.elite_fraction)
    schema = RawDataSchemaTemplate.from_items(samples[0])
    workers = min(settings.field_workers, len(schema.fields))
    fields, reports = [None] * len(schema.fields), [None] * len(schema.fields)
    stopped = threading.Event()
    class FitCancellation:
        def is_set(self):
            return stopped.is_set() or (cancel_event is not None and cancel_event.is_set())
    cancellation = FitCancellation()
    def fit_one(index):
        field = schema.fields[index]
        check_cancelled(cancellation)
        begin = time.perf_counter()
        target = np.empty((len(samples), int(np.prod(field.main_shape))), dtype=np.float64)
        for row, sample in zip(target, samples, strict=True):
            row[:] = np.asarray(sample.items[index].payload[field.main_key]).reshape(-1)
        model = fit_field(x, target, rows, settings=settings, cancel_event=cancellation,
                          capture_warnings=workers == 1)
        del row, target
        report = {**model.diagnostics, "selector": list(field.selector),
                  "fit_wall_sec": time.perf_counter() - begin}
        return model, report

    # One numerical-thread scope covers the complete executor lifetime; workers
    # never enter overlapping threadpoolctl contexts or copy shared rawData.
    with threadpool_limits(limits=1):
        if workers == 1:
            for index in range(len(schema.fields)):
                fields[index], reports[index] = fit_one(index)
        else:
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="amplitude-field") as executor:
                futures = {executor.submit(fit_one, index): index for index in range(len(schema.fields))}
                try:
                    for future in as_completed(futures):
                        index = futures[future]
                        fields[index], reports[index] = future.result()
                except BaseException:
                    stopped.set()
                    for future in futures:
                        future.cancel()
                    raise
    check_cancelled(cancel_event)
    diagnostics = {"gp_fit_rows": len(rows), "training_rows": len(x),
        "gp_row_ids": [data.row_ids[ordering[i]] for i in rows], "fields": reports,
        "field_workers": workers,
        "model_fit_wall_sec": time.perf_counter()-start}
    return AmplitudeModel(schema, tuple(fields), diagnostics)
