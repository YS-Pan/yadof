from __future__ import annotations

import builtins
import math
import subprocess
import sys

import numpy as np
import pytest

from yadof.job_template import JointObjectiveSamples
from yadof.optimize.qnehvi.backend import score_discrete_qlognehvi


pytestmark = pytest.mark.filterwarnings("ignore:Failed to compile fused qLogEHVI")


def _samples(
    costs=None,
    *,
    valid=None,
    population=((0.2,), (0.3,), (0.4,)),
    source=None,
):
    if costs is None:
        costs = np.asarray(
            [
                [[0.20, 0.70], [0.60, 0.20], [0.30, 0.30]],
                [[0.30, 0.60], [0.50, 0.25], [0.35, 0.35]],
                [[0.25, 0.65], [0.55, 0.22], [0.32, 0.31]],
            ],
            dtype=np.float64,
        )
    costs = np.asarray(costs, dtype=np.float64)
    if valid is None:
        valid = np.ones(costs.shape[:2], dtype=bool)
    draw_ids = tuple(f"draw-{index}" for index in range(costs.shape[0]))
    diagnostics = {
        "posterior_kind": "empirical_ensemble",
        "support_kind": "finite",
        "unique_support": costs.shape[0],
        "draw_sources": [f"source-{index}" for index in range(costs.shape[0])],
        **dict(source or {}),
    }
    return JointObjectiveSamples.from_arrays(
        cost_samples=costs,
        valid_mask=valid,
        draw_ids=draw_ids,
        normalized_population=population,
        objective_names=("first", "second")[: costs.shape[2]],
        source_diagnostics=diagnostics,
    )


def _score(samples=None, batches=((0,), (1,), (0, 1)), **kwargs):
    seed = kwargs.pop("seed", 19)
    return score_discrete_qlognehvi(
        baseline_population=((0.0,), (0.1,)),
        baseline_costs=((0.4, 0.8), (0.7, 0.3)),
        candidate_samples=_samples() if samples is None else samples,
        candidate_batches=batches,
        seed=seed,
        **kwargs,
    )


