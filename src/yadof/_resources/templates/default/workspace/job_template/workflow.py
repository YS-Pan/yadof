"""Pure-Python starter workflow: assigned variables -> generic rawData."""

from __future__ import annotations

import json

import numpy as np

from parameters_constraints import get_parameters


def _evaluate(context) -> int:
    from worker_misc import rawdata_metadata

    values = np.asarray([parameter.value for parameter in get_parameters()], dtype=float)
    if not np.all(np.isfinite(values)):
        raise ValueError("starter workflow requires assigned finite parameter values")

    response = np.asarray(float(np.mean(values**2)), dtype=float)
    np.savez(
        context.raw_data_dir / "response.npz",
        values=response,
        metadata=json.dumps(
            rawdata_metadata("response", response.shape),
            sort_keys=True,
        ),
    )
    return 0


def main() -> int:
    from worker_misc import run_workflow

    return int(run_workflow(_evaluate))


if __name__ == "__main__":
    raise SystemExit(main())
