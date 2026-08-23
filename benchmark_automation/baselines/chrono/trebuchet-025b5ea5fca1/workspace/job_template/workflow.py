"""Prepared local/distributed workflow for the King Arthur trebuchet."""

from __future__ import annotations

import os
from types import MappingProxyType

from evaluation import evaluate_prepared
from parameters_constraints import get_parameters


def _evaluate(context):
    parameters = MappingProxyType(
        {parameter.name: float(parameter.value) for parameter in get_parameters()}
    )
    backend = "distributed" if os.environ.get("_CONDOR_SCRATCH_DIR") else "local"
    return evaluate_prepared(
        parameters,
        MappingProxyType(
            {
                "backend": backend,
                "evaluation_name": context.base_dir.name,
                "scratch_dir": context.temp_dir,
                "rawdata_dir": context.raw_data_dir,
                "environment": MappingProxyType({}),
                "timeout_sec": 120.0,
            }
        ),
    )


def main() -> int:
    from worker_misc import run_workflow

    run_workflow(_evaluate)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

