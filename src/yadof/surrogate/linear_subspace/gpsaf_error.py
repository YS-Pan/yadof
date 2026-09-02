"""Side-effect-free five-fold cost-error bootstrap for the PCA/SVD provider."""
from __future__ import annotations

import numpy as np

from ...job_template import assign_parameters, calculate_costs_from_raw_data


def estimate_initial_error(component, context, data, *, folds=5):
    count = data.sample_count
    if count < 2:
        return None
    permutation = np.random.default_rng(context.random_seed + 1701).permutation(count)
    errors = []
    for held_out in np.array_split(permutation, min(folds, count)):
        held = set(int(i) for i in held_out)
        train = [i for i in range(count) if i not in held]
        model = component.fit_deployable(
            [data.normalized_variables[i] for i in train],
            [data.raw_data[i] for i in train], parameter_names=data.parameter_names,
        )
        rows = tuple(data.normalized_variables[int(i)] for i in held_out)
        samples = component.predict_rawdata(model, rows)
        variables = tuple({p.name: p.value for p in assign_parameters(context.config.workspace, row)} for row in rows)
        prediction = calculate_costs_from_raw_data(context.config.workspace,
            tuple(sample.cost_items() for sample in samples), variables)
        actual = calculate_costs_from_raw_data(context.config.workspace,
            tuple(data.raw_data[int(i)].cost_items() for i in held_out), variables)
        errors.extend(np.abs(np.asarray(prediction) - np.asarray(actual)))
    return tuple(float(v) for v in np.max(errors, axis=0))
