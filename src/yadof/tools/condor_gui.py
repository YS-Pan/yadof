"""Windows desktop controls for one yadof workspace and an HTCondor pool."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
from typing import Callable

from ..config import load_config


STATUS_FIELDS = (
    "Name", "Machine", "Activity", "Cpus", "Memory", "Disk", "CpusUsage", "MyAddress",
)
STATUS_COMMAND = ("condor_status", "-af:t", *STATUS_FIELDS)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
GENERATION_PROGRESS_LINE = re.compile(
    r"^\[yadof\] generation (?P<generation>\d+) \([^)]+\) \[[#.]+\] "
    r"(?P<completed>\d+)/(?P<total>\d+) "
    r"successful=\d+ errors=\d+ remaining=\d+$"
)
CONDOR_PENDING_LINE = re.compile(
    r"^\[yadof\] htcondor: pending=(?P<pending>\d+)/(?P<total>\d+)$"
)
DRAIN_MODES = ("graceful", "quick", "fast")


@dataclass(frozen=True)
class SlotStatus:
    name: str
    machine: str
    activity: str
    cpus: str
    memory_mb: str
    disk_mb: str
    cpus_usage: str
    my_address: str = ""

    @property
    def display(self) -> tuple[str, ...]:
        return (
            self.name, self.activity, self.cpus, self.memory_mb,
            self.disk_mb, self.cpus_usage,
        )

    @property
    def display_with_machine(self) -> tuple[str, ...]:
        return (self.name, self.machine, *self.display[1:])


@dataclass(frozen=True)
class FailureRow:
    event_time: datetime
    job_name: str
    worker: str
    error_type: str
    error_message: str
    job_dir: Path | None

    @property
    def display(self) -> tuple[str, ...]:
        return (
            self.event_time.isoformat(sep=" ", timespec="milliseconds"),
            self.worker,
            self.job_name,
            self.error_type,
            self.error_message or "无详细信息",
        )


FAILURE_COLUMNS = ("event_time", "worker", "job_name", "error_type", "error_message")
FAILURE_HEADERS = ("时间", "Worker", "Job", "错误类型", "错误信息")


def failure_sort_key(row: FailureRow, column: str):
    if column not in FAILURE_COLUMNS:
        raise ValueError(f"Unknown failure column: {column}")
    value = getattr(row, column)
    return value if column == "event_time" else str(value).casefold()


def _job_dir_for_name(jobs_dir: Path, job_name: str) -> Path | None:
    if not job_name or Path(job_name).name != job_name:
        return None
    root = jobs_dir.resolve()
    candidate = (root / job_name).resolve()
    return candidate if candidate.parent == root else None


@dataclass(frozen=True)
class GenerationProgress:
    generation_index: int
    completed: int
    total: int

    @property
    def label(self) -> str:
        return (
            f"第 {self.generation_index + 1} 代（索引 {self.generation_index}）"
            f" · 已完成 {self.completed}/{self.total} 个"
        )


def parse_generation_progress(line: str) -> GenerationProgress | None:
    match = GENERATION_PROGRESS_LINE.fullmatch(line.strip())
    if match is None:
        return None
    generation = int(match["generation"])
    completed = int(match["completed"])
    total = int(match["total"])
    if completed > total:
        return None
    return GenerationProgress(generation, completed, total)


@dataclass(frozen=True)
class CondorPendingProgress:
    pending: int
    total: int

    @property
    def completed(self) -> int:
        return self.total - self.pending


def parse_condor_pending_progress(line: str) -> CondorPendingProgress | None:
    match = CONDOR_PENDING_LINE.fullmatch(line.strip())
    if match is None:
        return None
    pending = int(match["pending"])
    total = int(match["total"])
    if total < 1 or pending > total:
        return None
    return CondorPendingProgress(pending=pending, total=total)


def _display_number(value: str, *, divisor: float = 1.0) -> str:
    if value.casefold() in {"undefined", "error", ""}:
        return "—"
    try:
        number = float(value) / divisor
    except ValueError:
        return "—"
    if not number == number or number in (float("inf"), float("-inf")):
        return "—"
    return f"{number:,.2f}".rstrip("0").rstrip(".")


def parse_status(output: str) -> list[SlotStatus]:
    """Parse tab-delimited ClassAd attributes without trusting column spacing."""

    slots: list[SlotStatus] = []
    for line in output.splitlines():
        values = line.split("\t")
        if len(values) not in {len(STATUS_FIELDS) - 1, len(STATUS_FIELDS)}:
            continue
        name, machine, activity, cpus, memory, disk, usage = (
            value.strip() for value in values[:7]
        )
        my_address = values[7].strip() if len(values) == len(STATUS_FIELDS) else ""
        if not name or not machine or machine.casefold() == "undefined":
            continue
        slots.append(SlotStatus(
            name=name,
            machine=machine,
            activity=activity or "—",
            cpus=_display_number(cpus),
            memory_mb=_display_number(memory),
            disk_mb=_display_number(disk, divisor=1024.0),
            cpus_usage=_display_number(usage),
            my_address=my_address,
        ))
    return slots


def optimization_command(
    interpreter: str, workspace: Path, start_generation: int, generations: int,
    *, smoke_test: bool = True,
) -> list[str]:
    if start_generation < 0 or generations < 1:
        raise ValueError("起始代数必须 ≥ 0，运行代数必须 ≥ 1")
    return [
        interpreter, "-m", "yadof", "run", "--workspace", str(workspace),
        "--start-generation", str(start_generation), "--generations", str(generations),
        "--smoke-test" if smoke_test else "--no-smoke-test",
    ]


def _console_python() -> str:
    executable = Path(sys.executable)
    if os.name == "nt" and executable.name.casefold() == "pythonw.exe":
        candidate = executable.with_name("python.exe")
        if candidate.is_file():
            return str(candidate)
    return str(executable)


def query_status(*, run: Callable = subprocess.run) -> list[SlotStatus]:
    result = run(
        STATUS_COMMAND, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=8, creationflags=NO_WINDOW,
    )
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or "condor_status failed").strip())
    return parse_status(result.stdout)


def _validate_machine(machine: str) -> None:
    if not machine or any(char.isspace() for char in machine):
        raise ValueError("请选择有效的机器")


def _valid_my_address(address: str | None) -> str | None:
    value = str(address or "").strip()
    if len(value) < 3 or not (value.startswith("<") and value.endswith(">")):
        return None
    if any(char in value for char in "\r\n\t"):
        return None
    return value


def _run_drain_command(
    options: tuple[str, ...], machine: str, my_address: str | None, *,
    success_message: str, run: Callable,
) -> str:
    kwargs = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": 30,
        "creationflags": NO_WINDOW,
    }
    result = run(["condor_drain", *options, machine], **kwargs)
    if result.returncode == 0:
        return (result.stdout or result.stderr or success_message).strip()

    primary_error = (result.stderr or result.stdout or "condor_drain failed").strip()
    address = _valid_my_address(my_address)
    lookup_failed = "can't find address for startd" in primary_error.casefold()
    if not address or not lookup_failed:
        raise RuntimeError(primary_error)

    fallback = run(["condor_drain", *options, address], **kwargs)
    if fallback.returncode:
        fallback_error = (
            fallback.stderr or fallback.stdout or "condor_drain MyAddress retry failed"
        ).strip()
        raise RuntimeError(f"{primary_error}；MyAddress 重试失败：{fallback_error}")
    detail = (fallback.stdout or fallback.stderr or success_message).strip()
    return f"Machine 名称查找失败，已通过 ClassAd MyAddress 重试：{detail}"


def drain_machine(
    machine: str, mode: str = "graceful", *, my_address: str | None = None,
    run: Callable = subprocess.run,
) -> str:
    _validate_machine(machine)
    if mode not in DRAIN_MODES:
        raise ValueError(f"Drain 模式必须是以下之一：{', '.join(DRAIN_MODES)}")
    return _run_drain_command(
        (f"-{mode}",), machine, my_address,
        success_message="Drain 请求已提交", run=run,
    )


def cancel_drain_machine(
    machine: str, *, my_address: str | None = None, run: Callable = subprocess.run,
) -> str:
    _validate_machine(machine)
    return _run_drain_command(
        ("-cancel",), machine, my_address,
        success_message="Drain 请求已取消", run=run,
    )


def stop_optimization(process: subprocess.Popen, *, run: Callable = subprocess.run) -> str:
    """Stop the launched process tree, then remove all queued Condor jobs."""

    errors: list[str] = []
    removal_message = ""
    try:
        if process.poll() is None:
            if os.name == "nt":
                result = run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                    timeout=30, creationflags=NO_WINDOW,
                )
                if result.returncode:
                    errors.append((result.stderr or result.stdout or "taskkill failed").strip())
            else:
                process.terminate()
    except (OSError, subprocess.TimeoutExpired) as exc:
        errors.append(f"无法停止优化进程：{exc}")
    try:
        result = run(
            ["condor_rm", "-all"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30, creationflags=NO_WINDOW,
        )
        if result.returncode:
            errors.append((result.stderr or result.stdout or "condor_rm failed").strip())
        else:
            removal_message = (result.stdout or "condor_rm -all 已执行").strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        errors.append(f"condor_rm -all：{exc}")
    if errors:
        raise RuntimeError("；".join(errors))
    return removal_message


def failure_rows(workspace: Path) -> list[FailureRow]:
    """Use the time tool's failure rows and the configured workspace jobs root."""

    from .view_time import ViewTimeError, build_rows

    try:
        rows = [row for row in build_rows(workspace) if row["failed"]]
    except ViewTimeError as exc:
        if "No recorded timing rows" in str(exc):
            return []
        raise
    if not rows:
        return []
    jobs_dir = load_config(workspace).workspace.jobs_dir
    return [FailureRow(
        event_time=row["event_time"],
        job_name=str(row["job_name"]),
        worker=str(row.get("computer") or "unknown"),
        error_type=str(row["error_type"]),
        error_message=str(row["error_message"] or ""),
        job_dir=_job_dir_for_name(jobs_dir, str(row["job_name"])),
    ) for row in rows]


