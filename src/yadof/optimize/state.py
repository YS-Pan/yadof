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
PROGRAM_COMPLETION_RELATIVE_PATH = Path(
    ".yadof/optimization/program-completion.json"
)
PROGRAM_COMPLETION_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class ActiveStrategyState:
    strategy_signature: str
    strategy_namespace: str
    strategy_identity: Mapping[str, object]
    optimization_source_hash: str


@dataclass(frozen=True, slots=True)
class ProgramCompletionState:
    program_signature: str
    generation_index: int
    program_source_fingerprint: str
    task_snapshot_id: str


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


def activate_strategy_state(
    workspace: WorkspaceContext | str | os.PathLike[str],
    *,
    strategy_signature: str,
    strategy_identity: Mapping[str, object],
    optimization_source_hash: str,
) -> ActiveStrategyState:
    """Switch one semantic namespace, closing only in-memory retained work."""

    context = resolve_workspace(workspace)
    active = read_active_strategy_state(context)
    if active is not None and active.strategy_signature != strategy_signature:
        try:
            from ..surrogate.api import deactivate_workspace

            deactivate_workspace(context.root)
        except ImportError:
            # Core-only real search cannot own an unavailable optional runtime's
            # in-memory task. Its disk namespace remains isolated by signature.
            pass
    return write_active_strategy_state(
        context,
        strategy_signature=strategy_signature,
        strategy_identity=strategy_identity,
        optimization_source_hash=optimization_source_hash,
    )


def read_program_completion_state(
    workspace: WorkspaceContext | str | os.PathLike[str],
) -> ProgramCompletionState | None:
    context = resolve_workspace(workspace)
    path = context.root / PROGRAM_COMPLETION_RELATIVE_PATH
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if int(payload["schema_version"]) != PROGRAM_COMPLETION_SCHEMA_VERSION:
            raise ValueError("unsupported program completion schema")
        signature = _sha256(payload["program_signature"], "program_signature")
        generation_index = int(payload["generation_index"])
        if generation_index < 0:
            raise ValueError("program completion generation_index is negative")
        return ProgramCompletionState(
            program_signature=signature,
            generation_index=generation_index,
            program_source_fingerprint=_sha256(
                payload["program_source_fingerprint"],
                "program_source_fingerprint",
            ),
            task_snapshot_id=_sha256(payload["task_snapshot_id"], "task_snapshot_id"),
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid explicit program completion pointer: {path}") from exc


def write_program_completion_state(
    workspace: WorkspaceContext | str | os.PathLike[str],
    *,
    program_signature: str,
    generation_index: int,
    program_source_fingerprint: str,
    task_snapshot_id: str,
) -> ProgramCompletionState:
    context = resolve_workspace(workspace)
    selected_generation = int(generation_index)
    if selected_generation < 0:
        raise ValueError("completed program generation_index must be non-negative")
    state = ProgramCompletionState(
        program_signature=_sha256(program_signature, "program_signature"),
        generation_index=selected_generation,
        program_source_fingerprint=_sha256(
            program_source_fingerprint,
            "program_source_fingerprint",
        ),
        task_snapshot_id=_sha256(task_snapshot_id, "task_snapshot_id"),
    )
    path = context.root / PROGRAM_COMPLETION_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": PROGRAM_COMPLETION_SCHEMA_VERSION,
        "program_signature": state.program_signature,
        "generation_index": state.generation_index,
        "program_source_fingerprint": state.program_source_fingerprint,
        "task_snapshot_id": state.task_snapshot_id,
        "completed_at": datetime.now().astimezone().isoformat(timespec="milliseconds"),
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


def _sha256(value: object, label: str) -> str:
    text = str(value).strip().lower()
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ValueError(f"{label} must be a SHA-256 hex digest")
    return text


__all__ = [
    "ACTIVE_STATE_RELATIVE_PATH",
    "PROGRAM_COMPLETION_RELATIVE_PATH",
    "ActiveStrategyState",
    "ProgramCompletionState",
    "activate_strategy_state",
    "active_strategy_signature",
    "read_active_strategy_state",
    "read_program_completion_state",
    "strategy_namespace_for_signature",
    "write_active_strategy_state",
    "write_program_completion_state",
]
