from __future__ import annotations

import json
from pathlib import Path

import pytest

from yadof.surrogate import _shared
from yadof.surrogate._shared import artifacts, finite_members, training_events
from yadof.surrogate.conditional_inr import checkpoints as conditional_checkpoints
from yadof.surrogate.conditional_inr import posterior_adapter as conditional_posterior
from yadof.surrogate.hierarchical_cae import checkpoints as cae_checkpoints
from yadof.surrogate.hierarchical_cae import posterior_adapter as cae_posterior


def test_shared_package_import_is_dependency_neutral() -> None:
    assert _shared.__name__ == "yadof.surrogate._shared"


def test_component_publication_paths_keep_policy_namespaces(tmp_path: Path) -> None:
    signature = "a" * 64
    conditional = conditional_checkpoints.new_publication_paths(
        tmp_path, generation_index=7, strategy_signature=signature
    )
    cae = cae_checkpoints.new_publication_paths(
        tmp_path, generation_index=7, strategy_signature=signature
    )

    assert conditional[0] == cae[0] == tmp_path / "generation_0007.json"
    assert conditional[4] == cae[4] == "strategy-aaaaaaaaaaaaaaaa"
    assert conditional[5] == "conditional-inr"
    assert cae[5] == "hierarchical-cae"
    assert conditional[2].parent != cae[2].parent


def test_atomic_json_writer_preserves_canonical_payload_shape(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "event.json"
    artifacts.atomic_write_json(path, {"status": "completed", "count": 3})

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "status": "completed",
        "count": 3,
    }
    assert not list(path.parent.glob("*.tmp"))


@pytest.mark.parametrize("seed", [0, 17, 2**64 + 17])
def test_finite_member_selection_is_identical_for_both_adapters(seed: int) -> None:
    expected = finite_members.seeded_member_indices(3, 8, seed)

    assert conditional_posterior._seeded_member_indices(3, 8, seed) == expected
    assert cae_posterior._seeded_member_indices(3, 8, seed) == expected
    assert set(expected) == {0, 1, 2}


def test_failure_event_is_bounded_and_policy_neutral() -> None:
    payload = training_events.failure_metadata(
        generation_index=4,
        exc=RuntimeError("training stopped"),
        model="model-id",
        started_at="start",
        ended_at="end",
        strategy_signature="b" * 64,
    )

    assert payload == {
        "record_type": "surrogate_training",
        "status": "error",
        "generation_index": 4,
        "started_at": "start",
        "ended_at": "end",
        "error_type": "RuntimeError",
        "error_message": "training stopped",
        "strategy_signature": "b" * 64,
        "model": "model-id",
    }
