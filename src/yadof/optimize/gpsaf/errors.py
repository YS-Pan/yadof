"""Explicit run-owned, prequential GPSAF prediction-error state."""
from __future__ import annotations

from collections import deque
import math
from typing import Protocol, runtime_checkable


@runtime_checkable
class GPSAFErrorEstimator(Protocol):
    def estimate_initial_error(self, context, training_data, *, folds: int = 5): ...


class GPSAFErrorState:
    """Average the last five per-batch maximum absolute held-out errors.

    An optional initial estimate can come from five-fold cross-validation, or
    exact zeros for a real-simulation oracle. Without an initial estimate beta
    waits for the first predicted-then-real batch; alpha still collects it.
    No model is retrained here, and no prediction is persisted as real evidence.
    """

    def __init__(self, initial_error=None):
        self._initial = None if initial_error is None else self._validate(initial_error)
        self._batches = deque(() if self._initial is None else (self._initial,), maxlen=5)
        self._interpretation = None
        self.observed_rows = 0

    @staticmethod
    def _validate(error):
        values = tuple(float(value) for value in error)
        if not values or any(not math.isfinite(value) or value < 0 for value in values):
            raise ValueError("GPSAF errors must have positive width and finite nonnegative values")
        return values

    def for_interpretation(self, fingerprint):
        if self._interpretation is not None and self._interpretation != fingerprint:
            self._batches.clear()
            self.observed_rows = 0
            self._initial = None
        self._interpretation = fingerprint
        return self.error

    def initialize(self, error):
        if self.error is not None:
            raise ValueError("GPSAF prediction error is already initialized")
        self._initial = self._validate(error)
        self._batches.append(self._initial)

    @property
    def error(self):
        if not self._batches:
            return self._initial
        return tuple(math.fsum(row[j] for row in self._batches) / len(self._batches)
                     for j in range(len(self._batches[0])))

    def observe(self, selected, actual_costs):
        """Call after real evaluation, using predictions captured before training."""
        predicted = selected.predicted_costs
        if len(actual_costs) != len(selected.population):
            raise ValueError("real GPSAF outcomes must align with the selected population")
        if not predicted:
            return
        if len(predicted) != len(actual_costs):
            raise ValueError("GPSAF predictions and outcomes must align")
        differences = []
        for prediction, actual in zip(predicted, actual_costs):
            if prediction is None:
                continue
            if len(prediction) != len(actual):
                raise ValueError("GPSAF predicted and actual objective widths differ")
            if all(math.isfinite(float(v)) for v in (*prediction, *actual)):
                differences.append(tuple(abs(p - float(a)) for p, a in zip(prediction, actual)))
        if differences:
            error = tuple(max(row[j] for row in differences) for j in range(len(differences[0])))
            if self.error is not None and len(error) != len(self.error):
                raise ValueError("GPSAF error objective width changed")
            self._batches.append(error)
            self.observed_rows += len(differences)

    def diagnostics(self):
        return {
            "gpsaf_prediction_error": self.error,
            "gpsaf_error_statistic": "mean-of-last-five-batch-maximum-absolute-errors",
            "gpsaf_error_batches": len(self._batches),
            "gpsaf_error_observed_rows": self.observed_rows,
            "gpsaf_error_initialization": "provided" if self._initial is not None else "prequential-warmup",
        }


def initialize_gpsaf_error(surrogate, context, training_data, error_state):
    """Explicit optional bootstrap, outside the read-only selection operation."""
    error_state.for_interpretation(context.snapshot.interpretation_fingerprint)
    if error_state.error is None and isinstance(surrogate, GPSAFErrorEstimator):
        initial = surrogate.estimate_initial_error(context, training_data, folds=5)
        if initial is not None:
            error_state.initialize(initial)
    return error_state.diagnostics()
