"""Owned fitted state for the retrieval response."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class RetrievalResponseState:
    generation_index: int
    sample_count: int
    state_signature: str
    training_data_digest: str
    training_provenance_digest: str
    identity: dict[str, object]
    training_row_ids: tuple[str, ...]
    training_normalized_variables: tuple[tuple[float, ...], ...]
    training_provenance: dict[str, object]
    model: Any = field(repr=False)
    checkpoint_path: Path
    namespace_manifest_path: Path
    artifact_dir: Path
    train_history: dict[str, object]
