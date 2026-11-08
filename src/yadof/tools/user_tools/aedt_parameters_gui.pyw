"""Double-click AEDT OptimizationSetup1 exporter using its owning installation."""
from __future__ import annotations

from pathlib import Path
import os
import subprocess
import sys


def _runtime(launcher: Path) -> Path:
    site_packages = next((parent for parent in launcher.resolve().parents if parent.name == "site-packages"), None)
    if site_packages is None:
        raise FileNotFoundError("Open aedt_parameters_gui.pyw from the installed user_tools folder.")
    prefix = site_packages.parent
    if prefix.name.lower() == "lib":
        prefix = prefix.parent
    for candidate in (prefix / "Scripts/pythonw.exe", prefix / "pythonw.exe"):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("Cannot find the Python runtime belonging to this yadof installation.")


def _forward_to_runtime() -> int | None:
    script = Path(__file__).resolve()
    runtime = _runtime(script)
    if Path(sys.executable).resolve().parent != runtime.parent:
        return subprocess.call([str(runtime), str(script), *sys.argv[1:]])
    return None


if __name__ == "__main__":
    forwarded = _forward_to_runtime()
    if forwarded is not None:
        raise SystemExit(forwarded)


import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from yadof.tools.user_tools.aedt_parameters.parameter_extraction import (
    OptParam,
    ParameterExtractionResult,
    _format_ranges,
    export_aedt_parameters,
    read_aedt_parameters,
)


