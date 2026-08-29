"""Mode selection and dispatch for hierarchical-CAE training-data filtering."""

from __future__ import annotations

from typing import Mapping, Sequence

from ....job_template.rawdata_template import StructuredRawDataSample
from .frequency import FrequencyFilter, assess_frequency_filter, frequency_filter_from_mapping
from .types import DataFilterAssessment, uniform_data_filter_assessment


DATA_FILTER_NONE = "none"
DATA_FILTER_FREQUENCY = "frequency"
DATA_FILTER_MODES = (DATA_FILTER_NONE, DATA_FILTER_FREQUENCY)


def normalize_data_filter_mode(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("hierarchical_cae(): data_filter_mode must be a string")
    mode = value.strip().lower()
    if mode not in DATA_FILTER_MODES:
        choices = ", ".join(repr(item) for item in DATA_FILTER_MODES)
        raise ValueError(
            "hierarchical_cae(): data_filter_mode must be one of "
            f"{choices}; got {value!r}"
        )
    return mode


def resolve_data_filter(
    *,
    mode: object,
    frequency_filter: Mapping[str, object] | FrequencyFilter | None,
) -> tuple[str, FrequencyFilter | None]:
    """Validate the one mode selector and its mode-specific declaration."""

    normalized_mode = normalize_data_filter_mode(mode)
    selected_filter = frequency_filter_from_mapping(frequency_filter)
    if normalized_mode == DATA_FILTER_NONE:
        if selected_filter is not None:
            raise ValueError(
                "hierarchical_cae(): frequency_filter requires "
                "data_filter_mode='frequency'"
            )
        return normalized_mode, None
    if selected_filter is None:
        raise ValueError(
            "hierarchical_cae(): data_filter_mode='frequency' requires "
            "frequency_filter"
        )
    return normalized_mode, selected_filter


def assess_data_filter(
    *,
    mode: object,
    frequency_filter: FrequencyFilter | None,
    samples: Sequence[StructuredRawDataSample],
    record_metadata: Sequence[Mapping[str, object]] = (),
) -> DataFilterAssessment:
    """Create the immutable training view selected by ``mode``."""

    normalized_mode, selected_filter = resolve_data_filter(
        mode=mode,
        frequency_filter=frequency_filter,
    )
    if normalized_mode == DATA_FILTER_NONE:
        return uniform_data_filter_assessment(samples)
    return assess_frequency_filter(
        frequency_filter=selected_filter,
        samples=samples,
        record_metadata=record_metadata,
    )


__all__ = [
    "DATA_FILTER_MODES",
    "DATA_FILTER_NONE",
    "DATA_FILTER_FREQUENCY",
    "assess_data_filter",
    "normalize_data_filter_mode",
    "resolve_data_filter",
]
