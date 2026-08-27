"""Frozen named rawData templates used by submit-side derived predictions."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from types import MappingProxyType
from typing import Mapping, Sequence

import numpy as np

from .rawdata_contract import (
    NamedRawDataItem,
    RawDataContractError,
    parse_metadata,
    resolve_main_array_key,
    validate_named_rawdata_items,
)


RawDataFieldSelector = tuple[str, str]


class RawDataTemplateError(RawDataContractError):
    """A named sample does not match one frozen rawData template."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_type="schema_incompatible")


@dataclass(frozen=True, slots=True)
class StructuredRawDataSample:
    """One complete in-memory rawData sample with direct ``.npz`` names."""

    items: tuple[NamedRawDataItem, ...]

    @classmethod
    def from_items(
        cls,
        items: Mapping[str, Mapping[str, object]]
        | Sequence[NamedRawDataItem],
    ) -> "StructuredRawDataSample":
        validated = _validated_named_items(items)
        ordered = tuple(
            sorted(
                validated,
                key=lambda item: (
                    item.filename.casefold(),
                    item.filename,
                    resolve_main_array_key(item.payload),
                ),
            )
        )
        return cls(
            tuple(
                NamedRawDataItem(
                    item.filename,
                    _freeze_mapping(item.payload),
                )
                for item in ordered
            )
        )

    @property
    def field_selectors(self) -> tuple[RawDataFieldSelector, ...]:
        return tuple(
            (item.filename, resolve_main_array_key(item.payload))
            for item in self.items
        )

    def cost_items(self) -> tuple[Mapping[str, object], ...]:
        """Return complete payloads in canonical selector order for cost code."""

        return tuple(item.payload for item in self.items)

    def as_mapping(self) -> dict[str, dict[str, object]]:
        """Return an owned mutable copy keyed by exact ``.npz`` basename."""

        return {
            item.filename: _thaw_mapping(item.payload)
            for item in self.items
        }


RawDataSampleLike = (
    StructuredRawDataSample
    | Mapping[str, Mapping[str, object]]
    | Sequence[NamedRawDataItem]
)


@dataclass(frozen=True, slots=True)
class RawDataFieldTemplate:
    """One frozen named rawData item and its resolved main-array identity."""

    filename: str
    main_key: str
    payload: Mapping[str, object]
    _descriptor: Mapping[str, object] = field(repr=False)

    @property
    def selector(self) -> RawDataFieldSelector:
        return (self.filename, self.main_key)

    @property
    def main_shape(self) -> tuple[int, ...]:
        return tuple(int(value) for value in np.asarray(self.payload[self.main_key]).shape)

    @property
    def main_dtype(self) -> str:
        return str(np.asarray(self.payload[self.main_key]).dtype)