def test_qlognehvi_uses_botorch_core_and_scores_q1_q2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("botorch")
    from yadof.optimize.qnehvi import _botorch_backend as backend

    calls = []
    original = backend._QLOGNEHVI_CLASS

    def spy(*args, **kwargs):
        calls.append(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(backend, "_QLOGNEHVI_CLASS", spy)
    result = _score()

    assert len(calls) == 1
    assert result.batch_indices == ((0,), (1,), (0, 1))
    assert all(math.isfinite(value) for value in result.log_acquisition_values)
    assert result.log_acquisition_values[2] > result.log_acquisition_values[0]
    assert result.diagnostics["backend_class"] == (
        "qLogNoisyExpectedHypervolumeImprovement"
    )
    assert result.diagnostics["direction"] == (
        "minimization_cost_negated_once_for_backend_maximization"
    )
    assert result.diagnostics["fixed_baseline"] is True
    assert result.diagnostics["observation_noise_included"] is False
    assert result.diagnostics["usable_draw_count"] == 3


def test_zero_noise_fixed_baseline_matches_qlogehvi_limit() -> None:
    pytest.importorskip("botorch")
    import torch
    from botorch.acquisition.multi_objective.logei import (
        qLogExpectedHypervolumeImprovement,
    )
    from botorch.utils.multi_objective.box_decompositions.non_dominated import (
        FastNondominatedPartitioning,
    )
    from yadof.optimize.qnehvi._botorch_backend import (
        _EnumerateSampler,
        _LookupEnsembleModel,
    )

    objective_samples = _samples()
    result = _score(objective_samples, batches=((0,), (0, 1)))
    baseline_x = torch.tensor([[0.0], [0.1]], dtype=torch.float64)
    candidate_x = torch.tensor([[0.2], [0.3], [0.4]], dtype=torch.float64)
    baseline_costs = torch.tensor(
        [[0.4, 0.8], [0.7, 0.3]], dtype=torch.float64
    )
    candidate_costs = torch.as_tensor(
        np.array(objective_samples.cost_samples, copy=True),
        dtype=torch.float64,
    )
    model = _LookupEnsembleModel(
        torch.cat((baseline_x, candidate_x)),
        torch.cat(
            (
                -baseline_costs.unsqueeze(0).expand(3, -1, -1),
                -candidate_costs,
            ),
            dim=1,
        ),
    )
    sampler = _EnumerateSampler(torch.Size((3,)), seed=19)
    partitioning = FastNondominatedPartitioning(
        ref_point=torch.tensor([-1.0, -1.0], dtype=torch.float64),
        Y=-baseline_costs,
    )
    acquisition = qLogExpectedHypervolumeImprovement(
        model=model,
        ref_point=[-1.0, -1.0],
        partitioning=partitioning,
        sampler=sampler,
    )
    with torch.no_grad():
        expected = tuple(
            float(acquisition(candidate_x[list(batch)]).item())
            for batch in ((0,), (0, 1))
        )
    assert result.log_acquisition_values == pytest.approx(expected, abs=1e-4)


def test_joint_draw_pairing_changes_acquisition_when_objective_is_rearranged() -> None:
    pytest.importorskip("botorch")
    original = _samples()
    rearranged = np.asarray(original.cost_samples).copy()
    rearranged[:, :, 1] = rearranged[::-1, :, 1]

    coherent = _score(original, batches=((0, 1),)).log_acquisition_values[0]
    incoherent = _score(
        _samples(rearranged),
        batches=((0, 1),),
    ).log_acquisition_values[0]
    assert coherent != pytest.approx(incoherent, abs=1e-10)


def test_invalid_projection_rejects_whole_draw_and_finite_one_remains_valid() -> None:
    pytest.importorskip("botorch")
    costs = np.asarray(
        [
            [[1.0, 1.0], [0.5, 0.6]],
            [[0.2, 0.3], [0.4, 0.5]],
            [[0.3, 0.4], [0.2, 0.3]],
        ],
        dtype=np.float64,
    )
    valid = np.asarray([[True, True], [True, False], [True, True]])
    samples = _samples(
        costs,
        valid=valid,
        population=((0.2,), (0.3,)),
        source={
            "unique_support": 3,
            "draw_sources": ["member-0", "member-1", "member-2"],
        },
    )
    result = _score(
        samples,
        batches=((0,),),
        minimum_unique_support=2,
    )

    assert result.diagnostics["usable_draw_count"] == 2
    assert result.diagnostics["rejected_whole_draw_count"] == 1
    assert result.diagnostics["effective_unique_support"] == 2
    assert result.diagnostics["finite_one_is_valid"] is True


def test_low_finite_support_policy_is_visible() -> None:
    pytest.importorskip("botorch")
    samples = _samples(
        source={
            "unique_support": 3,
            "effective_unique_support": 1,
            "draw_sources": ["member-0", "member-0", "member-0"],
        }
    )
    with pytest.raises(RuntimeError, match="effective support 1"):
        _score(samples, minimum_unique_support=2)

    with pytest.warns(RuntimeWarning, match="effective support 1"):
        result = _score(
            samples,
            minimum_unique_support=2,
            low_support_policy="warn",
        )
    assert result.diagnostics["low_support"] is True
    assert result.diagnostics["low_support_policy"] == "warn"


def test_backend_validation_covers_objectives_empty_duplicates_and_seed() -> None:
    pytest.importorskip("botorch")
    one_objective = JointObjectiveSamples.from_arrays(
        cost_samples=np.asarray([[[0.2]], [[0.3]]]),
        valid_mask=np.ones((2, 1), dtype=bool),
        draw_ids=("a", "b"),
        normalized_population=((0.2,),),
        objective_names=("only",),
    )
    with pytest.raises(ValueError, match="at least two objectives"):
        _score(one_objective, batches=((0,),))
    with pytest.raises(ValueError, match="candidate pool must not be empty"):
        _score(
            _samples(
                np.zeros((2, 0, 2)),
                valid=np.zeros((2, 0), dtype=bool),
                population=(),
            ),
            batches=((0,),),
        )
    with pytest.raises(ValueError, match="duplicate rows"):
        _score(
            _samples(population=((0.2,), (0.2,), (0.4,))),
            batches=((0,),),
        )
    with pytest.raises(ValueError, match="cannot repeat"):
        _score(batches=((0, 0),))

    first = _score(batches=((0,),), seed=23)
    second = _score(batches=((0,),), seed=23)
    assert first.log_acquisition_values == second.log_acquisition_values
    assert first.diagnostics["seed"] == 23


def test_missing_optional_backend_has_actionable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_name = "yadof.optimize.qnehvi._botorch_backend"
    saved = sys.modules.pop(private_name, None)
    real_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "botorch" or name.startswith("botorch."):
            raise ModuleNotFoundError("blocked for test", name="botorch")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    try:
        with pytest.raises(RuntimeError, match=r"yadof\[qnehvi\]"):
            _score(batches=((0,),))
    finally:
        if saved is not None:
            sys.modules[private_name] = saved


def test_parent_optimize_import_does_not_load_optional_backend() -> None:
    command = (
        "import json, sys; import yadof.optimize; "
        "print(json.dumps([name for name in ('torch','botorch','gpytorch') "
        "if name in sys.modules]))"
    )
    completed = subprocess.run(
        [sys.executable, "-I", "-c", command],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout.strip() == "[]"
