"""Windows desktop controls for one yadof workspace and an HTCondor pool."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
from typing import Callable


STATUS_FIELDS = ("Name", "Machine", "Activity", "Cpus", "Memory", "Disk", "CpusUsage")
STATUS_COMMAND = ("condor_status", "-af:t", *STATUS_FIELDS)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass(frozen=True)
class SlotStatus:
    name: str
    machine: str
    activity: str
    cpus: str
    memory_mb: str
    disk_mb: str
    cpus_usage: str

    @property
    def display(self) -> tuple[str, ...]:
        return (
            self.name, self.activity, self.cpus, self.memory_mb,
            self.disk_mb, self.cpus_usage,
        )


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
        if len(values) != len(STATUS_FIELDS):
            continue
        name, machine, activity, cpus, memory, disk, usage = (v.strip() for v in values)
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
        ))
    return slots


def optimization_command(
    interpreter: str, workspace: Path, start_generation: int, generations: int
) -> list[str]:
    if start_generation < 0 or generations < 1:
        raise ValueError("起始代数必须 ≥ 0，运行代数必须 ≥ 1")
    return [
        interpreter, "-m", "yadof", "run", "--workspace", str(workspace),
        "--start-generation", str(start_generation), "--generations", str(generations),
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


def drain_machine(machine: str, *, run: Callable = subprocess.run) -> str:
    if not machine or any(char.isspace() for char in machine):
        raise ValueError("请选择有效的机器")
    result = run(
        ["condor_drain", "-graceful", machine], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=30, creationflags=NO_WINDOW,
    )
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or "condor_drain failed").strip())
    return (result.stdout or result.stderr or "Drain 请求已提交").strip()


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


def failure_lines(workspace: Path) -> list[str]:
    """Use the existing time tool's typed failure rows for the error view."""

    from .view_time import ViewTimeError, build_rows

    try:
        rows = [row for row in build_rows(workspace) if row["failed"]]
    except ViewTimeError as exc:
        if "No recorded timing rows" in str(exc):
            return []
        raise
    return [
        f"{row['event_time']}  {row['job_name']}  {row['error_type']}  "
        f"{row['error_message'] or '无详细信息'}"
        for row in rows
    ]


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
        self.slots: dict[str, SlotStatus] = {}
        self.workspace_var = tk.StringVar(value=str(workspace or Path.cwd()))
        self.start_var = tk.StringVar(value="0")
        self.generations_var = tk.StringVar(value="50")
        self.interval_var = tk.StringVar(value="10")
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

        ttk.Label(frame, text="工作区").grid(row=0, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.workspace_var).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(frame, text="浏览…", command=self.browse).grid(row=0, column=2)

        controls = ttk.Frame(frame)
        controls.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(12, 8))
        for label, variable, width in (
            ("起始代数", self.start_var, 7),
            ("总共运行代数", self.generations_var, 7),
            ("刷新间隔（秒）", self.interval_var, 6),
        ):
            ttk.Label(controls, text=label).pack(side="left", padx=(0, 5))
            ttk.Entry(controls, textvariable=variable, width=width).pack(side="left", padx=(0, 16))
        self.start_button = ttk.Button(controls, text="开始优化", command=self.start)
        self.start_button.pack(side="left", padx=4)
        self.stop_button = ttk.Button(controls, text="停止优化", command=self.stop, state="disabled")
        self.stop_button.pack(side="left", padx=4)

        bar = ttk.Frame(frame)
        bar.grid(row=2, column=0, columnspan=3, sticky="ew")
        ttk.Label(bar, textvariable=self.pool_var).pack(side="left")
        ttk.Button(bar, text="刷新", command=self.refresh).pack(side="right", padx=4)
        ttk.Button(bar, text="Drain 选中机器", command=self.drain).pack(side="right", padx=4)

        columns = ("Name", "Activity", "Cpus", "Memory(MB)", "Disk(MB)", "CpusUsage")
        self.tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
        for column in columns:
            self.tree.heading(column, text=column)
            self.tree.column(column, width=190 if column == "Name" else 120, anchor="w")
        self.tree.grid(row=3, column=0, columnspan=3, sticky="nsew")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        scroll.grid(row=3, column=3, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)

        views = ttk.Frame(frame)
        views.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(12, 5))
        for label, kind in (("viewcost", "cost"), ("viewtime", "time"), ("viewerror", "error")):
            ttk.Button(views, text=label, command=lambda k=kind: self.view(k)).pack(side="left", padx=(0, 8))
        ttk.Label(views, textvariable=self.state_var).pack(side="right")

        self.log = tk.Text(frame, height=10, state="disabled", wrap="word")
        self.log.grid(row=5, column=0, columnspan=3, sticky="nsew")
        log_scroll = ttk.Scrollbar(frame, orient="vertical", command=self.log.yview)
        log_scroll.grid(row=5, column=3, sticky="ns")
        self.log.configure(yscrollcommand=log_scroll.set)
        self.root.after(100, self._drain_events)
        self.root.after(0, self.refresh)
        self.root.after(10000, self._periodic_refresh)

    def _workspace(self) -> Path:
        path = Path(self.workspace_var.get()).expanduser().resolve()
        if not (path / ".yadof" / "workspace.json").is_file():
            raise ValueError("请选择含 .yadof/workspace.json 的 yadof 工作区")
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

        selected = filedialog.askdirectory(parent=self.root, initialdir=self.workspace_var.get())
        if selected:
            self.workspace_var.set(selected)

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
        try:
            workspace = self._workspace()
            start = self._integer(self.start_var.get(), 0, "起始代数")
            generations = self._integer(self.generations_var.get(), 1, "运行代数")
            command = optimization_command(_console_python(), workspace, start, generations)
        except ValueError as exc:
            self._error(str(exc))
            return
        if self.process is not None and self.process.poll() is None:
            self._error("已有优化进程正在运行")
            return
        self.start_button.configure(state="disabled")
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
        from tkinter import messagebox

        selected = self.tree.selection()
        if not selected:
            self._error("先选择一个 slot")
            return
        machine = self.slots[selected[0]].machine
        if not messagebox.askyesno(
            "确认 Drain", f"以 graceful 模式 Drain 整台机器 {machine}？",
            parent=self.root,
        ):
            return
        self.state_var.set(f"正在 Drain {machine}")
        threading.Thread(target=self._drain_worker, args=(machine,), daemon=True).start()

    def _drain_worker(self, machine: str) -> None:
        try:
            self.events.put(("drained", (machine, drain_machine(machine))))
        except Exception as exc:
            self.events.put(("drain_error", str(exc)))

    def view(self, kind: str) -> None:
        try:
            workspace = self._workspace()
        except ValueError as exc:
            self._error(str(exc))
            return
        self.state_var.set(f"正在生成 {kind}")
        threading.Thread(target=self._view_worker, args=(kind, workspace), daemon=True).start()

    def _view_worker(self, kind: str, workspace: Path) -> None:
        try:
            if kind == "error":
                self.events.put(("errors", failure_lines(workspace)))
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

    def _show_errors(self, lines: list[str]) -> None:
        if not lines:
            self._log("没有失败记录")
            self.state_var.set("没有失败记录")
            return
        window = self.tk.Toplevel(self.root)
        window.title(f"失败记录（{len(lines)}）")
        window.geometry("900x450")
        content = self.tk.Text(window, wrap="word")
        content.pack(fill="both", expand=True)
        content.insert("1.0", "\n\n".join(lines))
        content.configure(state="disabled")
        self.state_var.set(f"{len(lines)} 条失败记录")

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
                        self.tree.insert("", "end", iid=item_id, values=slot.display)
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
                    self.start_button.configure(state="disabled" if self.stopping else "normal")
                    self.stop_button.configure(state="disabled")
                    self.state_var.set(f"优化结束 · 退出码 {payload}")
                    self._log(f"优化退出码：{payload}")
                elif kind == "run_error":
                    self.process = None
                    self.start_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    self._error(f"无法启动优化：{payload}")
                elif kind == "log":
                    self._log(str(payload))
                elif kind == "stopped":
                    self.stopping = False
                    if self.process is None:
                        self.start_button.configure(state="normal")
                    self._log(str(payload))
                    self.state_var.set("已执行停止命令")
                elif kind in {"stop_error", "drain_error", "view_error"}:
                    self.stopping = False
                    if kind == "stop_error":
                        if self.process is None:
                            self.start_button.configure(state="normal")
                        elif self.process.poll() is None:
                            self.stop_button.configure(state="normal")
                    self._error(str(payload))
                elif kind == "drained":
                    machine, detail = payload
                    self._log(f"Drain {machine}：{detail}")
                    self.refresh()
                elif kind == "errors":
                    self._show_errors(payload)
                elif kind == "view":
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

        if self.stopping or (self.process is not None and self.process.poll() is None):
            messagebox.showinfo("yadof", "请等待停止操作和 condor_rm -all 完成后再关闭窗口。", parent=self.root)
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
