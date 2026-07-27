"""Cross-generation error heatmap tab and its UI state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import tkinter as tk
from tkinter import messagebox, ttk

from ..backend import CrossGenerationErrorAudit, SurrogateWorkspace
from .plots import HeatmapPlot
from .widgets import bind_combobox_keyboard


@dataclass(frozen=True)
class QuantityOption:
    label: str
    kind: str
    index: int | None


class HeatmapTab(ttk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        *,
        on_calculate: Callable[[float], None],
        on_stop: Callable[[], None],
    ) -> None:
        super().__init__(parent)
        self._on_calculate = on_calculate
        self._on_stop = on_stop
        self._audit: CrossGenerationErrorAudit | None = None
        self._quantity_options: tuple[QuantityOption, ...] = ()
        self.calculating = False

        self.error_type_var = tk.StringVar(master=self, value="Relative")
        self.quantity_var = tk.StringVar(master=self)
        self.sample_percent_var = tk.DoubleVar(master=self, value=10.0)
        self.status_var = tk.StringVar(master=self, value="Not calculated")
        self.progress_var = tk.DoubleVar(master=self, value=0.0)
        self._build()

    @property
    def audit(self) -> CrossGenerationErrorAudit | None:
        return self._audit

    @property
    def quantity_options(self) -> tuple[QuantityOption, ...]:
        return self._quantity_options

    def _build(self) -> None:
        toolbar = ttk.Frame(self, padding=(12, 10))
        toolbar.pack(fill=tk.X)
        ttk.Label(
            toolbar,
            text="Independent cross-generation audit",
            font=("Segoe UI Semibold", 11),
        ).pack(side=tk.LEFT, padx=(0, 18))
        ttk.Label(toolbar, text="Error").pack(side=tk.LEFT, padx=(0, 5))
        self.error_type_combo = ttk.Combobox(
            toolbar,
            textvariable=self.error_type_var,
            values=("Relative", "Absolute"),
            state="readonly",
            width=10,
        )
        self.error_type_combo.current(0)
        self.error_type_combo.pack(side=tk.LEFT, padx=(0, 10))
        self.error_type_combo.bind(
            "<<ComboboxSelected>>",
            self._metric_changed,
        )
        bind_combobox_keyboard(self.error_type_combo)

        ttk.Label(toolbar, text="Quantity").pack(side=tk.LEFT, padx=(0, 5))
        self.quantity_combo = ttk.Combobox(
            toolbar,
            textvariable=self.quantity_var,
            state="readonly",
            width=32,
        )
        self.quantity_combo.pack(side=tk.LEFT, padx=(0, 10))
        self.quantity_combo.bind(
            "<<ComboboxSelected>>",
            self._metric_changed,
        )
        bind_combobox_keyboard(self.quantity_combo)

        ttk.Label(toolbar, text="Sample").pack(side=tk.LEFT, padx=(0, 5))
        self.sample_spinbox = ttk.Spinbox(
            toolbar,
            from_=1.0,
            to=100.0,
            increment=1.0,
            textvariable=self.sample_percent_var,
            width=6,
            justify=tk.RIGHT,
        )
        self.sample_spinbox.pack(side=tk.LEFT)
        ttk.Label(toolbar, text="% / generation").pack(
            side=tk.LEFT,
            padx=(3, 10),
        )
        self.calculate_button = ttk.Button(
            toolbar,
            text="Calculate predictions once",
            style="Accent.TButton",
            command=self._calculate_clicked,
        )
        self.calculate_button.pack(side=tk.LEFT)
        self.stop_button = ttk.Button(
            toolbar,
            text="Stop",
            command=self._stop_clicked,
            state=tk.DISABLED,
        )
        self.stop_button.pack(side=tk.LEFT, padx=(6, 0))

        progress_frame = ttk.Frame(self, padding=(12, 0, 12, 4))
        progress_frame.pack(fill=tk.X)
        ttk.Label(
            progress_frame,
            textvariable=self.status_var,
            style="Subtle.TLabel",
        ).pack(anchor=tk.E, pady=(0, 3))
        self.progress = ttk.Progressbar(
            progress_frame,
            variable=self.progress_var,
            maximum=100.0,
            mode="determinate",
        )
        self.progress.pack(fill=tk.X)

        plot_frame = ttk.Frame(self, padding=(8, 4, 8, 8))
        plot_frame.pack(fill=tk.BOTH, expand=True)
        self.plot = HeatmapPlot(plot_frame)
        self.plot.pack(fill=tk.BOTH, expand=True)

    def load_workspace(self, workspace: SurrogateWorkspace) -> None:
        cost_options = (
            QuantityOption("Costs · all", "cost", None),
            *(
                QuantityOption(f"Cost · {name}", "cost", index)
                for index, name in enumerate(workspace.objective_names)
            ),
        )
        rawdata_options = (
            QuantityOption("rawData · all", "rawdata", None),
            *(
                QuantityOption(f"rawData · {name}", "rawdata", index)
                for index, name in enumerate(workspace.rawdata_names)
            ),
        )
        self._quantity_options = (*cost_options, *rawdata_options)
        self.quantity_combo["values"] = tuple(
            option.label
            for option in self._quantity_options
        )
        self.quantity_combo.current(0)
        self._audit = None
        self.calculating = False
        self.progress_var.set(0.0)
        self.status_var.set("Not calculated")
        self.calculate_button.configure(
            text="Calculate predictions once",
            state=tk.NORMAL,
        )
        self.stop_button.configure(state=tk.DISABLED)
        self.plot.draw_empty()

    def begin_calculation(self, sample_percent: float) -> None:
        self.calculating = True
        self.calculate_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.NORMAL)
        self.progress_var.set(0.0)
        self.status_var.set(
            f"Sampling {sample_percent:g}% from each optimization generation…"
        )

    def set_progress(
        self,
        current: int,
        total: int,
        message: str,
    ) -> None:
        percent = 0.0 if total <= 0 else 100.0 * current / total
        self.progress_var.set(percent)
        self.status_var.set(message)

    def finish(self, audit: CrossGenerationErrorAudit) -> None:
        self.calculating = False
        self._audit = audit
        self.calculate_button.configure(
            text="Recalculate all predictions",
            state=tk.NORMAL,
        )
        self.stop_button.configure(state=tk.DISABLED)
        self.progress_var.set(100.0)
        self._draw_selected()

    def cancelled(self) -> None:
        self.calculating = False
        self.calculate_button.configure(state=tk.NORMAL)
        self.stop_button.configure(state=tk.DISABLED)
        if self._audit is None:
            self.progress_var.set(0.0)
            self.plot.draw_empty()
            self.status_var.set(
                "Stopped · no previous complete calculation is available."
            )
            return
        self.progress_var.set(100.0)
        self._draw_selected()
        self.status_var.set(
            "Stopped · showing the previous complete calculation."
        )

    def failed(self) -> None:
        self.calculating = False
        self.calculate_button.configure(state=tk.NORMAL)
        self.stop_button.configure(state=tk.DISABLED)
        self.status_var.set("Calculation failed")

    def _calculate_clicked(self) -> None:
        try:
            sample_percent = float(self.sample_percent_var.get())
        except (tk.TclError, TypeError, ValueError):
            sample_percent = float("nan")
        if not 1.0 <= sample_percent <= 100.0:
            messagebox.showerror(
                "Invalid sample percentage",
                "Sample percentage must be a number from 1 to 100.",
            )
            return
        self._on_calculate(sample_percent)

    def _stop_clicked(self) -> None:
        if not self.calculating:
            return
        self.stop_button.configure(state=tk.DISABLED)
        self.status_var.set("Stopping after the current inference batch…")
        self._on_stop()

    def _metric_changed(self, _event: tk.Event | None = None) -> None:
        if self.calculating:
            self.status_var.set(
                "Calculating once; the selected metric will be shown "
                "when complete."
            )
        elif self._audit is None:
            self.status_var.set(
                "Metric selected. Calculate predictions once to enable "
                "instant switching."
            )
        else:
            self._draw_selected()

    def _draw_selected(self) -> None:
        if self._audit is None:
            return
        selection = self.quantity_combo.current()
        if not 0 <= selection < len(self._quantity_options):
            selection = 0
        option = self._quantity_options[selection]
        matrix = self._audit.matrix(
            metric=self.error_type_var.get().strip().lower(),
            quantity_kind=option.kind,
            quantity_index=option.index,
        )
        self.plot.draw(matrix)
        kibibytes = self._audit.memory_bytes / 1024.0
        sampled = sum(self._audit.sample_counts)
        self.status_var.set(
            f"Instant update · {sampled} sampled individuals "
            f"({100.0 * self._audit.sample_fraction:g}%) · "
            f"{kibibytes:.1f} KiB aggregates."
        )
