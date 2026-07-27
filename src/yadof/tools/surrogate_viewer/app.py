"""Tkinter application coordinator for the yadof surrogate viewer."""

from __future__ import annotations

import argparse
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
import queue
import sys
import threading
import traceback
from typing import Callable

import matplotlib

matplotlib.use("TkAgg")

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .backend import AuditCancelled, PredictionResult, SurrogateWorkspace
from .ui.heatmap import HeatmapTab
from .ui.interactive import InteractiveTab
from .ui.style import BACKGROUND, configure_styles
from .ui.widgets import ScrollableFrame, _is_widget_descendant


class SurrogateViewerApp:
    def __init__(
        self,
        root: tk.Tk,
        workspace: str | Path | None = None,
    ) -> None:
        self.root = root
        self.root.title("yadof surrogate checkpoint viewer")
        self.root.geometry("1460x900")
        self.root.minsize(1100, 700)
        self.root.configure(background=BACKGROUND)
        configure_styles(root)

        self.workspace: SurrogateWorkspace | None = None
        self.executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="surrogate-viewer",
        )
        self.ui_queue: queue.Queue[Callable[[], None]] = queue.Queue()
        self._prediction_serial = 0
        self._prediction_future: Future[PredictionResult] | None = None
        self._heatmap_serial = 0
        self._heatmap_cancel_event: threading.Event | None = None
        self._last_callback_error = ""

        self.workspace_var = tk.StringVar(
            master=root,
            value=str(Path(workspace).resolve()) if workspace else "",
        )
        self.status_var = tk.StringVar(
            master=root,
            value="Choose a yadof workspace to begin.",
        )
        self._build_header()
        self._build_tabs()

        self.root.report_callback_exception = self._report_callback_exception
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.after(80, self._drain_ui_queue)
        if workspace:
            self.root.after(120, self.load_workspace)

    def _build_header(self) -> None:
        header = ttk.Frame(self.root, padding=(18, 14, 18, 10))
        header.pack(fill=tk.X)
        title_block = ttk.Frame(header)
        title_block.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(
            title_block,
            text="Surrogate checkpoint viewer",
            style="Header.TLabel",
        ).pack(anchor=tk.W)
        ttk.Label(
            title_block,
            text=(
                "Read-only yadof tool · checkpoint selection, "
                "live prediction, real-data comparison, "
                "cross-generation error"
            ),
            style="Subtle.TLabel",
        ).pack(anchor=tk.W, pady=(2, 0))

        workspace_bar = ttk.Frame(header)
        workspace_bar.pack(side=tk.RIGHT, padx=(20, 0))
        ttk.Entry(
            workspace_bar,
            textvariable=self.workspace_var,
            width=55,
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(
            workspace_bar,
            text="Browse…",
            command=self._browse_workspace,
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(
            workspace_bar,
            text="Load workspace",
            style="Accent.TButton",
            command=self.load_workspace,
        ).pack(side=tk.LEFT)

    def _build_tabs(self) -> None:
        notebook = ttk.Notebook(self.root, style="Viewer.TNotebook")
        notebook.pack(
            fill=tk.BOTH,
            expand=True,
            padx=18,
            pady=(0, 8),
        )
        self.interactive_tab = InteractiveTab(
            notebook,
            on_prediction_request=self.request_prediction,
        )
        self.heatmap_tab = HeatmapTab(
            notebook,
            on_calculate=self.request_heatmap,
            on_stop=self.stop_heatmap,
        )
        notebook.add(
            self.interactive_tab,
            text="Interactive prediction & real comparison",
        )
        notebook.add(
            self.heatmap_tab,
            text="Cross-generation error heatmap",
        )

        footer = ttk.Frame(self.root, padding=(18, 3, 18, 10))
        footer.pack(fill=tk.X)
        ttk.Label(
            footer,
            textvariable=self.status_var,
            style="Subtle.TLabel",
        ).pack(side=tk.LEFT)

    def _browse_workspace(self) -> None:
        selected = filedialog.askdirectory(
            title="Choose yadof workspace",
            initialdir=self.workspace_var.get() or str(Path.cwd()),
        )
        if selected:
            self.workspace_var.set(selected)

    def load_workspace(self) -> None:
        raw_path = self.workspace_var.get().strip()
        if not raw_path:
            messagebox.showinfo(
                "Workspace required",
                "Choose a workspace first.",
            )
            return
        self._cancel_pending_work()
        self.status_var.set("Loading workspace metadata…")
        self.root.update_idletasks()
        try:
            workspace = SurrogateWorkspace(raw_path)
        except Exception as exc:
            self.status_var.set("Workspace load failed.")
            messagebox.showerror(
                "Cannot load workspace",
                self._error_text(exc),
            )
            return

        self.workspace = workspace
        self.workspace_var.set(str(workspace.root))
        self.interactive_tab.load_workspace(workspace)
        self.heatmap_tab.load_workspace(workspace)
        self.status_var.set(
            f"Loaded {len(workspace.checkpoints)} checkpoints, "
            f"{len(workspace.real_results)} completed generation results, "
            f"{len(workspace.parameters)} parameters."
        )
        self.request_prediction()

    def request_prediction(self) -> None:
        if self.workspace is None:
            return
        generation, normalized, true_job_name = (
            self.interactive_tab.prediction_inputs()
        )
        self._prediction_serial += 1
        serial = self._prediction_serial
        if self._prediction_future is not None:
            self._prediction_future.cancel()
        self.status_var.set(
            f"Loading checkpoint {generation} and predicting…"
        )
        future = self.executor.submit(
            self.workspace.predict_one,
            generation,
            normalized,
            true_job_name=true_job_name,
        )
        self._prediction_future = future

        def finished(done: Future[PredictionResult]) -> None:
            def update() -> None:
                if serial != self._prediction_serial:
                    return
                try:
                    result = done.result()
                except Exception as exc:
                    self.status_var.set("Prediction failed.")
                    messagebox.showerror(
                        "Prediction failed",
                        self._error_text(exc),
                    )
                    return
                self.interactive_tab.show_prediction(result)
                comparison = (
                    f"; compared with {result.true_job_name}"
                    if result.true_job_name
                    else ""
                )
                self.status_var.set(
                    f"Checkpoint {result.checkpoint_generation} "
                    f"prediction ready{comparison}."
                )

            self.ui_queue.put(update)

        future.add_done_callback(finished)

    def request_heatmap(self, sample_percent: float) -> None:
        if self.workspace is None:
            messagebox.showinfo(
                "Workspace required",
                "Load a workspace first.",
            )
            return
        self._heatmap_serial += 1
        serial = self._heatmap_serial
        cancel_event = threading.Event()
        self._heatmap_cancel_event = cancel_event
        self.heatmap_tab.begin_calculation(sample_percent)

        def progress(current: int, total: int, message: str) -> None:
            self.ui_queue.put(
                lambda: (
                    self.heatmap_tab.set_progress(current, total, message)
                    if serial == self._heatmap_serial
                    else None
                )
            )

        future = self.executor.submit(
            self.workspace.calculate_error_audit,
            sample_fraction=sample_percent / 100.0,
            cancel_event=cancel_event,
            progress=progress,
        )

        def finished(done: Future) -> None:
            def update() -> None:
                if serial != self._heatmap_serial:
                    return
                self._heatmap_cancel_event = None
                try:
                    audit = done.result()
                except AuditCancelled:
                    self.heatmap_tab.cancelled()
                    return
                except Exception as exc:
                    self.heatmap_tab.failed()
                    messagebox.showerror(
                        "Heatmap calculation failed",
                        self._error_text(exc),
                    )
                    return
                self.heatmap_tab.finish(audit)

            self.ui_queue.put(update)

        future.add_done_callback(finished)

    def stop_heatmap(self) -> None:
        if self._heatmap_cancel_event is not None:
            self._heatmap_cancel_event.set()

    def _cancel_pending_work(self) -> None:
        if self._heatmap_cancel_event is not None:
            self._heatmap_cancel_event.set()
        self._heatmap_cancel_event = None
        self._heatmap_serial += 1
        self._prediction_serial += 1
        if self._prediction_future is not None:
            self._prediction_future.cancel()

    def _drain_ui_queue(self) -> None:
        try:
            while True:
                self.ui_queue.get_nowait()()
        except queue.Empty:
            pass
        if self.root.winfo_exists():
            self.root.after(80, self._drain_ui_queue)

    @staticmethod
    def _error_text(exc: BaseException) -> str:
        details = "".join(
            traceback.format_exception_only(type(exc), exc)
        ).strip()
        return details or repr(exc)

    def _report_callback_exception(
        self,
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_traceback,
    ) -> None:
        traceback.print_exception(
            exc_type,
            exc_value,
            exc_traceback,
            file=sys.stderr,
        )
        details = self._error_text(exc_value)
        self.status_var.set(f"GUI callback failed: {details}")
        if details != self._last_callback_error:
            self._last_callback_error = details
            messagebox.showerror("GUI callback failed", details)

    def _close(self) -> None:
        self._cancel_pending_work()
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only GUI for yadof surrogate checkpoints"
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=None,
        help="yadof workspace containing recorded_data and checkpoints",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = tk.Tk()
    SurrogateViewerApp(root, args.workspace)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
