"""Shared external-PyChrono evaluation entry points for fast and prepared modes."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from chrono_com import run_pychrono


DEFAULT_CHILD_TIMEOUT_SEC = 120.0


def _timeout(context: Mapping[str, object]) -> float:
    value = context.get("timeout_sec")
    return DEFAULT_CHILD_TIMEOUT_SEC if value is None else float(value)


def evaluate_rawdata(
    parameters: Mapping[str, object],
    context: Mapping[str, object],
) -> tuple[Mapping[str, Mapping[str, object]], Mapping[str, object]]:
    """Fast-mode kernel returning adapter-validated rawData in memory."""

    result = run_pychrono(
        Path(__file__).with_name("chrono_worker.py"),
        parameters,
        scratch_root=Path(context["scratch_dir"]) / "pychrono",
        backend="fast",
        load_rawdata=True,
        timeout=_timeout(context),
        environment=context.get("environment"),
        evaluation_id=str(context["evaluation_name"]),
    )
    if result.rawdata is None:
        raise RuntimeError("fast PyChrono evaluation returned no in-memory rawData")
    return result.rawdata, result.as_diagnostics()


def evaluate_prepared(
    parameters: Mapping[str, object],
    context: Mapping[str, object],
) -> Mapping[str, object]:
    """Local/distributed prepared-job path publishing validated flat NPZ files."""

    backend = str(context["backend"])
    if backend not in {"local", "distributed"}:
        raise ValueError("prepared backend must be local or distributed")
    result = run_pychrono(
        Path(__file__).with_name("chrono_worker.py"),
        parameters,
        scratch_root=Path(context["scratch_dir"]) / "pychrono",
        backend=backend,
        rawdata_dir=Path(context["rawdata_dir"]),
        timeout=_timeout(context),
        environment=context.get("environment"),
        evaluation_id=str(context["evaluation_name"]),
    )
    return result.as_diagnostics()

