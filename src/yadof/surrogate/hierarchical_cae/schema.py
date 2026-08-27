from __future__ import annotations

import json
from typing import Mapping, Sequence

import numpy as np

from ...job_template.rawdata_contract import NamedRawDataItem
from ...job_template.rawdata_template import (
    RawDataFieldSelector,
    RawDataSchemaTemplate,
    RawDataTemplateError,
    StructuredRawDataSample,
)
from .types import AxisEncoding, FieldLayout, FieldScaler, HierarchicalSchema


def normalize_selector(value: object) -> RawDataFieldSelector:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or len(value) != 2
    ):
        raise ValueError("field selector must be ('.npz filename', 'values|data')")
    selector = (str(value[0]), str(value[1]))
    if (
        not selector[0]
        or not selector[0].lower().endswith(".npz")
        or "/" in selector[0]
        or "\\" in selector[0]
        or selector[1] not in {"values", "data"}
    ):
        raise ValueError(
            "field selector requires a direct .npz basename and values/data key"
        )
    return selector


def normalize_groups(
    groups: Sequence[Sequence[RawDataFieldSelector]],
) -> tuple[tuple[RawDataFieldSelector, ...], ...]:
    normalized = []
    claimed: set[RawDataFieldSelector] = set()
    for raw_group in groups:
        group = tuple(sorted((normalize_selector(value) for value in raw_group)))
        if not group:
            raise ValueError("explicit rawData groups must not be empty")
        if len(group) != len(set(group)):
            raise ValueError("a rawData group must not repeat a field")
        overlap = claimed.intersection(group)
        if overlap:
            raise ValueError(
                "overlapping rawData groups are unsupported in hierarchical CAE v1: "
                f"{tuple(sorted(overlap))!r}"
            )
        claimed.update(group)
        normalized.append(group)
    return tuple(sorted(normalized))


def normalize_field_layouts(
    layouts: Mapping[RawDataFieldSelector, Mapping[str, object]] | None,
) -> dict[RawDataFieldSelector, dict[str, tuple[str, ...]]]:
    output: dict[RawDataFieldSelector, dict[str, tuple[str, ...]]] = {}
    for raw_selector, raw_layout in dict(layouts or {}).items():
        selector = normalize_selector(raw_selector)
        if not isinstance(raw_layout, Mapping):
            raise ValueError(f"field layout for {selector!r} must be a mapping")
        unknown = set(raw_layout).difference({"channel_axes", "spatial_axes"})
        if unknown:
            raise ValueError(
                f"field layout for {selector!r} has unsupported keys: "
                f"{sorted(unknown)!r}"
            )
        output[selector] = {
            "channel_axes": tuple(
                str(value) for value in raw_layout.get("channel_axes", ())
            ),
            "spatial_axes": tuple(
                str(value) for value in raw_layout.get("spatial_axes", ())
            ),
        }
    return output


def normalize_axis_encodings(
    encodings: Mapping[RawDataFieldSelector, Mapping[str, object]] | None,
) -> dict[RawDataFieldSelector, dict[str, AxisEncoding]]:
    output: dict[RawDataFieldSelector, dict[str, AxisEncoding]] = {}
    for raw_selector, per_axis in dict(encodings or {}).items():
        selector = normalize_selector(raw_selector)
        if not isinstance(per_axis, Mapping):
            raise ValueError(f"axis encodings for {selector!r} must be a mapping")
        normalized: dict[str, AxisEncoding] = {}
        for axis_name, raw in per_axis.items():
            if isinstance(raw, str):
                encoding = AxisEncoding(raw)
            elif isinstance(raw, Mapping):
                encoding = AxisEncoding(
                    kind=str(raw.get("kind", "linear")),
                    period=raw.get("period"),
                )
            elif isinstance(raw, AxisEncoding):
                encoding = raw
            else:
                raise ValueError(
                    f"axis encoding for {selector!r}/{axis_name!r} is invalid"
                )
            normalized[str(axis_name)] = encoding
        output[selector] = normalized
    return output


