from dataclasses import replace
import threading

import numpy as np
import pytest

from yadof.surrogate import amplitude_gp
from yadof.surrogate.amplitude_gp import model
from test_amplitude_gp import _data


def test_parallel_fields_preserve_complete_predictions_and_inputs():
    data = _data(20)
    settings = amplitude_gp(minimum_training_samples=2, gp_max_rows=12,
                             shape_rank=4, optimizer_iterations=10).settings
    before = data.content_digest
    args = (data, tuple(range(data.sample_count)), np.asarray(data.normalized_variables))
    serial = model.fit_amplitude_model(*args, settings=settings)
    parallel = model.fit_amplitude_model(*args, settings=replace(settings, field_workers=3))
    x = np.linspace(0.025, 0.975, 13)[:, None]
    expected, actual = serial.predict(x), parallel.predict(x)
    assert expected[1] == actual[1]
    for a, b in zip(expected[0], actual[0], strict=True):
        assert a.field_selectors == b.field_selectors
        for left, right in zip(a.items, b.items, strict=True):
            for key, value in left.payload.items():
                if isinstance(value, np.ndarray):
                    np.testing.assert_array_equal(value, right.payload[key])
                else:
                    assert value == right.payload[key]
    assert data.content_digest == before
    assert parallel.diagnostics["field_workers"] == 3
    assert serial.diagnostics["gp_row_ids"] == parallel.diagnostics["gp_row_ids"]
    assert [r["selector"] for r in serial.diagnostics["fields"]] == [r["selector"] for r in parallel.diagnostics["fields"]]
    assert amplitude_gp(field_workers=1).semantic_identity(None, None) == amplitude_gp(field_workers=3).semantic_identity(None, None)


def test_field_failure_cancels_and_joins_other_workers(monkeypatch):
    data = _data()
    barrier = threading.Barrier(2)
    lock = threading.Lock()
    entered, exited = [], []
    def fit(*args, cancel_event=None, **kwargs):
        with lock:
            index = len(entered)
            entered.append(index)
        try:
            if index < 2:
                barrier.wait(timeout=5)
            if index == 0:
                raise RuntimeError("field failed")
            for _ in range(500):
                model.check_cancelled(cancel_event)
                threading.Event().wait(0.01)
            raise AssertionError("peer fitting did not observe cancellation")
        finally:
            exited.append(index)
    monkeypatch.setattr(model, "fit_field", fit)
    with pytest.raises(RuntimeError, match="field failed"):
        model.fit_amplitude_model(data, tuple(range(data.sample_count)),
            np.asarray(data.normalized_variables), settings=amplitude_gp(field_workers=2).settings)
    assert len(entered) >= 2 and sorted(exited) == sorted(entered)