@dataclass(frozen=True, slots=True)
class RawDataSchemaTemplate:
    """Exact fixed-schema template for structured posterior rawData samples.

    Field identity is the pair ``(NPZ basename including .npz, resolved main
    array key)``.  The schema signature fixes that selector set, main-array shape
    and dtype representation, and every non-main template value such as axes,
    units, and metadata.  Main-array values themselves are deliberately excluded.
    """

    fields: tuple[RawDataFieldTemplate, ...]
    signature: str = field(init=False)

    def __post_init__(self) -> None:
        fields = tuple(self.fields)
        if not fields:
            raise RawDataTemplateError("rawData schema template must contain fields")
        selectors = tuple(item.selector for item in fields)
        if selectors != tuple(sorted(selectors, key=_selector_sort_key)):
            raise RawDataTemplateError(
                "rawData schema fields must use canonical selector order"
            )
        if len(selectors) != len(set(selectors)):
            raise RawDataTemplateError("rawData field selectors must be unique")
        object.__setattr__(self, "fields", fields)
        object.__setattr__(
            self,
            "signature",
            _hash_json(
                {
                    "contract": "yadof.rawdata-schema-template",
                    "contract_version": 1,
                    "fields": [dict(item._descriptor) for item in fields],
                }
            ),
        )

    @classmethod
    def from_items(
        cls,
        items: Mapping[str, Mapping[str, object]]
        | Sequence[NamedRawDataItem],
    ) -> "RawDataSchemaTemplate":
        sample = StructuredRawDataSample.from_items(items)
        fields = []
        for item in sample.items:
            main_key = resolve_main_array_key(item.payload)
            descriptor = _field_descriptor(
                item.filename,
                main_key,
                item.payload,
            )
            fields.append(
                RawDataFieldTemplate(
                    filename=item.filename,
                    main_key=main_key,
                    payload=item.payload,
                    _descriptor=MappingProxyType(descriptor),
                )
            )
        return cls(tuple(fields))

    @property
    def field_selectors(self) -> tuple[RawDataFieldSelector, ...]:
        return tuple(field.selector for field in self.fields)

    def reconstruct(
        self,
        main_arrays: Mapping[RawDataFieldSelector, object],
    ) -> StructuredRawDataSample:
        """Rebuild one complete sample from exact selector-keyed main arrays."""

        provided = set(main_arrays)
        expected = set(self.field_selectors)
        if provided != expected:
            missing = tuple(sorted(expected - provided, key=_selector_sort_key))
            extra = tuple(sorted(provided - expected, key=_selector_sort_key))
            raise RawDataTemplateError(
                "rawData selector set does not match template; "
                f"missing={missing!r}, extra={extra!r}"
            )

        rebuilt: dict[str, dict[str, object]] = {}
        for field_template in self.fields:
            payload = _thaw_mapping(field_template.payload)
            predicted = np.asarray(main_arrays[field_template.selector])
            template_main = np.asarray(
                field_template.payload[field_template.main_key]
            )
            if predicted.shape != template_main.shape:
                raise RawDataTemplateError(
                    f"rawData field {field_template.selector!r} shape mismatch: "
                    f"expected {template_main.shape}, got {predicted.shape}"
                )
            if predicted.dtype != template_main.dtype:
                raise RawDataTemplateError(
                    f"rawData field {field_template.selector!r} dtype mismatch: "
                    f"expected {template_main.dtype}, got {predicted.dtype}"
                )
            payload[field_template.main_key] = predicted.copy()
            rebuilt[field_template.filename] = payload
        return self.validate_sample(rebuilt)

    def validate_sample(
        self,
        sample: RawDataSampleLike,
    ) -> StructuredRawDataSample:
        """Validate one complete sample against the exact frozen template."""

        structured = StructuredRawDataSample.from_items(
            sample.items if isinstance(sample, StructuredRawDataSample) else sample
        )
        actual = {selector: item for selector, item in zip(
            structured.field_selectors,
            structured.items,
        )}
        expected = set(self.field_selectors)
        if set(actual) != expected:
            missing = tuple(sorted(expected - set(actual), key=_selector_sort_key))
            extra = tuple(sorted(set(actual) - expected, key=_selector_sort_key))
            raise RawDataTemplateError(
                "rawData selector set does not match template; "
                f"missing={missing!r}, extra={extra!r}"
            )

        ordered_items = []
        for field_template in self.fields:
            item = actual[field_template.selector]
            descriptor = _field_descriptor(
                item.filename,
                field_template.main_key,
                item.payload,
            )
            if descriptor != dict(field_template._descriptor):
                raise RawDataTemplateError(
                    f"rawData field {field_template.selector!r} does not match "
                    "the frozen shape/dtype/axis/metadata template"
                )
            ordered_items.append(item)
        return StructuredRawDataSample(tuple(ordered_items))


def _validated_named_items(
    items: Mapping[str, Mapping[str, object]] | Sequence[NamedRawDataItem],
) -> tuple[NamedRawDataItem, ...]:
    if isinstance(items, Mapping):
        return validate_named_rawdata_items(items)
    selected = tuple(items)
    if not all(isinstance(item, NamedRawDataItem) for item in selected):
        raise RawDataTemplateError(
            "structured rawData must be a named mapping or NamedRawDataItem sequence"
        )
    mapping: dict[str, Mapping[str, object]] = {}
    folded: set[str] = set()
    for item in selected:
        key = item.filename.casefold()
        if key in folded:
            raise RawDataTemplateError(
                f"rawData names must be unique ignoring case: {item.filename!r}"
            )
        folded.add(key)
        mapping[item.filename] = item.payload
    return validate_named_rawdata_items(mapping)


