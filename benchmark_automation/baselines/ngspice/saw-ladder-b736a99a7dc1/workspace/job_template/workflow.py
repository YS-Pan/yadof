"""Prepared-job wrapper around the shared ngspice SAW evaluation kernel."""

from __future__ import annotations

from types import MappingProxyType

import numpy as np

from evaluation import evaluate_rawdata
from parameters_constraints import get_parameters


def _evaluate(context) -> int:
    parameters = MappingProxyType(
        {parameter.name: float(parameter.value) for parameter in get_parameters()}
    )
    rawdata_items, _diagnostics = evaluate_rawdata(
        parameters,
        MappingProxyType(
            {
                "evaluation_name": context.base_dir.name,
                "scratch_dir": context.temp_dir,
                "environment": MappingProxyType({}),
                "timeout_sec": 45.0,
            }
        ),
    )
    for filename, payload in rawdata_items.items():
        np.savez_compressed(context.raw_data_dir / filename, **payload)
    return 0


def main() -> int:
    from worker_misc import run_workflow

    return int(run_workflow(_evaluate))


if __name__ == "__main__":
    raise SystemExit(main())

