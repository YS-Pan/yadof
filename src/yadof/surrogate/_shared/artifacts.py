"""Atomic checkpoint publication primitives without component policy."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import time
import uuid


def run_namespace_for_signature(strategy_signature: str) -> str:
    signature = str(strategy_signature).lower()
    if len(signature) != 64 or any(char not in "0123456789abcdef" for char in signature):
        raise ValueError("strategy signature must be 64 lowercase hexadecimal characters")
    return f"strategy-{signature[:16]}"


def new_publication_paths(
    checkpoint_dir: Path,
    *,
    generation_index: int,
    strategy_signature: str,
    component_namespace: str,
) -> tuple[Path, Path, Path, Path, str, str]:
    root = Path(checkpoint_dir)
    run_namespace = run_namespace_for_signature(strategy_signature)
    namespace_dir = root / "runs" / run_namespace / "components" / component_namespace
    publication_id = f"{time.time_ns():020d}_{uuid.uuid4().hex}"
    stem = f"generation_{int(generation_index):04d}"
    return (
        root / f"{stem}.json",
        namespace_dir / f"{stem}_{publication_id}.json",
        namespace_dir / f"{stem}_{publication_id}",
        namespace_dir / f".{stem}_{publication_id}.tmp",
        run_namespace,
        component_namespace,
    )


def atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