class AedtParametersApp:
    def __init__(self, root: tk.Tk, *, script_dir: Path) -> None:
        self.root = root
        self.default_backup = script_dir / "parameters_backup"
        self.project = tk.StringVar(master=root)
        self.backup = tk.StringVar(master=root, value=str(self.default_backup))
        self.output = tk.StringVar(master=root, value="输出到 AEDT 文件所在目录")
        self.status = tk.StringVar(master=root, value="请选择 AEDT 文件，可先预览优化变量。")
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.busy = False
        self.controls: list[ttk.Widget] = []

        root.title("AEDT 优化变量 → yadof 参数文件")
        root.geometry("880x540")
        root.minsize(680, 420)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        frame = ttk.Frame(root, padding=18)
        frame.grid(sticky="nsew")
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(5, weight=1)

        ttk.Label(frame, text="AEDT 文件：").grid(row=0, column=0, sticky="w", pady=6)
        entry = ttk.Entry(frame, textvariable=self.project)
        entry.grid(row=0, column=1, sticky="ew", padx=8)
        browse = ttk.Button(frame, text="浏览...", command=self._browse_project)
        browse.grid(row=0, column=2)
        ttk.Label(frame, text="备份目录：").grid(row=1, column=0, sticky="w", pady=6)
        backup_entry = ttk.Entry(frame, textvariable=self.backup)
        backup_entry.grid(row=1, column=1, sticky="ew", padx=8)
        backup_browse = ttk.Button(frame, text="浏览...", command=self._browse_backup)
        backup_browse.grid(row=1, column=2)
        self.controls.extend((entry, browse, backup_entry, backup_browse))
        ttk.Label(frame, text="输出文件：").grid(row=2, column=0, sticky="w", pady=6)
        ttk.Label(frame, textvariable=self.output, wraplength=650).grid(
            row=2, column=1, columnspan=2, sticky="w", padx=8,
        )
        ttk.Label(
            frame, text="仅提取 OptimizationSetup1 中勾选 Include 的变量。新文件 CONSTRAINTS 为空；旧文件会备份。",
            wraplength=780,
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 12))
        actions = ttk.Frame(frame)
        actions.grid(row=4, column=0, columnspan=3, sticky="w", pady=(0, 10))
        preview = ttk.Button(actions, text="预览变量", command=lambda: self._start("preview"))
        preview.pack(side="left", padx=(0, 10))
        generate = ttk.Button(actions, text="备份并生成", command=lambda: self._start("export"))
        generate.pack(side="left")
        self.controls.extend((preview, generate))

        table = ttk.Frame(frame)
        table.grid(row=5, column=0, columnspan=3, sticky="nsew")
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        self.variables = ttk.Treeview(table, columns=("name", "ranges", "unit"), show="headings")
        for key, label, width in (("name", "优化变量", 220), ("ranges", "范围 / 离散取值", 390), ("unit", "单位", 90)):
            self.variables.heading(key, text=label)
            self.variables.column(key, width=width, minwidth=70, anchor="w")
        self.variables.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(table, orient="vertical", command=self.variables.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(table, orient="horizontal", command=self.variables.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.variables.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        ttk.Label(frame, textvariable=self.status, wraplength=780).grid(
            row=6, column=0, columnspan=3, sticky="w", pady=(12, 0),
        )
        self.project.trace_add("write", self._project_changed)
        root.protocol("WM_DELETE_WINDOW", self._close)
        self._poll_id = root.after(100, self._poll)
        entry.focus_set()

    def _browse_project(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self.root, title="选择 AEDT 文件",
            filetypes=[("AEDT 工程文件", "*.aedt"), ("所有文件", "*.*")],
        )
        if selected:
            self.project.set(selected)

    def _browse_backup(self) -> None:
        selected = filedialog.askdirectory(parent=self.root, title="选择备份目录", mustexist=False)
        if selected:
            self.backup.set(selected)

    def _project_changed(self, *_args: str) -> None:
        raw = self.project.get().strip().strip('"')
        self.output.set(str(Path(raw).parent / "parameters_constraints.py") if raw else "输出到 AEDT 文件所在目录")
        self._clear_preview()
        self.status.set("请选择预览变量，或直接备份并生成。")

    def _clear_preview(self) -> None:
        self.variables.delete(*self.variables.get_children())

    def _start(self, action: str) -> None:
        if self.busy:
            return
        project, backup = self.project.get().strip(), self.backup.get().strip()
        if not project:
            messagebox.showerror("路径为空", "请浏览选择或手动输入 AEDT 文件路径。", parent=self.root)
            return
        if not backup:
            backup = str(self.default_backup)
            self.backup.set(backup)
        self.busy = True
        self._clear_preview()
        for control in self.controls:
            control.configure(state="disabled")
        self.status.set("正在读取 AEDT 文件…" if action == "preview" else "正在解析、备份并生成参数文件…")

        def work() -> None:
            try:
                result = (read_aedt_parameters(project) if action == "preview" else
                          export_aedt_parameters(project, backup_dir=backup))
                self.events.put((action, result))
            except Exception as exc:
                self.events.put(("error", exc))

        threading.Thread(target=work, daemon=True).start()

    def _poll(self) -> None:
        try:
            action, result = self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            for control in self.controls:
                control.configure(state="normal")
            if action == "error":
                self.status.set(f"操作失败：{result}")
                messagebox.showerror("操作失败", str(result), parent=self.root)
            elif action == "preview":
                parameters: tuple[OptParam, ...] = result
                for parameter in parameters:
                    self.variables.insert("", "end", values=(parameter.name, _format_ranges(parameter.ranges), parameter.unit))
                self.status.set(f"OptimizationSetup1 中找到 {len(parameters)} 个 Include 变量。预览未写入文件。")
            else:
                exported: ParameterExtractionResult = result
                self.output.set(str(exported.parameter_file))
                backup_message = str(exported.backup_file) if exported.backup_file else "无旧文件，无需备份"
                self.status.set(f"已生成 {exported.parameter_count} 个优化变量。备份：{backup_message}")
                messagebox.showinfo(
                    "生成成功", f"已生成 {exported.parameter_count} 个优化变量：\n{exported.parameter_file}\n\n备份：\n{backup_message}",
                    parent=self.root,
                )
        self._poll_id = self.root.after(100, self._poll)

    def _close(self) -> None:
        if self.busy:
            return
        self.root.after_cancel(self._poll_id)
        self.root.destroy()


def main(*, script_dir: Path | None = None) -> int:
    forwarded = _forward_to_runtime()
    if forwarded is not None:
        return forwarded
    data_root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local") / "Yadof"
    root = tk.Tk()
    AedtParametersApp(root, script_dir=(script_dir or data_root).resolve())
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
