"""Portable starter session: each call recomputes complete generic rawData."""

import json
import numpy as np

YADOF_FAST_API = "yadof.fast.session/v1"


class EvaluationSession:
    def evaluate_rawdata(self, parameters, context):
        values = np.asarray(tuple(parameters.values()), dtype=float)
        if not np.all(np.isfinite(values)):
            raise ValueError("starter evaluation requires assigned finite parameter values")
        response = np.asarray(float(np.mean(values**2)), dtype=float)
        return {"response.npz": {
            "values": response,
            "metadata": json.dumps({"schema_version": 1, "rawdata_name": "response", "shape": []}, sort_keys=True),
        }}

    def close(self):
        pass


def create_evaluation_session(context):
    return EvaluationSession()