def _metadata(payload: Mapping[str, object]) -> dict[str, object]:
    raw = payload.get("metadata", {})
    if isinstance(raw, np.ndarray):
        if raw.size != 1:
            return {}
        raw = raw.item()
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return dict(raw) if isinstance(raw, Mapping) else {}


def _axes_for_field(
    payload: Mapping[str, object], shape: tuple[int, ...]
) -> tuple[tuple[str, ...], tuple[np.ndarray, ...]]:
    if not shape:
        return (), ()
    metadata = _metadata(payload)
    descriptors = metadata.get("axes", ())
    descriptor_rows = (
        tuple(descriptors)
        if isinstance(descriptors, Sequence)
        and not isinstance(descriptors, (str, bytes, Mapping))
        else ()
    )
    raw_names = metadata.get("axis_names", ())
    names = (
        tuple(str(value) for value in raw_names)
        if isinstance(raw_names, Sequence)
        and not isinstance(raw_names, (str, bytes))
        else ()
    )
    if not names and len(descriptor_rows) == len(shape):
        names = tuple(
            str(
                descriptor.get("name")
                or str(descriptor.get("values_key", index)).removeprefix(
                    "axis_"
                )
            )
            if isinstance(descriptor, Mapping)
            else str(descriptor)
            for index, descriptor in enumerate(descriptor_rows)
        )
    if len(names) != len(shape):
        raise ValueError(
            "rawData main-array rank requires one stable metadata axis name per axis"
        )
    if len(names) != len(set(names)) or any(not name for name in names):
        raise ValueError("rawData metadata axis names must be non-empty and unique")
    by_name: dict[str, Mapping[str, object]] = {}
    if descriptor_rows:
        for raw_descriptor in descriptor_rows:
            if (
                isinstance(raw_descriptor, Mapping)
                and raw_descriptor.get("name") is not None
            ):
                by_name[str(raw_descriptor["name"])] = raw_descriptor
    values = []
    for name, size in zip(names, shape):
        descriptor = by_name.get(name, {})
        key = descriptor.get("values_key", f"axis_{name}")
        if not isinstance(key, str) or key not in payload:
            raise ValueError(
                f"rawData axis {name!r} is missing its declared coordinate array"
            )
        array = np.asarray(payload[key])
        if array.ndim != 1 or array.size != int(size):
            raise ValueError(
                f"rawData axis {name!r} must have shape ({int(size)},), "
                f"got {array.shape}"
            )
        if not np.issubdtype(array.dtype, np.floating) or not np.all(
            np.isfinite(array)
        ):
            raise ValueError(f"rawData axis {name!r} must be finite floating data")
        values.append(np.ascontiguousarray(array.copy()))
    return names, tuple(values)