class CondorGUI:
    def __init__(self, root, workspace: Path | None = None) -> None:
        import tkinter as tk
        from tkinter import ttk

        self.root = root
        self.tk = tk
        self.ttk = ttk
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.process: subprocess.Popen | None = None
        self.poll_busy = False
        self.stopping = False
        self.running = False
        self.initializing = False
        self.clearing = False
        self.viewing = False
        self.progress_generation_index: int | None = None
        self.progress_phase = "waiting"
        self.slots: dict[str, SlotStatus] = {}
        self.workspace_var = tk.StringVar(value=str(workspace or Path.cwd() / "workspace"))
        self.start_var = tk.StringVar(value="0")
        self.generations_var = tk.StringVar(value="50")
        self.interval_var = tk.StringVar(value="10")
        self.smoke_var = tk.BooleanVar(value=True)
        self.progress_var = tk.StringVar(value="尚未启动优化")
        self.state_var = tk.StringVar(value="就绪")
        self.pool_var = tk.StringVar(value="Condor：等待查询")
        root.title("yadof · HTCondor 控制台")
        root.geometry("1050x720")
        root.minsize(800, 560)
        root.protocol("WM_DELETE_WINDOW", self.close)

        frame = ttk.Frame(root, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(3, weight=1)
        frame.rowconfigure(5, weight=1)

        ttk.Label(frame, text="文件夹").grid(row=0, column=0, sticky="w")
        self.workspace_entry = ttk.Entry(frame, textvariable=self.workspace_var)
        self.workspace_entry.grid(row=0, column=1, sticky="ew", padx=8)
        workspace_actions = ttk.Frame(frame)
        workspace_actions.grid(row=0, column=2)
        self.workspace_button = ttk.Button(
            workspace_actions, text="选择文件夹…", command=self.browse,
        )
        self.workspace_button.pack(side="left", padx=(0, 8))
        self.init_button = ttk.Button(
            workspace_actions, text="初始化 workspace", command=self.initialize_workspace,
        )
        self.init_button.pack(side="left", padx=(0, 8))
        self.clear_button = ttk.Button(
            workspace_actions, text="清空 workspace", command=self.clear_workspace,
        )
        self.clear_button.pack(side="left")

        controls = ttk.Frame(frame)
        controls.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(12, 8))
        settings = ttk.Frame(controls)
        settings.pack(anchor="w")
        for label, variable, width in (
            ("起始代数", self.start_var, 7),
            ("总共运行代数", self.generations_var, 7),
            ("刷新间隔（秒）", self.interval_var, 6),
        ):
            ttk.Label(settings, text=label).pack(side="left", padx=(0, 5))
            ttk.Entry(settings, textvariable=variable, width=width).pack(side="left", padx=(0, 16))
        actions = ttk.Frame(controls)
        actions.pack(fill="x", pady=(8, 0))
        ttk.Checkbutton(
            actions, text="启用 smoke job", variable=self.smoke_var,
        ).pack(side="left", padx=(0, 16))
        self.start_button = ttk.Button(actions, text="开始优化", command=self.start)
        self.start_button.pack(side="left", padx=4)
        self.stop_button = ttk.Button(actions, text="停止优化", command=self.stop, state="disabled")
        self.stop_button.pack(side="left", padx=4)

        progress_row = ttk.Frame(controls)
        progress_row.pack(fill="x", pady=(10, 0))
        self.generation_bar = ttk.Progressbar(
            progress_row, orient="horizontal", mode="determinate", maximum=1,
        )
        self.generation_bar.pack(side="left", fill="x", expand=True)
        ttk.Label(
            progress_row, textvariable=self.progress_var, width=38, anchor="w",
        ).pack(side="left", padx=(10, 0))

        bar = ttk.Frame(frame)
        bar.grid(row=2, column=0, columnspan=3, sticky="ew")
        ttk.Label(bar, textvariable=self.pool_var).pack(side="left")
        ttk.Button(bar, text="刷新", command=self.refresh).pack(side="right", padx=4)
        ttk.Button(bar, text="取消 Drain 选中机器", command=self.cancel_drain).pack(side="right", padx=4)
        ttk.Button(bar, text="Drain 选中机器", command=self.drain).pack(side="right", padx=4)

        columns = ("Name", "Machine", "Activity", "Cpus", "Memory(MB)", "Disk(MB)", "CpusUsage")
        self.tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
        for column in columns:
            self.tree.heading(column, text=column)
            self.tree.column(column, width=150 if column in {"Name", "Machine"} else 110, anchor="w")
        self.tree.grid(row=3, column=0, columnspan=3, sticky="nsew")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        scroll.grid(row=3, column=3, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)

        views = ttk.Frame(frame)
        views.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(12, 5))
        self.view_buttons = []
        for label, kind in (("viewcost", "cost"), ("viewtime", "time"), ("viewerror", "error")):
            button = ttk.Button(views, text=label, command=lambda k=kind: self.view(k))
            button.pack(side="left", padx=(0, 8))
            self.view_buttons.append(button)
        ttk.Label(views, textvariable=self.state_var).pack(side="right")

        self.log = tk.Text(frame, height=10, state="disabled", wrap="word")
        self.log.grid(row=5, column=0, columnspan=3, sticky="nsew")
        log_scroll = ttk.Scrollbar(frame, orient="vertical", command=self.log.yview)
        log_scroll.grid(row=5, column=3, sticky="ns")
        self.log.configure(yscrollcommand=log_scroll.set)
        self.root.after(100, self._drain_events)
        self.root.after(0, self.refresh)
        self.root.after(10000, self._periodic_refresh)

    def _workspace_path(self) -> Path:
        if not self.workspace_var.get().strip():
            raise ValueError("请先选择文件夹")
        return Path(self.workspace_var.get()).expanduser().resolve()

    def _workspace(self) -> Path:
        path = self._workspace_path()
        if not (path / ".yadof" / "workspace.json").is_file():
            raise ValueError("当前文件夹尚未初始化为 workspace，请点击“初始化 workspace”")
        return path

    def _integer(self, value: str, minimum: int, label: str) -> int:
        try:
            number = int(value)
        except ValueError as exc:
            raise ValueError(f"{label}必须是整数") from exc
        if number < minimum:
            raise ValueError(f"{label}必须 ≥ {minimum}")
        return number

    def _log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _error(self, message: str) -> None:
        from tkinter import messagebox

        self.state_var.set("错误")
        self._log(message)
        messagebox.showerror("yadof", message, parent=self.root)

    def browse(self) -> None:
        from tkinter import filedialog

        if self._workspace_busy():
            return
        selected = filedialog.askdirectory(
            parent=self.root, title="选择文件夹",
            initialdir=self.workspace_var.get(), mustexist=True,
        )
        if not selected:
            return
        try:
            workspace = Path(selected).expanduser().resolve()
        except (OSError, ValueError) as exc:
            self._error(str(exc))
            return
        self.workspace_var.set(str(workspace))
        self.state_var.set("已选择文件夹")
        self._log(f"已选择文件夹：{workspace}")

    def initialize_workspace(self) -> None:
        if self._workspace_busy():
            self._error("请等待当前操作完成，再初始化 workspace")
            return
        try:
            workspace = self._workspace_path()
        except (OSError, ValueError) as exc:
            self._error(str(exc))
            return
        self.initializing = True
        self._update_workspace_controls()
        self.state_var.set("正在初始化 workspace")
        self._log("初始化：" + subprocess.list2cmdline([
            _console_python(), "-m", "yadof", "init", str(workspace),
        ]))
        threading.Thread(target=self._init_worker, args=(workspace,), daemon=True).start()

    def _init_worker(self, workspace: Path) -> None:
        try:
            environment = os.environ.copy()
            environment["PYTHONIOENCODING"] = "utf-8"
            result = subprocess.run(
                [_console_python(), "-m", "yadof", "init", str(workspace)],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", env=environment,
                creationflags=NO_WINDOW,
            )
            if result.returncode:
                detail = result.stdout.strip() or f"退出码 {result.returncode}"
                self.events.put(("init_error", detail))
            else:
                self.events.put(("workspace_initialized", (workspace, result.stdout)))
        except Exception as exc:
            self.events.put(("init_error", str(exc)))

    def _workspace_busy(self) -> bool:
        return self.running or self.stopping or self.initializing or self.clearing or self.viewing

    def _update_workspace_controls(self) -> None:
        state = "disabled" if self._workspace_busy() else "normal"
        for widget in (
            self.workspace_entry, self.workspace_button, self.init_button, self.clear_button,
            self.start_button,
        ):
            widget.configure(state=state)
        for button in self.view_buttons:
            button.configure(
                state="disabled" if self.initializing or self.clearing or self.viewing else "normal",
            )

    def clear_workspace(self) -> None:
        from tkinter import messagebox

        if self._workspace_busy():
            self._error("请先停止优化并等待当前操作完成，再清空 workspace")
            return
        try:
            workspace = self._workspace()
            context = load_config(workspace).workspace
        except Exception as exc:
            self._error(str(exc))
            return
        if not messagebox.askyesno(
            "清空 workspace",
            f"确定清空当前 workspace？\n{workspace}\n\n"
            f"将永久删除以下目录中的所有数据：\n"
            f"jobs：{context.jobs_dir}\n"
            f"recorded_data（含 metadata 和代理训练记录）：{context.recorded_data_dir}\n"
            f"代理 checkpoint：{context.surrogate_checkpoint_dir}\n"
            f"优化续跑状态：{workspace / '.yadof' / 'optimization'}\n\n"
            "保留 config.py、submit、job_template 和工作区标记。\n"
            "此操作无法撤销；完成后起始代数重置为 0。",
            parent=self.root, icon="warning", default=messagebox.NO,
        ):
            return
        self.clearing = True
        self._update_workspace_controls()
        self.state_var.set("正在清空 workspace")
        self._log(f"清空 workspace：{workspace}")
        threading.Thread(target=self._clear_worker, args=(workspace,), daemon=True).start()

    def _clear_worker(self, workspace: Path) -> None:
        from .history import clear_history

        try:
            result = clear_history(workspace, confirm=True, all_recorded_data=True)
            self.events.put(("workspace_cleared", result))
        except Exception as exc:
            self.events.put(("clear_error", str(exc)))

    def refresh(self) -> None:
        if self.poll_busy:
            return
        self.poll_busy = True
        threading.Thread(target=self._status_worker, daemon=True).start()

    def _status_worker(self) -> None:
        try:
            self.events.put(("slots", query_status()))
        except Exception as exc:
            self.events.put(("status_error", str(exc)))

    def _periodic_refresh(self) -> None:
        try:
            seconds = self._integer(self.interval_var.get(), 1, "刷新间隔")
        except ValueError:
            seconds = 10
        self.refresh()
        self.root.after(seconds * 1000, self._periodic_refresh)

    def start(self) -> None:
        if self._workspace_busy():
            self._error("请等待当前操作完成后再开始优化")
            return
        try:
            workspace = self._workspace()
            start = self._integer(self.start_var.get(), 0, "起始代数")
            generations = self._integer(self.generations_var.get(), 1, "运行代数")
            command = optimization_command(
                _console_python(), workspace, start, generations,
                smoke_test=self.smoke_var.get(),
            )
        except ValueError as exc:
            self._error(str(exc))
            return
        if self.process is not None and self.process.poll() is None:
            self._error("已有优化进程正在运行")
            return
        self.generation_bar.configure(maximum=1, value=0)
        self.progress_generation_index = start
        self.progress_phase = "smoke" if self.smoke_var.get() else "generation"
        self.progress_var.set(f"等待第 {start + 1} 代（索引 {start}）")
        self.running = True
        self._update_workspace_controls()
        self.state_var.set("正在启动优化")
        self._log("开始：" + subprocess.list2cmdline(command))
        threading.Thread(target=self._run_worker, args=(command, workspace), daemon=True).start()

    def _run_worker(self, command: list[str], workspace: Path) -> None:
        try:
            process = subprocess.Popen(
                command, cwd=workspace, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
                creationflags=NO_WINDOW,
            )
            self.events.put(("run_started", process))
            assert process.stdout is not None
            for line in process.stdout:
                self.events.put(("log", line))
            self.events.put(("run_finished", process.wait()))
        except Exception as exc:
            self.events.put(("run_error", str(exc)))

    def stop(self) -> None:
        if self.process is None or self.stopping:
            return
        self.stopping = True
        self.stop_button.configure(state="disabled")
        self.state_var.set("正在停止并执行 condor_rm -all")
        threading.Thread(target=self._stop_worker, args=(self.process,), daemon=True).start()

    def _stop_worker(self, process: subprocess.Popen) -> None:
        try:
            self.events.put(("stopped", stop_optimization(process)))
        except Exception as exc:
            self.events.put(("stop_error", str(exc)))

    def drain(self) -> None:
        selected = self.tree.selection()
        if not selected:
            self._error("先选择一个 slot")
            return
        machine = self.slots[selected[0]].machine
        mode = self._choose_drain_mode(machine)
        if mode is None:
            return
        self.state_var.set(f"正在以 {mode} 模式 Drain {machine}")
        my_address = self.slots[selected[0]].my_address
        threading.Thread(
            target=self._drain_worker,
            args=(machine, mode, my_address),
            daemon=True,
        ).start()

    def _choose_drain_mode(self, machine: str) -> str | None:
        window = self.tk.Toplevel(self.root)
        window.title("选择 Drain 模式")
        window.transient(self.root)
        window.resizable(False, False)
        mode_var = self.tk.StringVar(master=window, value="graceful")
        selected: dict[str, str | None] = {"mode": None}
        frame = self.ttk.Frame(window, padding=12)
        frame.pack(fill="both", expand=True)
        self.ttk.Label(
            frame, text=f"选择机器 {machine} 的 Drain 模式：",
        ).pack(anchor="w", pady=(0, 8))
        descriptions = (
            ("graceful", "遵守作业 retirement 时间并协调逐步退出"),
            ("quick", "忽略 retirement 时间，但保留通常的 vacate 时间"),
            ("fast", "立即强制结束作业，不等待正常退出"),
        )
        for mode, description in descriptions:
            self.ttk.Radiobutton(
                frame,
                text=f"{mode} — {description}",
                value=mode,
                variable=mode_var,
            ).pack(anchor="w", pady=2)
        buttons = self.ttk.Frame(frame)
        buttons.pack(fill="x", pady=(12, 0))

        def confirm() -> None:
            selected["mode"] = mode_var.get()
            window.destroy()

        self.ttk.Button(
            buttons, text="开始 Drain", command=confirm,
        ).pack(side="right", padx=(6, 0))
        self.ttk.Button(buttons, text="取消", command=window.destroy).pack(side="right")
        window.protocol("WM_DELETE_WINDOW", window.destroy)
        window.grab_set()
        window.wait_window()
        return selected["mode"]

    def _drain_worker(
        self, machine: str, mode: str = "graceful", my_address: str | None = None,
    ) -> None:
        try:
            detail = drain_machine(machine, mode, my_address=my_address)
            self.events.put(("drained", (machine, mode, detail)))
        except Exception as exc:
            self.events.put(("drain_error", str(exc)))

    def cancel_drain(self) -> None:
        selected = self.tree.selection()
        if not selected:
            self._error("先选择一个 slot")
            return
        slot = self.slots[selected[0]]
        machine = slot.machine
        self.state_var.set(f"正在取消 {machine} 的 Drain")
        threading.Thread(
            target=self._cancel_drain_worker,
            args=(machine, slot.my_address),
            daemon=True,
        ).start()

    def _cancel_drain_worker(self, machine: str, my_address: str | None = None) -> None:
        try:
            detail = cancel_drain_machine(machine, my_address=my_address)
            self.events.put(("drain_cancelled", (machine, detail)))
        except Exception as exc:
            self.events.put(("drain_cancel_error", str(exc)))

    def view(self, kind: str) -> None:
        if self.initializing or self.clearing or self.viewing:
            return
        try:
            workspace = self._workspace()
        except ValueError as exc:
            self._error(str(exc))
            return
        self.viewing = True
        self._update_workspace_controls()
        self.state_var.set(f"正在生成 {kind}")
        threading.Thread(target=self._view_worker, args=(kind, workspace), daemon=True).start()

    def _view_worker(self, kind: str, workspace: Path) -> None:
        try:
            if kind == "error":
                self.events.put(("errors", failure_rows(workspace)))
                return
            import matplotlib

            matplotlib.use("Agg")
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            if kind == "cost":
                from .cost_viewer import view_cost

                summary, output = view_cost(workspace, output_path=f"cost_{stamp}.png")
            else:
                from .view_time import view_time

                summary, output = view_time(workspace, output_path=f"time_{stamp}.png")
            self.events.put(("view", (kind, summary, output)))
        except Exception as exc:
            self.events.put(("view_error", str(exc)))

    def _show_errors(self, rows: list[FailureRow]) -> None:
        if not rows:
            self._log("没有失败记录")
            self.state_var.set("没有失败记录")
            return
        window = self.tk.Toplevel(self.root)
        window.title(f"失败记录（{len(rows)}）")
        window.geometry("1200x500")
        frame = self.ttk.Frame(window, padding=8)
        frame.pack(fill="both", expand=True)
        self.ttk.Label(frame, text="双击记录可打开对应的 jobs 文件夹").pack(anchor="w", pady=(0, 6))
        table_frame = self.ttk.Frame(frame)
        table_frame.pack(fill="both", expand=True)
        table = self.ttk.Treeview(table_frame, columns=FAILURE_COLUMNS, show="headings")
        for column, header, width in zip(FAILURE_COLUMNS, FAILURE_HEADERS, (185, 145, 260, 130, 500)):
            table.heading(column, text=header)
            table.column(column, width=width, stretch=column == "error_message", anchor="w")
        vertical = self.ttk.Scrollbar(table_frame, orient="vertical", command=table.yview)
        horizontal = self.ttk.Scrollbar(table_frame, orient="horizontal", command=table.xview)
        table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        table.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        indexed_rows = {str(index): row for index, row in enumerate(rows)}
        for item_id, row in indexed_rows.items():
            table.insert("", "end", iid=item_id, values=row.display)

        current_sort = ("event_time", False)

        def sort_by(column: str) -> None:
            nonlocal current_sort
            descending = not current_sort[1] if current_sort[0] == column else False
            ordered = sorted(indexed_rows, key=lambda item_id: failure_sort_key(indexed_rows[item_id], column),
                             reverse=descending)
            for position, item_id in enumerate(ordered):
                table.move(item_id, "", position)
            current_sort = (column, descending)
            for key, header in zip(FAILURE_COLUMNS, FAILURE_HEADERS):
                suffix = " ↓" if key == column and descending else " ↑" if key == column else ""
                table.heading(key, text=header + suffix)

        for column in FAILURE_COLUMNS:
            table.heading(column, command=lambda key=column: sort_by(key))
        sort_by("event_time")

        def open_selected(event) -> None:
            if table.identify_region(event.x, event.y) != "cell":
                return
            item_id = table.identify_row(event.y)
            if not item_id:
                return
            row = indexed_rows[item_id]
            if row.job_dir is None or not row.job_dir.is_dir():
                self._error(f"找不到 {row.job_name} 的 jobs 文件夹")
                return
            try:
                os.startfile(row.job_dir)  # type: ignore[attr-defined]
            except OSError as exc:
                self._error(f"无法打开 jobs 文件夹：{exc}")

        table.bind("<Double-1>", open_selected)
        self.state_var.set(f"{len(rows)} 条失败记录")

    def _drain_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "slots":
                    selected = self.tree.selection()
                    selected_name = self.slots[selected[0]].name if selected else None
                    self.tree.delete(*self.tree.get_children())
                    self.slots = {}
                    for index, slot in enumerate(payload):
                        item_id = str(index)
                        self.tree.insert("", "end", iid=item_id, values=slot.display_with_machine)
                        self.slots[item_id] = slot
                        if slot.name == selected_name:
                            self.tree.selection_set(item_id)
                    self.poll_busy = False
                    self.pool_var.set(f"Condor：{len(self.slots)} 个 slots · {datetime.now():%H:%M:%S}")
                elif kind == "status_error":
                    self.poll_busy = False
                    self.pool_var.set("Condor 查询失败")
                    self._log(f"condor_status：{payload}")
                elif kind == "run_started":
                    self.process = payload
                    self.stop_button.configure(state="normal")
                    self.state_var.set(f"优化运行中 · PID {payload.pid}")
                elif kind == "run_finished":
                    self.process = None
                    self.running = False
                    self._update_workspace_controls()
                    self.stop_button.configure(state="disabled")
                    self.state_var.set(f"优化结束 · 退出码 {payload}")
                    self._log(f"优化退出码：{payload}")
                elif kind == "run_error":
                    self.process = None
                    self.running = False
                    self._update_workspace_controls()
                    self.stop_button.configure(state="disabled")
                    self._error(f"无法启动优化：{payload}")
                elif kind == "log":
                    line = str(payload)
                    progress = parse_generation_progress(line)
                    pending = parse_condor_pending_progress(line)
                    if progress is not None:
                        self.progress_phase = "generation"
                        self.progress_generation_index = progress.generation_index
                        self.generation_bar.configure(
                            maximum=max(1, progress.total), value=progress.completed,
                        )
                        self.progress_var.set(progress.label)
                    elif pending is not None:
                        self.generation_bar.configure(
                            maximum=pending.total, value=pending.completed,
                        )
                        if self.progress_phase == "smoke":
                            label = f"Smoke job · Condor 待完成 {pending.pending}/{pending.total} 个"
                        elif self.progress_generation_index is None:
                            label = f"当前批次 · Condor 待完成 {pending.pending}/{pending.total} 个"
                        else:
                            index = self.progress_generation_index
                            label = (
                                f"第 {index + 1} 代（索引 {index}） · "
                                f"Condor 待完成 {pending.pending}/{pending.total} 个"
                            )
                        self.progress_var.set(label)
                    elif line.startswith("Starting real-task smoke test"):
                        self.progress_phase = "smoke"
                        self.progress_var.set("Smoke job 进行中 · 本代尚未开始")
                    self._log(line)
                elif kind == "stopped":
                    self.stopping = False
                    self._update_workspace_controls()
                    self._log(str(payload))
                    self.state_var.set("已执行停止命令")
                elif kind in {
                    "stop_error", "drain_error", "drain_cancel_error", "view_error",
                    "clear_error", "init_error",
                }:
                    if kind == "stop_error":
                        self.stopping = False
                        if self.process is not None and self.process.poll() is None:
                            self.stop_button.configure(state="normal")
                    elif kind == "view_error":
                        self.viewing = False
                    elif kind == "clear_error":
                        self.clearing = False
                        payload = f"清空失败（可能已清理部分数据，请检查后重试）：{payload}"
                    elif kind == "init_error":
                        self.initializing = False
                        payload = f"初始化 workspace 失败：{payload}"
                    self._update_workspace_controls()
                    self._error(str(payload))
                elif kind == "workspace_initialized":
                    workspace, output = payload
                    self.initializing = False
                    self._update_workspace_controls()
                    self.state_var.set("workspace 已初始化")
                    self._log(str(output))
                    self._log(f"当前 workspace：{workspace}")
                elif kind == "workspace_cleared":
                    self.clearing = False
                    self.start_var.set("0")
                    self.progress_generation_index = None
                    self.progress_phase = "waiting"
                    self.generation_bar.configure(maximum=1, value=0)
                    self.progress_var.set("尚未启动优化")
                    self._update_workspace_controls()
                    self.state_var.set("workspace 已清空，可从第 0 代重新优化")
                    self._log(f"workspace 已清空：{payload['workspace']}")
                elif kind == "drained":
                    machine, mode, detail = payload
                    self._log(f"Drain {machine}（{mode}）：{detail}")
                    self.state_var.set(f"已提交 {mode} Drain 请求：{machine}")
                    self.refresh()
                elif kind == "drain_cancelled":
                    machine, detail = payload
                    self._log(f"取消 Drain {machine}：{detail}")
                    self.state_var.set(f"已提交取消 Drain 请求：{machine}")
                    self.refresh()
                elif kind == "errors":
                    self.viewing = False
                    self._update_workspace_controls()
                    self._show_errors(payload)
                elif kind == "view":
                    self.viewing = False
                    self._update_workspace_controls()
                    view_kind, summary, output = payload
                    self._log(f"{view_kind}：\n{summary}\n图片：{output}")
                    self.state_var.set(f"{view_kind} 已生成")
                    if output is not None and os.name == "nt":
                        try:
                            os.startfile(output)  # type: ignore[attr-defined]
                        except OSError as exc:
                            self._log(f"无法打开图片：{exc}")
        except queue.Empty:
            pass
        self.root.after(100, self._drain_events)

    def close(self) -> None:
        from tkinter import messagebox

        if self._workspace_busy():
            messagebox.showinfo("yadof", "请先停止优化，并等待当前操作完成后再关闭窗口。", parent=self.root)
            return
        self.root.destroy()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="yadof HTCondor desktop controls")
    parser.add_argument("--workspace", type=Path, default=None)
    args = parser.parse_args(argv)
    import tkinter as tk

    root = tk.Tk()
    CondorGUI(root, args.workspace)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
