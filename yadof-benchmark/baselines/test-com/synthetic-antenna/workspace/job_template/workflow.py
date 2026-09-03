"""Prepared-job wrapper for the same ``test_com`` rawData kernel."""

from __future__ import annotations

from types import MappingProxyType

import numpy as np

from evaluation import create_evaluation_session
from parameters_constraints import get_parameters


def _evaluate(context) -> None:
    parameters = MappingProxyType(
        {parameter.name: float(parameter.value) for parameter in get_parameters()}
    )
    session = create_evaluation_session({"session_dir": context.temp_dir, "environment": {}})
    try:
        payloads, _diagnostics = session.evaluate_rawdata(
            parameters,
            MappingProxyType(
                {
                    "evaluation_name": context.base_dir.name,
                    "scratch_dir": context.temp_dir,
                    "environment": MappingProxyType({}),
                }
            ),
        )
    finally:
        session.close()
    for filename, payload in payloads.items():
        np.savez_compressed(context.raw_data_dir / filename, **payload)


def main() -> int:
    from worker_misc import run_workflow

    run_workflow(_evaluate)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