def build_schema(
    first_sample: StructuredRawDataSample,
    *,
    groups: Sequence[Sequence[RawDataFieldSelector]] = (),
    field_layouts: Mapping[RawDataFieldSelector, Mapping[str, object]] | None = None,
    axis_encodings: Mapping[RawDataFieldSelector, Mapping[str, object]] | None = None,
) -> HierarchicalSchema:
    template = RawDataSchemaTemplate.from_items(first_sample.items)
    normalized_groups = normalize_groups(groups)
    layout_config = normalize_field_layouts(field_layouts)
    encoding_config = normalize_axis_encodings(axis_encodings)
    selectors = set(template.field_selectors)
    referenced = set(layout_config) | set(encoding_config) | {
        selector for group in normalized_groups for selector in group
    }
    unknown = referenced - selectors
    if unknown:
        raise ValueError(
            "hierarchical CAE configuration references rawData fields absent "
            f"from the schema: {tuple(sorted(unknown))!r}"
        )

    layouts = []
    for field in template.fields:
        array = np.asarray(field.payload[field.main_key])
        if np.iscomplexobj(array):
            raise ValueError(
                f"hierarchical CAE v1 does not support complex main array "
                f"{field.selector!r}"
            )
        if not np.issubdtype(array.dtype, np.floating):
            raise ValueError(
                f"hierarchical CAE v1 requires floating main array "
                f"{field.selector!r}; got {array.dtype}"
            )
        if not np.all(np.isfinite(array)):
            raise ValueError(
                f"hierarchical CAE v1 requires finite main array {field.selector!r}"
            )
        shape = tuple(int(value) for value in array.shape)
        rank = len(shape)
        if rank > 3:
            raise ValueError(
                "hierarchical CAE v1 supports scalar through rank-3 fields; "
                f"{field.selector!r} has rank {rank}"
            )
        axis_names, axis_values = _axes_for_field(field.payload, shape)
        declared = layout_config.get(field.selector)
        if rank == 0:
            if declared:
                raise ValueError(f"scalar field {field.selector!r} cannot declare axes")
            codec_kind = "scalar-mlp"
            channel_axes = ()
            spatial_axes = ()
            permutation = ()
            model_channels = 1
            spatial_shape = ()
        elif rank == 1:
            if declared and (
                declared["channel_axes"]
                or declared["spatial_axes"] not in {(), axis_names}
            ):
                raise ValueError(
                    f"rank-1 field {field.selector!r} uses its sole axis as "
                    "Conv1d spatial axis"
                )
            codec_kind = "conv1d"
            channel_axes = ()
            spatial_axes = axis_names
            permutation = (0,)
            model_channels = 1
            spatial_shape = shape
        elif rank == 2:
            if declared and (
                declared["channel_axes"]
                or declared["spatial_axes"] not in {(), axis_names}
            ):
                raise ValueError(
                    f"rank-2 field {field.selector!r} uses both axes as Conv2d "
                    "spatial axes"
                )
            codec_kind = "conv2d"
            channel_axes = ()
            spatial_axes = axis_names
            permutation = (0, 1)
            model_channels = 1
            spatial_shape = shape
        else:
            if declared is None:
                raise ValueError(
                    f"rank-3 field {field.selector!r} requires explicit "
                    "field_layouts with channel_axes and exactly two spatial_axes"
                )
            channel_axes = declared["channel_axes"]
            spatial_axes = declared["spatial_axes"]
            if not channel_axes or len(spatial_axes) != 2:
                raise ValueError(
                    f"rank-3 field {field.selector!r} requires at least one "
                    "channel axis and exactly two spatial axes"
                )
            ordered_roles = channel_axes + spatial_axes
            if len(ordered_roles) != rank or set(ordered_roles) != set(axis_names):
                raise ValueError(
                    f"rank-3 layout for {field.selector!r} must cover each axis "
                    f"exactly once; axes={axis_names!r}, roles={ordered_roles!r}"
                )
            permutation = tuple(axis_names.index(name) for name in ordered_roles)
            model_channels = int(
                np.prod([shape[index] for index in permutation[:-2]])
            )
            spatial_shape = tuple(shape[index] for index in permutation[-2:])
            codec_kind = "conv2d"
        inverse = (
            tuple(int(value) for value in np.argsort(permutation))
            if permutation
            else ()
        )
        per_axis = encoding_config.get(field.selector, {})
        unknown_axes = set(per_axis).difference(axis_names)
        if unknown_axes:
            raise ValueError(
                f"axis encodings for {field.selector!r} reference unknown axes: "
                f"{tuple(sorted(unknown_axes))!r}"
            )
        encodings = tuple(
            per_axis.get(name, AxisEncoding()) for name in axis_names
        )
        layouts.append(
            FieldLayout(
                selector=field.selector,
                shape=shape,
                dtype=str(array.dtype),
                axis_names=axis_names,
                codec_kind=codec_kind,
                channel_axes=channel_axes,
                spatial_axes=spatial_axes,
                model_permutation=permutation,
                inverse_permutation=inverse,
                model_channels=model_channels,
                model_spatial_shape=spatial_shape,
                axis_values=axis_values,
                axis_encodings=encodings,
            )
        )
    return HierarchicalSchema(template, tuple(layouts), normalized_groups)