def _selector_sort_key(selector: RawDataFieldSelector) -> tuple[str, str, str]:
    return (selector[0].casefold(), selector[0], selector[1])


def _field_descriptor(
    filename: str,
    main_key: str,
    payload: Mapping[str, object],
) -> dict[str, object]:
    resolved = resolve_main_array_key(payload)
    if resolved != main_key:
        raise RawDataTemplateError(
            f"rawData field {(filename, resolved)!r} does not match expected main "
            f"key {main_key!r}"
        )
    keys = tuple(sorted(str(key) for key in payload))
    if len(keys) != len(payload) or any(key not in payload for key in keys):
        raise RawDataTemplateError("rawData payload keys must be unique strings")
    main = np.asarray(payload[main_key])
    if (
        main.dtype.hasobject
        or main.dtype.fields is not None
        or not np.issubdtype(main.dtype, np.number)
    ):
        raise RawDataTemplateError(
            f"rawData field {(filename, main_key)!r} must use an unstructured "
            "numeric main array"
        )
    return {
        "selector": [filename, main_key],
        "keys": list(keys),
        "main": {
            "dtype": main.dtype.str,
            "shape": list(main.shape),
        },
        "template_values": {
            key: (
                {"metadata": _json_value(parse_metadata(payload[key]))}
                if key == "metadata"
                else _value_descriptor(payload[key])
            )
            for key in keys
            if key != main_key
        },
    }


def _value_descriptor(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            "mapping": {
                str(key): _value_descriptor(item)
                for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            }
        }
    if isinstance(value, (list, tuple)):
        return {"sequence": [_value_descriptor(item) for item in value]}
    array = np.asarray(value)
    if array.dtype.hasobject:
        raise RawDataTemplateError("rawData template values cannot use object dtype")
    contiguous = np.ascontiguousarray(array)
    return {
        "array": {
            "dtype": contiguous.dtype.str,
            "shape": list(contiguous.shape),
            "sha256": hashlib.sha256(contiguous.tobytes()).hexdigest(),
        }
    }


def _freeze_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    if any(not isinstance(key, str) for key in value):
        raise RawDataTemplateError("rawData payload keys must be strings")
    return MappingProxyType(
        {key: _freeze_value(item) for key, item in value.items()}
    )


def _freeze_value(value: object) -> object:
    if isinstance(value, np.ndarray):
        copied = value.copy()
        copied.setflags(write=False)
        return copied
    if isinstance(value, Mapping):
        return _freeze_mapping(value)
    if isinstance(value, list):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, np.generic):
        copied = np.asarray(value).copy()
        copied.setflags(write=False)
        return copied
    return value


def _thaw_mapping(value: Mapping[str, object]) -> dict[str, object]:
    return {str(key): _thaw_value(item) for key, item in value.items()}


def _thaw_value(value: object) -> object:
    if isinstance(value, np.ndarray):
        return value.copy()
    if isinstance(value, Mapping):
        return _thaw_mapping(value)
    if isinstance(value, tuple):
        return tuple(_thaw_value(item) for item in value)
    return value


def _hash_json(value: object) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RawDataTemplateError(
            "rawData schema template must contain JSON-safe finite metadata"
        ) from exc
    return hashlib.sha256(encoded).hexdigest()


def _json_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): _json_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, np.ndarray):
        if value.shape == ():
            return _json_value(value.item())
        return [_json_value(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _json_value(value.item())
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise RawDataTemplateError(
        f"rawData metadata contains non-JSON value {type(value).__name__}"
    )


__all__ = [
    "RawDataFieldSelector",
    "RawDataFieldTemplate",
    "RawDataSampleLike",
    "RawDataSchemaTemplate",
    "RawDataTemplateError",
    "StructuredRawDataSample",
]
