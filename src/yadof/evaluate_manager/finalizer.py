"""Backend-neutral result validation, current cost, and recorder admission."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path
import time

from ..job_template import api as job_template_api
from ..recorded_data.rawdata_v2 import own_rawdata_source
from ..recorded_data.records_v2 import build_owned_envelope
from ..recorded_data.session import CampaignSession
from ..task_snapshot import GenerationTaskSnapshot
from .types import JobResult


def finalize_result(
    session: CampaignSession,
    snapshot: GenerationTaskSnapshot,
    result: JobResult,
) -> JobResult:
    """Return current cost before and independently of best-effort persistence."""

    started = time.monotonic()
    metadata = dict(result.metadata)
    metadata.setdefault("campaign_id", session.campaign_id)
    metadata.update(
        {
            "interpretation_fingerprint": snapshot.interpretation_fingerprint,
            "evaluation_fingerprint": snapshot.evaluation_fingerprint,
            "task_snapshot_id": snapshot.task_snapshot_id,
        }
    )
    if result.status != "done":
        failed = replace(result, metadata=metadata, costs=None)
        _offer_nonfatal(session, snapshot, failed, (), None)
        return failed

    try:
        source = (
            result.raw_data_items
            if result.raw_data_items
            else tuple(Path(path) for path in result.raw_data_paths)
        )
        owned = own_rawdata_source(source)
        raw_variables = tuple(float(value) for value in result.unnormalized_variables)
        costs = job_template_api.calculate_cost(
            snapshot.config.workspace,
            (tuple(item.payload for item in owned),),
            (raw_variables,),
        )[0]
        if len(costs) != len(snapshot.objective_names):
            raise ValueError(
                f"current cost width {len(costs)} does not match "
                f"generation objective width {len(snapshot.objective_names)}"
            )
    except Exception as exc:  # noqa: BLE001 - one candidate becomes a failure row.
        metadata.update(
            {
                "status": "error",
                "failure_stage": "result_finalization",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "failed_at": _now_text(),
                "rawdata_validation_cost_sec": max(
                    0.0, time.monotonic() - started
                ),
            }
        )
        failed = replace(
            result,
            status="error",
            raw_data_paths=(),
            raw_data_items=(),
            metadata=metadata,
            costs=None,
        )
        _offer_nonfatal(session, snapshot, failed, (), None)
        return failed

    metadata["rawdata_validation_cost_sec"] = max(0.0, time.monotonic() - started)
    finalized = replace(
        result,
        raw_data_paths=(),
        raw_data_items=owned,
        metadata=metadata,
        costs=tuple(float(value) for value in costs),
    )
    admission_started = time.monotonic()
    _offer_nonfatal(session, snapshot, finalized, owned, finalized.costs)
    finalized_metadata = dict(finalized.metadata)
    finalized_metadata["recorder_admission_sec"] = max(
        0.0, time.monotonic() - admission_started
    )
    return replace(finalized, metadata=finalized_metadata)


def _offer_nonfatal(
    session: CampaignSession,
    snapshot: GenerationTaskSnapshot,
    result: JobResult,
    owned,
    costs,
) -> None:
    try:
        envelope = build_owned_envelope(
            snapshot.config.workspace,
            result.job_name,
            result.unnormalized_variables,
            owned,
            result.metadata,
            status="completed" if result.status == "done" else result.status,
        )
        session.add_finalized(
            envelope,
            normalized=(
                result.normalized_variables if result.status == "done" else None
            ),
            costs=costs,
            interpretation_fingerprint=snapshot.interpretation_fingerprint,
        )
    except Exception:
        # A valid cost is already final at this boundary. Even envelope construction
        # and logging failures are best-effort recording loss.
        return


def _now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


__all__ = ["finalize_result"]
