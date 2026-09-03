"""Fast test_com evaluator retaining the antenna-like rawData fields."""

from __future__ import annotations

import json

import numpy as np

from test_com import evaluate_raw_data


def _evaluate_rawdata(parameters, context):
    del context
    blocks = evaluate_raw_data(parameters, profile="hfss_like")
    payloads: dict[str, dict[str, object]] = {}
    for name, block in blocks.items():
        payload = {
            str(key): np.asarray(value).copy()
            for key, value in dict(block["arrays"]).items()
        }
        payload["metadata"] = np.asarray(
            json.dumps(dict(block["metadata"]), ensure_ascii=True, sort_keys=True)
        )
        payloads[f"{name}.npz"] = payload
    return payloads, {"simulator": "test_com", "profile": "hfss_like"}



YADOF_FAST_API = "yadof.fast.session/v1"


class _EvaluationSession:
    def evaluate_rawdata(self, parameters, context):
        return _evaluate_rawdata(parameters, context)

    def close(self):
        pass


def create_evaluation_session(context):
    return _EvaluationSession()
