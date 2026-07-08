from __future__ import annotations

from dataclasses import asdict
import json

import numpy as np

from .types import RawDataSchema, SurrogateState


def schema_payload(schema: RawDataSchema | None) -> dict[str, object]:
    if schema is None:
        return {"flat_dim": 0, "modeled_slots": []}
    return {
        "rawdata_item_count": len(schema.templates),
        "flat_dim": int(schema.flat_dim),
        "query_count": int(schema.coord_table.shape[0]),
        "n_fields": int(schema.n_fields),
        "modeled_slots": [
            {
                "item_index": int(slot.item_index),
                "key": slot.key,
                "shape": list(slot.shape),
                "dtype": slot.dtype,
                "start": int(slot.start),
                "end": int(slot.end),
                "field_id": int(slot.field_id),
            }
            for slot in schema.modeled_slots
        ],
    }


def write_checkpoint(state: SurrogateState) -> None:
    state.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    state.artifact_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generation_index": int(state.generation_index),
        "sample_count": int(state.sample_count),
        "parameter_names": list(state.parameter_names),
        "model": state.model_name,
        "member_count": int(state.train_history.get("member_count", 0)),
        "mean_relative_error": float(state.mean_relative_error),
        "historical_relative_error_p50": list(state.historical_relative_error_p50),
        "historical_relative_error_p90": list(state.historical_relative_error_p90),
        "historical_relative_error_p95": list(state.historical_relative_error_p95),
        "historical_absolute_error_p90": list(state.historical_absolute_error_p90),
        "model_path": state.model_path.name,
        "artifact_dir": state.artifact_dir.name,
        "schema": schema_payload(state.schema),
        "train_cfg": None if state.train_cfg is None else asdict(state.train_cfg),
        "train_history": state.train_history,
        "note": "Surrogate predicts rawData arrays with a conditional INR deep ensemble; costs are dynamically derived through job_template.calc_cost.",
    }
    state.checkpoint_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
        newline="\n",
    )

    arrays: dict[str, np.ndarray] = {
        "schema_flat_dim": np.asarray(0 if state.schema is None else state.schema.flat_dim, dtype=np.int64),
        "training_sample_count": np.asarray(state.sample_count, dtype=np.int64),
        "training_flat_values": np.ascontiguousarray(state.training_flat_values, dtype=np.float32),
        "query_weights": np.ascontiguousarray(state.query_weights, dtype=np.float32),
    }
    if state.schema is not None:
        arrays["coord_table"] = np.ascontiguousarray(state.schema.coord_table, dtype=np.float32)
        arrays["field_ids"] = np.ascontiguousarray(state.schema.field_ids, dtype=np.int64)
    if state.scaler is not None:
        arrays["target_mean"] = np.ascontiguousarray(state.scaler.mean, dtype=np.float32)
        arrays["target_scale"] = np.ascontiguousarray(state.scaler.scale, dtype=np.float32)
    np.savez_compressed(state.model_path, **arrays)
