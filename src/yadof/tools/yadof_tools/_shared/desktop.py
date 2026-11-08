"""Read-only desktop shells around the existing cost, time and failure APIs."""
from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import queue
import threading


def build_view(kind: str, workspace: Path) -> tuple[str, object]:
    if kind == "error":
        from yadof.tools.yadof_tools.view_error import failure_rows

        return "errors", failure_rows(workspace)
    if kind not in {"cost", "time"}:
        raise ValueError(f"Unknown history view: {kind}")
    import matplotlib

    matplotlib.use("Agg")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if kind == "cost":
        from yadof.tools.yadof_tools.cost_viewer import view_cost

        summary, output = view_cost(workspace, output_path=f"cost_{stamp}.png")
    else:
        from yadof.tools.yadof_tools.view_time import view_time

        summary, output = view_time(workspace, output_path=f"time_{stamp}.png")
    return "view", (kind, summary, output)


class HistoryViewApp:
    def __init__(self, root, kind: str, workspace: Path) -> None:
        import tkinter as tk
        from tkinter import ttk

        self.root, self.kind, self.workspace = root, kind, workspace
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.busy = True
        self.exit_code = 0
        root.title(f"yadof · view{kind}")
        root.geometry("600x150")
        frame = ttk.Frame(root, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=str(workspace), wraplength=560).pack(anchor="w")
        self.status = tk.StringVar(master=root, value="正在读取记录并生成结果…")
        ttk.Label(frame, textvariable=self.status).pack(anchor="w", pady=(10, 8))
        self.bar = ttk.Progressbar(frame, mode="indeterminate")
        self.bar.pack(fill="x")
        self.bar.start()
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(100, self.drain_events)
        threading.Thread(target=self.work, daemon=True).start()

    def work(self) -> None:
        try:
            self.events.put(build_view(self.kind, self.workspace))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def drain_events(self) -> None:
        from tkinter import messagebox

        try:
            event, payload = self.events.get_nowait()
        except queue.Empty:
            self.root.after(100, self.drain_events)
            return
        self.busy = False
        self.bar.stop()
        try:
            if event == "error":
                raise RuntimeError(str(payload))
            if event == "errors":
                if not payload:
                    messagebox.showinfo("viewerror", "没有失败记录", parent=self.root)
                    self.root.destroy()
                    return
                from yadof.tools.yadof_tools.view_error.app import show_errors

                self.root.withdraw()
                window = show_errors(
                    self.root, payload,
                    on_error=lambda message: messagebox.showerror("viewerror", message, parent=self.root),
                )
                window.protocol("WM_DELETE_WINDOW", self.root.destroy)
                return
            _, summary, output = payload
            if output is None:
                messagebox.showinfo(f"view{self.kind}", summary, parent=self.root)
            else:
                os.startfile(output)  # type: ignore[attr-defined]
            self.root.destroy()
        except Exception as exc:
            self.exit_code = 1
            messagebox.showerror(f"view{self.kind}", str(exc), parent=self.root)
            self.root.destroy()

    def close(self) -> None:
        from tkinter import messagebox

        if self.busy:
            messagebox.showinfo("yadof", "请等待当前记录读取完成后关闭。", parent=self.root)
        else:
            self.root.destroy()


def main(kind: str, workspace: Path | None = None) -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox

    root = tk.Tk()
    root.withdraw()
    if workspace is None:
        selected = filedialog.askdirectory(parent=root, title=f"view{kind} · 选择 workspace", mustexist=True)
        if not selected:
            root.destroy()
            return 0
        workspace = Path(selected)
    workspace = workspace.expanduser().resolve()
    if not (workspace / ".yadof/workspace.json").is_file():
        messagebox.showerror("yadof", "请选择已初始化的 workspace。", parent=root)
        root.destroy()
        return 1
    root.deiconify()
    app = HistoryViewApp(root, kind, workspace)
    root.mainloop()
    return app.exit_code
