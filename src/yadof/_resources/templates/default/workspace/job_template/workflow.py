"""Pure-Python starter workflow: assigned variables -> generic rawData."""

from __future__ import annotations

import numpy as np

from evaluation import create_evaluation_session
from parameters_constraints import get_parameters


def _evaluate(context) -> int:
    session = create_evaluation_session({"session_dir": context.temp_dir, "environment": {}})
    try:
        payloads = session.evaluate_rawdata(
            {parameter.name: float(parameter.value) for parameter in get_parameters()},
            {"evaluation_name": context.base_dir.name, "scratch_dir": context.temp_dir, "environment": {}},
        )
        for filename, payload in payloads.items():
            np.savez(context.raw_data_dir / filename, **payload)
    finally:
        session.close()
    return 0


def main() -> int:
    from worker_misc import run_workflow

    return int(run_workflow(_evaluate))


if __name__ == "__main__":
    raise SystemExit(main())