def validate_samples(
    schema: HierarchicalSchema,
    samples: Sequence[StructuredRawDataSample],
) -> tuple[StructuredRawDataSample, ...]:
    validated = []
    for row_index, sample in enumerate(samples):
        try:
            current = schema.template.validate_sample(sample)
        except RawDataTemplateError as exc:
            raise ValueError(
                f"rawData design row {row_index} is incompatible with the "
                f"frozen schema: {exc}"
            ) from exc
        for field, item in zip(schema.template.fields, current.items):
            values = np.asarray(item.payload[field.main_key])
            if np.iscomplexobj(values) or not np.issubdtype(
                values.dtype, np.floating
            ):
                raise ValueError(
                    f"rawData field {field.selector!r} changed to an unsupported dtype"
                )
            if not np.all(np.isfinite(values)):
                raise ValueError(
                    f"rawData field {field.selector!r} contains non-finite training data"
                )
        validated.append(current)
    return tuple(validated)


def field_matrices(
    schema: HierarchicalSchema,
    samples: Sequence[StructuredRawDataSample],
) -> tuple[np.ndarray, ...]:
    rows = validate_samples(schema, samples)
    matrices = []
    for field_index, field in enumerate(schema.template.fields):
        values = [
            np.asarray(row.items[field_index].payload[field.main_key]).reshape(-1)
            for row in rows
        ]
        matrices.append(
            np.ascontiguousarray(np.stack(values), dtype=np.float64)
        )
    return tuple(matrices)


def fit_scalers(
    matrices: Sequence[np.ndarray], *, scale_floor: float
) -> tuple[FieldScaler, ...]:
    scalers = []
    floor = float(scale_floor)
    for matrix in matrices:
        mean = np.mean(matrix, axis=0, dtype=np.float64)
        scale = np.std(matrix, axis=0, dtype=np.float64)
        robust_floor = max(
            floor, float(np.max(scale, initial=0.0)) * 1.0e-6
        )
        scale = np.maximum(scale, robust_floor)
        scalers.append(
            FieldScaler(
                mean=np.ascontiguousarray(mean),
                scale=np.ascontiguousarray(scale),
            )
        )
    return tuple(scalers)


def standardized_field_matrices(
    schema: HierarchicalSchema, matrices: Sequence[np.ndarray]
) -> tuple[np.ndarray, ...]:
    if not schema.scalers:
        raise ValueError("hierarchical schema has no fitted field scalers")
    return tuple(
        scaler.transform(matrix).reshape((matrix.shape[0],) + layout.shape)
        for layout, scaler, matrix in zip(
            schema.layouts, schema.scalers, matrices
        )
    )


def reconstruct_samples(
    schema: HierarchicalSchema,
    predicted_fields: Sequence[np.ndarray],
) -> tuple[StructuredRawDataSample, ...]:
    if len(predicted_fields) != len(schema.layouts):
        raise ValueError("one predicted field matrix is required per schema field")
    row_count = int(np.asarray(predicted_fields[0]).shape[0])
    if any(
        int(np.asarray(values).shape[0]) != row_count
        for values in predicted_fields
    ):
        raise ValueError(
            "predicted hierarchical CAE fields must share a row count"
        )
    output = []
    for row_index in range(row_count):
        arrays = {}
        for field, layout, scaler, scaled in zip(
            schema.template.fields,
            schema.layouts,
            schema.scalers,
            predicted_fields,
        ):
            values = scaler.inverse(
                np.asarray(scaled[row_index]).reshape(-1)
            ).reshape(layout.shape)
            dtype = np.dtype(layout.dtype)
            converted = values.astype(dtype, copy=False)
            arrays[field.selector] = (
                converted.copy()
                if layout.shape == ()
                else np.ascontiguousarray(converted)
            )
        output.append(schema.template.reconstruct(arrays))
    return tuple(output)


def named_sample_from_payloads(
    filenames: Sequence[str], payloads: Sequence[Mapping[str, object]]
) -> StructuredRawDataSample:
    if len(filenames) != len(payloads):
        raise ValueError("rawData filenames and payloads must align")
    return StructuredRawDataSample.from_items(
        tuple(
            NamedRawDataItem(str(filename), dict(payload))
            for filename, payload in zip(filenames, payloads)
        )
    )


__all__ = [
    "build_schema",
    "field_matrices",
    "fit_scalers",
    "named_sample_from_payloads",
    "normalize_axis_encodings",
    "normalize_field_layouts",
    "normalize_groups",
    "normalize_selector",
    "reconstruct_samples",
    "standardized_field_matrices",
    "validate_samples",
]
