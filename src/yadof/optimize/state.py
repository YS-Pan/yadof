"""Active optimization-strategy pointer and retained namespace identity."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile
from typing import Mapping

from ..workspace import WorkspaceContext, resolve_workspace


ACTIVE_STATE_RELATIVE_PATH = Path(".yadof/optimization/active.json")
ACTIVE_STATE_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class ActiveStrategyState:
    strategy_signature: str
    strategy_namespace: str
    strategy_identity: Mapping[str, object]
    optimization_source_hash: str


def strategy_namespace_for_signature(signature: str) -> str:
    selected = str(signature).lower()
    if len(selected) != 64 or any(char not in "0123456789abcdef" for char in selected):
        raise ValueError("strategy signature must be 64 lowercase hexadecimal characters")
    return f"strategy-{selected[:16]}"


def read_active_strategy_state(
    workspace: WorkspaceContext | str | os.PathLike[str],
) -> ActiveStrategyState | None:
    context = resolve_workspace(workspace)
    path = context.root / ACTIVE_STATE_RELATIVE_PATH
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if int(payload["schema_version"]) != ACTIVE_STATE_SCHEMA_VERSION:
            return None
        signature = str(payload["strategy_signature"])
        namespace = strategy_namespace_for_signature(signature)
        if str(payload["strategy_namespace"]) != namespace:
            return None
        identity = payload["strategy_identity"]
        if not isinstance(identity, dict):
            return None
        return ActiveStrategyState(
            strategy_signature=signature,
            strategy_namespace=namespace,
            strategy_identity=identity,
            optimization_source_hash=str(payload["optimization_source_hash"]),
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def write_active_strategy_state(
    workspace: WorkspaceContext | str | os.PathLike[str],
    *,
    strategy_signature: str,
    strategy_identity: Mapping[str, object],
    optimization_source_hash: str,
) -> ActiveStrategyState:
    context = resolve_workspace(workspace)
    namespace = strategy_namespace_for_signature(strategy_signature)
    state = ActiveStrategyState(
        strategy_signature=str(strategy_signature),
        strategy_namespace=namespace,
        strategy_identity=dict(strategy_identity),
        optimization_source_hash=str(optimization_source_hash),
    )
    current = read_active_strategy_state(context)
    if current == state:
        return current
    path = context.root / ACTIVE_STATE_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": ACTIVE_STATE_SCHEMA_VERSION,
        "strategy_signature": state.strategy_signature,
        "strategy_namespace": state.strategy_namespace,
        "strategy_identity": dict(state.strategy_identity),
        "optimization_source_hash": state.optimization_source_hash,
        "activated_at": datetime.now().astimezone().isoformat(timespec="milliseconds"),
    }
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return state


def active_strategy_signature(
    workspace: WorkspaceContext | str | os.PathLike[str],
) -> str | None:
    state = read_active_strategy_state(workspace)
    return None if state is None else state.strategy_signature


__all__ = [
    "ACTIVE_STATE_RELATIVE_PATH",
    "ActiveStrategyState",
    "active_strategy_signature",
    "read_active_strategy_state",
    "strategy_namespace_for_signature",
    "write_active_strategy_state",
]
