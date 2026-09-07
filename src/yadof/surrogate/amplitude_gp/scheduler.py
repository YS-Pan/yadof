"""One owned training worker per workspace, strategy and settings snapshot."""

from dataclasses import dataclass
import threading

from ..training import TrainingCancelledError
from . import runtime


@dataclass(frozen=True, slots=True)
class TrainingScheduleStatus:
    action: str
    generation_index: int | None = None
    pending_generation_index: int | None = None
    latest_completed_generation_index: int | None = None
    error: str = ""


@dataclass
class _Schedule:
    handle: object = None
    generation: int | None = None
    completed: int | None = None


_LOCK = threading.RLock()
_SCHEDULES = {}


def start(context, data, settings):
    runtime._require_data(data)
    generation = context.generation_index
    if data.sample_count < settings.minimum_training_samples:
        return TrainingScheduleStatus("skipped_no_data", generation)
    key = runtime.workspace_state_key(context.snapshot.config.workspace, settings)
    with _LOCK:
        schedule = _SCHEDULES.setdefault(key, _Schedule())
        if schedule.handle is not None:
            return TrainingScheduleStatus("already_running", generation, schedule.generation, schedule.completed)
        schedule.handle = runtime.start_fit(
            context.config.workspace, data, generation_index=generation, settings=settings,
            session=context.session, snapshot=context.snapshot)
        schedule.generation = generation
        return TrainingScheduleStatus("started", generation, generation, schedule.completed)


def finish(workspace, settings):
    key = runtime.workspace_state_key(runtime.selected_workspace(workspace), settings)
    with _LOCK:
        schedule = _SCHEDULES.get(key)
        if schedule is None or schedule.handle is None:
            return TrainingScheduleStatus("idle", latest_completed_generation_index=(
                None if schedule is None else schedule.completed))
        handle, generation = schedule.handle, schedule.generation
    state, error, action = None, "", "completed"
    try:
        state = handle.wait()
    except TrainingCancelledError as exc:
        action, error = "cancelled", str(exc)
    except Exception as exc:  # A failed model is reported; selection can use real evaluations.
        action, error = "failed", f"{type(exc).__name__}: {exc}"
    finally:
        try:
            handle.close()
        except Exception as exc:
            if not error:
                action, error = "failed", f"{type(exc).__name__}: {exc}"
        with _LOCK:
            if state is not None:
                schedule.completed = state.generation_index
            if schedule.handle is handle:
                schedule.handle = schedule.generation = None
    return TrainingScheduleStatus(action, generation, None, schedule.completed, error)


def ensure_fresh_enough(context, data, settings):
    def latest():
        return runtime.recover(context.config.workspace, data, settings=settings,
                               snapshot=context.snapshot, allow_lagged=True)

    runtime._require_data(data)
    if data.sample_count < settings.minimum_training_samples:
        return TrainingScheduleStatus("skipped_no_data", context.generation_index)
    max_lag = max(0, int(context.config.OPTIMIZE_SURROGATE_MAX_TRAINING_LAG))
    state = latest()
    if state is not None and 0 <= context.generation_index - state.generation_index <= max_lag:
        return TrainingScheduleStatus("fresh", context.generation_index,
                                      latest_completed_generation_index=state.generation_index)
    finish(context.config.workspace, settings)
    state = latest()
    if state is not None and 0 <= context.generation_index - state.generation_index <= max_lag:
        return TrainingScheduleStatus("waited", context.generation_index,
                                      latest_completed_generation_index=state.generation_index)
    start(context, data, settings)
    return finish(context.config.workspace, settings)


def deactivate_workspace(workspace):
    root = str(runtime.workspace_root(workspace))
    with _LOCK:
        schedules = tuple((key, value) for key, value in _SCHEDULES.items() if key[0] == root)
    errors, generations = [], []
    for _key, schedule in schedules:
        if schedule.handle is not None:
            try:
                generations.append(schedule.handle.finish().generation_index)
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
    with _LOCK:
        for key, _schedule in schedules:
            _SCHEDULES.pop(key, None)
    runtime.reset_workspace_state(workspace)
    return TrainingScheduleStatus(
        "deactivated_with_errors" if errors else "deactivated",
        latest_completed_generation_index=max(generations) if generations else None, error="; ".join(errors))
