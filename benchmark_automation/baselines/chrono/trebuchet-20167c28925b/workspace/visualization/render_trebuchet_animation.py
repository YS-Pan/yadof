"""Render an MP4 replay from one completed trebuchet rawData snapshot.

Export launches one visualization-only PyChrono child so the mechanism continues
after release. It does not run yadof or add an optimization evaluation.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import runpy
import shutil
import sys

import matplotlib

matplotlib.use("Agg")

import matplotlib.animation as animation
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Polygon
import numpy as np


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_WORKSPACE = SCRIPT_DIR.parent
DEFAULT_OUTPUT_DIR = Path.cwd() / "temp" / "trebuchet_visualization"
DEFAULT_OUTPUT = DEFAULT_OUTPUT_DIR / "trebuchet.mp4"
DEFAULT_POSTER = DEFAULT_OUTPUT_DIR / "trebuchet_poster.png"
DEFAULT_WORK_DIR = DEFAULT_OUTPUT_DIR / "_work"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a completed King Arthur trebuchet simulation as MP4."
    )
    parser.add_argument(
        "--job",
        type=Path,
        help="Completed yadof job directory. Defaults to the newest compatible job.",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        help="Task workspace supplying job_template/ and submit/.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--poster", type=Path, default=DEFAULT_POSTER)
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=DEFAULT_WORK_DIR,
        help="Scratch/trajectory directory; keep it outside declared task inputs.",
    )
    parser.add_argument(
        "--title",
        help="Figure and video title. Defaults to a title derived from the job name.",
    )
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--dpi", type=int, default=120)
    parser.add_argument(
        "--continuation-timeout",
        type=float,
        default=120.0,
        help="Timeout in seconds for the visualization-only PyChrono child.",
    )
    return parser.parse_args()


def _latest_job(workspace: Path) -> Path:
    jobs_root = workspace / "jobs"
    candidates = [
        path
        for path in jobs_root.glob("job_*")
        if (path / "rawData" / "trebuchet_total_time.npz").is_file()
        and len(tuple((path / "rawData").glob("*.npz"))) > 1
        and (path / "parameters_constraints.py").is_file()
    ]
    if not candidates:
        raise FileNotFoundError(f"No compatible completed job found below {jobs_root}")
    return max(candidates, key=lambda path: path.stat().st_mtime_ns)


def _load_payload(path: Path) -> dict[str, object]:
    with np.load(path, allow_pickle=False) as payload:
        return {
            name: np.asarray(payload[name]).copy()
            for name in payload.files
        }


def _load_parameters(job: Path) -> dict[str, float]:
    module = runpy.run_path(str(job / "parameters_constraints.py"))
    return {item.name: float(item.value) for item in module["PARAMETERS"]}


def _save_payload(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".part")
    with partial.open("wb") as stream:
        np.savez_compressed(stream, **payload)
    os.replace(partial, path)


def _save_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".part")
    partial.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(partial, path)


def _generate_animation_trajectory(
    *,
    workspace: Path,
    job: Path,
    parameters: dict[str, float],
    timeout: float,
    work_dir: Path,
) -> tuple[
    np.ndarray,
    dict[str, object],
    dict[str, np.ndarray],
    dict[str, object],
    Path,
]:
    if not math.isfinite(timeout) or timeout <= 0.0:
        raise ValueError("--continuation-timeout must be finite and positive")

    task_dir = workspace / "job_template"
    sys.path.insert(0, str(task_dir))
    try:
        from chrono_com import run_pychrono
    finally:
        sys.path.pop(0)

    previous_workspace = os.environ.get("YADOF_ANIMATION_WORKSPACE")
    os.environ["YADOF_ANIMATION_WORKSPACE"] = str(workspace)
    work_dir = work_dir.resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = run_pychrono(
            SCRIPT_DIR / "chrono_animation_worker.py",
            parameters,
            scratch_root=work_dir / ".scratch",
            backend="fast",
            load_rawdata=True,
            timeout=timeout,
            evaluation_id=f"animation_{job.name}",
        )
    finally:
        if previous_workspace is None:
            os.environ.pop("YADOF_ANIMATION_WORKSPACE", None)
        else:
            os.environ["YADOF_ANIMATION_WORKSPACE"] = previous_workspace
    if result.rawdata is None:
        raise RuntimeError("animation PyChrono child returned no trajectory")
    payload = dict(result.rawdata["trebuchet_animation_trajectory.npz"])
    trajectory_path = work_dir / "trebuchet_animation_trajectory.npz"
    _save_payload(trajectory_path, payload)
    diagnostics = result.as_diagnostics()
    _save_json(work_dir / "continuation_diagnostics.json", diagnostics)
    metadata = json.loads(str(np.asarray(payload["metadata"]).item()))
    axes = {
        name: np.asarray(value, dtype=float)
        for name, value in payload.items()
        if name.startswith("axis_")
    }
    return (
        np.asarray(payload["values"], dtype=float),
        metadata,
        axes,
        diagnostics,
        trajectory_path,
    )


def _member_polygon(
    start: tuple[float, float],
    end: tuple[float, float],
    thickness: float,
) -> np.ndarray:
    start_array = np.asarray(start, dtype=float)
    end_array = np.asarray(end, dtype=float)
    direction = end_array - start_array
    length = float(np.linalg.norm(direction))
    if length <= 1.0e-12:
        return np.repeat(start_array[None, :], 4, axis=0)
    normal = np.array((-direction[1], direction[0])) / length
    offset = 0.5 * thickness * normal
    return np.vstack(
        (start_array + offset, end_array + offset, end_array - offset, start_array - offset)
    )


def _rotated_box(center: tuple[float, float], size: float, angle_rad: float) -> np.ndarray:
    half = 0.5 * size
    local = np.array(((-half, -half), (half, -half), (half, half), (-half, half)))
    rotation = np.array(
        ((math.cos(angle_rad), -math.sin(angle_rad)),
         (math.sin(angle_rad), math.cos(angle_rad)))
    )
    return local @ rotation.T + np.asarray(center, dtype=float)


def _configure_ffmpeg() -> str:
    executable = shutil.which("ffmpeg")
    if executable is None:
        common = Path(r"C:\Program Files\FFmpeg\ffmpeg.exe")
        if common.is_file():
            executable = str(common)
    if executable is None:
        raise RuntimeError("ffmpeg was not found; install it or add it to PATH")
    matplotlib.rcParams["animation.ffmpeg_path"] = executable
    return executable


def main() -> int:
    args = _parse_args()
    if args.fps <= 0 or args.dpi <= 0:
        raise ValueError("--fps and --dpi must be positive")

    workspace = (args.workspace or DEFAULT_WORKSPACE).resolve()
    if not workspace.is_dir():
        raise FileNotFoundError(f"animation task workspace does not exist: {workspace}")
    job = (args.job or _latest_job(workspace)).resolve()
    rawdata = job / "rawData"
    parameters = _load_parameters(job)
    task_dir = workspace / "job_template"
    submit_dir = workspace / "submit"
    sys.path.insert(0, str(task_dir))
    sys.path.insert(0, str(submit_dir))
    try:
        import calc_cost as task_cost
        from task_spec import (
            ALL_RAWDATA_FIELDS,
            COUNTERWEIGHT_BLOCK_SIZE_M,
            model_spec,
        )
    finally:
        sys.path.pop(0)
        sys.path.pop(0)
    rawdata_names = tuple(field[0] for field in ALL_RAWDATA_FIELDS)
    sample_rawdata = tuple(
        _load_payload(rawdata / f"{name}.npz") for name in rawdata_names
    )
    metrics = task_cost.extract_physical_metrics(sample_rawdata, parameters)
    spec = model_spec(parameters)
    title = args.title or f"King Arthur trebuchet — {job.name}"

    (
        trajectory,
        trajectory_metadata,
        axes,
        continuation_diagnostics,
        trajectory_path,
    ) = _generate_animation_trajectory(
        workspace=workspace,
        job=job,
        parameters=parameters,
        timeout=args.continuation_timeout,
        work_dir=args.work_dir,
    )
    child_diagnostics = continuation_diagnostics.get("child", {})

    channel_names = list(trajectory_metadata["channel_names"])
    channels = {name: trajectory[:, index] for index, name in enumerate(channel_names)}
    time_s = axes["axis_time_s"]

    impact_time = float(metrics["total_time_s"]) + float(metrics["flight_time_s"])
    replay_end = min(float(time_s[-1]), impact_time + 0.45)
    frame_times = np.arange(float(time_s[0]), replay_end + 0.5 / args.fps, 1.0 / args.fps)
    frame_indices = np.searchsorted(time_s, frame_times, side="left")
    frame_indices = np.clip(frame_indices, 0, time_s.size - 1)

    pivot = np.array((0.0, parameters["pivot_height_m"]))
    long_arm = parameters["long_arm_length_m"]
    short_arm = parameters["short_arm_length_m"]
    hanger_length = parameters["hanger_length_m"]
    arm_thickness = parameters["arm_height_m"]
    hanger_thickness = parameters["hanger_height_m"]
    counterweight_size = COUNTERWEIGHT_BLOCK_SIZE_M
    ball_radius = 0.0335

    ball_x = channels["ball_x_m"]
    ball_z = channels["ball_z_m"]
    visible_ball_x = ball_x[time_s <= replay_end]
    x_max = max(float(np.max(visible_ball_x)) + 0.8, 2.4)
    z_max = max(float(np.max(ball_z[time_s <= replay_end])) + 0.7, 2.8)
    x_min = min(float(np.min(visible_ball_x)) - 0.8, -2.4)
    mechanism_half_width = max(
        2.5,
        long_arm + spec.sling_length_m + 0.35,
        short_arm + hanger_length + counterweight_size + 0.35,
    )
    landing_side = (
        "+x"
        if metrics["signed_range_m"] > 0.0
        else "-x"
        if metrics["signed_range_m"] < 0.0
        else "none"
    )
    minimum_moving_clearance = min(
        float(
            child_diagnostics.get(
                "minimum_arm_ground_clearance_m",
                metrics["minimum_arm_ground_clearance_m"],
            )
        ),
        float(
            child_diagnostics.get(
                "minimum_hanger_ground_clearance_m",
                metrics["minimum_hanger_ground_clearance_m"],
            )
        ),
        float(
            child_diagnostics.get(
                "minimum_counterweight_ground_clearance_m",
                metrics["minimum_counterweight_ground_clearance_m"],
            )
        ),
    )

    plt.style.use("seaborn-v0_8-whitegrid")
    fig, (mechanism_ax, flight_ax) = plt.subplots(
        1,
        2,
        figsize=(14.4, 7.2),
        gridspec_kw={"width_ratios": (0.82, 1.55)},
    )
    fig.subplots_adjust(left=0.06, right=0.98, bottom=0.11, top=0.86, wspace=0.18)
    fig.suptitle(title, fontsize=17)
    subtitle = fig.text(
        0.5,
        0.89,
        "",
        ha="center",
        va="center",
        fontsize=11,
        color="#334155",
    )

    for axis in (mechanism_ax, flight_ax):
        axis.axhspan(-0.35, 0.0, color="#d6c6a5", alpha=0.58, zorder=0)
        axis.axhline(0.0, color="#5b4636", linewidth=1.5, zorder=1)
        axis.set_aspect("equal", adjustable="box")
        axis.set_xlabel("global x (m)")
        axis.set_ylabel("height z (m)")
        axis.grid(True, color="#dbe3ea", linewidth=0.7)

    mechanism_ax.set_title("mechanism detail")
    mechanism_ax.set_xlim(-mechanism_half_width, mechanism_half_width)
    mechanism_ax.set_ylim(-0.35, 2.7)
    flight_ax.set_title("complete ball trajectory")
    flight_ax.set_xlim(x_min, x_max)
    flight_ax.set_ylim(-0.35, z_max)

    def add_static_frame(axis: plt.Axes) -> None:
        leg_color = "#475569"
        base_half_width = 0.55
        axis.plot((-base_half_width, pivot[0]), (0.0, pivot[1]), color=leg_color, lw=5, zorder=2)
        axis.plot((base_half_width, pivot[0]), (0.0, pivot[1]), color=leg_color, lw=5, zorder=2)
        axis.plot((-0.72, 0.72), (0.0, 0.0), color=leg_color, lw=5, zorder=2)
        axis.add_patch(Circle(pivot, 0.06, facecolor="#e2e8f0", edgecolor="#1e293b", lw=2, zorder=8))
        runway_start, runway_end = axis.get_xlim()
        axis.plot(
            (runway_start, runway_end),
            (ball_radius, ball_radius),
            color="#64748b",
            lw=0.8,
            ls=":",
            zorder=1,
        )

    add_static_frame(mechanism_ax)
    add_static_frame(flight_ax)

    arm_patches: list[Polygon] = []
    hanger_patches: list[Polygon] = []
    counterweight_patches: list[Polygon] = []
    sling_lines = []
    ball_patches: list[Circle] = []
    for axis, display_ball_radius in ((mechanism_ax, 0.055), (flight_ax, 0.105)):
        arm_patch = Polygon(np.zeros((4, 2)), closed=True, facecolor="#b77935", edgecolor="#6b3f1d", lw=1.3, zorder=5)
        hanger_patch = Polygon(np.zeros((4, 2)), closed=True, facecolor="#d69e5c", edgecolor="#6b3f1d", lw=1.2, zorder=5)
        counterweight_patch = Polygon(np.zeros((4, 2)), closed=True, facecolor="#334155", edgecolor="#0f172a", lw=1.4, zorder=6)
        sling_line, = axis.plot([], [], color="#7c3aed", lw=1.5, zorder=4)
        ball_patch = Circle((ball_x[0], ball_z[0]), display_ball_radius, facecolor="#d8ff3e", edgecolor="#507000", lw=1.2, zorder=9)
        axis.add_patch(arm_patch)
        axis.add_patch(hanger_patch)
        axis.add_patch(counterweight_patch)
        axis.add_patch(ball_patch)
        arm_patches.append(arm_patch)
        hanger_patches.append(hanger_patch)
        counterweight_patches.append(counterweight_patch)
        sling_lines.append(sling_line)
        ball_patches.append(ball_patch)

    trail_line, = flight_ax.plot([], [], color="#e11d48", lw=2.0, alpha=0.9, zorder=3, label="tennis-ball path")
    flight_ax.legend(loc="upper right", framealpha=0.92)
    status_box = mechanism_ax.text(
        0.03,
        0.97,
        "",
        transform=mechanism_ax.transAxes,
        ha="left",
        va="top",
        fontsize=10,
        bbox={"boxstyle": "round,pad=0.45", "facecolor": "white", "edgecolor": "#cbd5e1", "alpha": 0.94},
        zorder=20,
    )
    metrics_box = flight_ax.text(
        0.02,
        0.97,
        (
            f"range  {metrics['range_m']:.2f} m\n"
            f"signed x  {metrics['signed_range_m']:+.2f} m\n"
            f"landing side  {landing_side}\n"
            f"release  {metrics['release_speed_mps']:.2f} m/s @ "
            f"{metrics['release_velocity_angle_deg']:.1f}°\n"
            f"moving mass  {metrics['moving_mass_kg']:.2f} kg\n"
            f"loaded height  {metrics['loaded_max_height_m']:.2f} m\n"
            f"min moving clearance  {minimum_moving_clearance:.3f} m\n"
            f"strength utilization  {metrics['peak_strength_utilization']:.3f}"
        ),
        transform=flight_ax.transAxes,
        ha="left",
        va="top",
        fontsize=9.5,
        bbox={"boxstyle": "round,pad=0.5", "facecolor": "white", "edgecolor": "#cbd5e1", "alpha": 0.94},
        zorder=20,
    )

    def update(frame_number: int):
        data_index = int(frame_indices[frame_number])
        current_time = float(time_s[data_index])
        arm_angle = math.radians(float(channels["arm_elevation_deg"][data_index]))
        hanger_angle = math.radians(float(channels["hanger_elevation_deg"][data_index]))
        arm_direction = np.array((math.cos(arm_angle), math.sin(arm_angle)))
        arm_tip = pivot + long_arm * arm_direction
        hanger_hinge = pivot - short_arm * arm_direction
        counterweight_center = hanger_hinge + hanger_length * np.array(
            (math.cos(hanger_angle), math.sin(hanger_angle))
        )
        current_ball = (float(ball_x[data_index]), float(ball_z[data_index]))

        arm_vertices = _member_polygon(tuple(arm_tip), tuple(hanger_hinge), arm_thickness)
        hanger_vertices = _member_polygon(tuple(hanger_hinge), tuple(counterweight_center), hanger_thickness)
        counterweight_vertices = _rotated_box(tuple(counterweight_center), counterweight_size, hanger_angle)
        sling_attached = bool(channels["sling_attached_flag"][data_index] > 0.5)
        arm_locked = bool(channels["arm_locked_flag"][data_index] > 0.5)

        for arm_patch, hanger_patch, counterweight_patch, sling_line, ball_patch in zip(
            arm_patches,
            hanger_patches,
            counterweight_patches,
            sling_lines,
            ball_patches,
            strict=True,
        ):
            arm_patch.set_xy(arm_vertices)
            hanger_patch.set_xy(hanger_vertices)
            counterweight_patch.set_xy(counterweight_vertices)
            ball_patch.center = current_ball
            if sling_attached:
                sling_line.set_data((arm_tip[0], current_ball[0]), (arm_tip[1], current_ball[1]))
            else:
                sling_line.set_data([], [])

        trail_line.set_data(ball_x[: data_index + 1], ball_z[: data_index + 1])
        if arm_locked:
            state = "1  counterweight fall\narm latched"
        elif sling_attached:
            state = "2  power stroke\nsling attached"
        elif current_time < impact_time:
            state = "3  ball flight\nsling released"
        else:
            state = "4  landed"
        status_box.set_text(state)
        subtitle.set_text(f"simulation time  {current_time:5.2f} s   •   {job.name}")
        return (
            *arm_patches,
            *hanger_patches,
            *counterweight_patches,
            *sling_lines,
            *ball_patches,
            trail_line,
            status_box,
            metrics_box,
            subtitle,
        )

    ffmpeg = _configure_ffmpeg()
    args.output.resolve().parent.mkdir(parents=True, exist_ok=True)
    args.poster.resolve().parent.mkdir(parents=True, exist_ok=True)
    movie = animation.FuncAnimation(
        fig,
        update,
        frames=len(frame_indices),
        interval=1000.0 / args.fps,
        blit=False,
    )
    writer = animation.FFMpegWriter(
        fps=args.fps,
        codec="libx264",
        bitrate=2600,
        extra_args=("-pix_fmt", "yuv420p", "-movflags", "+faststart"),
        metadata={"title": title},
    )
    movie.save(str(args.output.resolve()), writer=writer, dpi=args.dpi)

    poster_index = int(np.argmax(ball_z[: int(frame_indices[-1]) + 1]))
    poster_frame = int(np.argmin(np.abs(frame_indices - poster_index)))
    update(poster_frame)
    fig.savefig(args.poster.resolve(), dpi=args.dpi, bbox_inches="tight")
    plt.close(fig)

    print(f"job: {job}")
    print(f"title: {title}")
    print(f"ffmpeg: {ffmpeg}")
    print(f"frames: {len(frame_indices)} at {args.fps} fps")
    child = child_diagnostics
    print(
        "mechanism continuation: visualization-only PyChrono run "
        f"through {child.get('simulated_time_s', 'unknown')} s"
    )
    print(
        "minimum moving-part ground clearances (m): "
        f"arm={child.get('minimum_arm_ground_clearance_m', 'unknown')}, "
        f"hanger={child.get('minimum_hanger_ground_clearance_m', 'unknown')}, "
        "counterweight="
        f"{child.get('minimum_counterweight_ground_clearance_m', 'unknown')}"
    )
    print(f"animation trajectory: {trajectory_path.resolve()}")
    print(f"video: {args.output.resolve()}")
    print(f"poster: {args.poster.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
