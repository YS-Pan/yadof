"""Interactive checkpoint prediction and real-result comparison tab."""

from __future__ import annotations

import math
import random
from typing import Callable

import tkinter as tk
from tkinter import ttk

from ..backend import (
    DimensionSpec,
    PlotRequest,
    PredictionResult,
    RealResult,
    SurrogateWorkspace,
)
from .plots import InteractivePlot
from .style import MUTED, PANEL
from .widgets import (
    CheckmarkToggle,
    ScrollableFrame,
    bind_combobox_keyboard,
)


class InteractiveTab(ttk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        *,
        on_prediction_request: Callable[[], None],
    ) -> None:
        super().__init__(parent)
        self.workspace: SurrogateWorkspace | None = None
        self._on_prediction_request = on_prediction_request
        self._last_prediction: PredictionResult | None = None
        self._real_results_in_combo: tuple[RealResult, ...] = ()
        self._debounce_id: str | None = None
        self._slider_values: list[tk.DoubleVar] = []
        self._slider_labels: list[ttk.Label] = []
        self.parameter_scales: list[ttk.Scale] = []
        self._dimension_specs: tuple[DimensionSpec, ...] = ()
        self._dimension_plot_vars: list[tk.BooleanVar] = []
        self._dimension_fixed_vars: list[tk.StringVar] = []
        self._dimension_grid_combos: list[ttk.Combobox] = []
        self._dimension_fixed_entries: list[ttk.Entry] = []
        self.dimension_toggles: list[CheckmarkToggle] = []

        self.checkpoint_var = tk.StringVar(master=self)
        self.real_generation_var = tk.StringVar(master=self)
        self.real_result_var = tk.StringVar(master=self)
        self.rawdata_var = tk.StringVar(master=self)
        self.auto_refresh_var = tk.BooleanVar(master=self, value=True)
        self._build()

    def _build(self) -> None:
        panes = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        panes.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(panes, style="Panel.TFrame", width=380)
        right = ttk.Frame(panes, padding=(12, 8, 8, 8))
        panes.add(left, weight=1)
        panes.add(right, weight=4)

        controls = ttk.Frame(
            left,
            style="Panel.TFrame",
            padding=(14, 14, 14, 6),
        )
        controls.pack(fill=tk.X)
        ttk.Label(
            controls,
            text="Model & real result",
            style="PanelTitle.TLabel",
        ).grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 9))
        self.checkpoint_combo = self._add_combo(
            controls,
            row=1,
            label="Checkpoint",
            variable=self.checkpoint_var,
            callback=self._request_prediction,
        )
        self.real_generation_combo = self._add_combo(
            controls,
            row=2,
            label="Real generation",
            variable=self.real_generation_var,
            callback=self._real_generation_changed,
        )
        self.real_result_combo = self._add_combo(
            controls,
            row=3,
            label="Real individual",
            variable=self.real_result_var,
            callback=self._real_result_changed,
        )
        ttk.Button(
            controls,
            text="Clear real overlay",
            command=self._clear_real_result,
        ).grid(row=4, column=1, sticky=tk.E, pady=(4, 8))
        self.rawdata_combo = self._add_combo(
            controls,
            row=5,
            label="rawData output",
            variable=self.rawdata_var,
            callback=self._rawdata_changed,
        )
        self.dimension_frame = ttk.LabelFrame(
            controls,
            text="Plot dimensions",
            padding=(8, 5, 8, 7),
        )
        self.dimension_frame.grid(
            row=6,
            column=0,
            columnspan=2,
            sticky=tk.EW,
            pady=(8, 2),
        )
        self.auto_refresh_toggle = CheckmarkToggle(
            controls,
            text="Auto refresh",
            variable=self.auto_refresh_var,
        )
        self.auto_refresh_toggle.grid(
            row=7,
            column=0,
            columnspan=2,
            sticky=tk.EW,
            pady=(9, 3),
        )
        ttk.Button(
            controls,
            text="Predict now",
            style="Accent.TButton",
            command=self._request_prediction,
        ).grid(row=8, column=0, columnspan=2, sticky=tk.EW, pady=(5, 5))
        ttk.Label(
            controls,
            text=(
                "Keyboard: ↑/↓ selects menus · "
                "←/→ adjusts focused parameters"
            ),
            style="Panel.TLabel",
            foreground=MUTED,
            font=("Segoe UI", 8),
        ).grid(row=9, column=0, columnspan=2, sticky=tk.W, pady=(4, 0))
        controls.columnconfigure(1, weight=1)

        ttk.Separator(left).pack(fill=tk.X, padx=14, pady=6)
        self.parameter_scroll = ScrollableFrame(left)
        self.parameter_scroll.pack(fill=tk.BOTH, expand=True)
        self.plot = InteractivePlot(right)
        self.plot.pack(fill=tk.BOTH, expand=True)

    @staticmethod
    def _add_combo(
        parent: ttk.Frame,
        *,
        row: int,
        label: str,
        variable: tk.StringVar,
        callback: Callable,
    ) -> ttk.Combobox:
        ttk.Label(
            parent,
            text=label,
            style="Panel.TLabel",
        ).grid(row=row, column=0, sticky=tk.W, pady=3)
        combo = ttk.Combobox(
            parent,
            textvariable=variable,
            state="readonly",
            width=36,
        )
        combo.grid(row=row, column=1, sticky=tk.EW, pady=3)
        combo.bind("<<ComboboxSelected>>", callback)
        bind_combobox_keyboard(combo)
        return combo

    def load_workspace(self, workspace: SurrogateWorkspace) -> None:
        if self._debounce_id:
            self.after_cancel(self._debounce_id)
            self._debounce_id = None
        self.workspace = workspace
        self._last_prediction = None
        self.checkpoint_combo["values"] = tuple(
            checkpoint.label
            for checkpoint in workspace.checkpoints
        )
        self.checkpoint_combo.current(len(workspace.checkpoints) - 1)
        self.real_generation_combo["values"] = tuple(
            str(value)
            for value in workspace.generations
        )
        selected_generation = random.choice(workspace.generations)
        self.real_generation_combo.current(
            workspace.generations.index(selected_generation)
        )
        self._real_generation_changed()
        selected_real = random.choice(self._real_results_in_combo)
        self.real_result_combo.current(
            self._real_results_in_combo.index(selected_real)
        )
        self.rawdata_combo["values"] = workspace.rawdata_names
        self.rawdata_var.set("")
        if workspace.rawdata_names:
            preferred = next(
                (
                    index
                    for index, name in enumerate(workspace.rawdata_names)
                    if name.startswith("s11")
                ),
                0,
            )
            self.rawdata_combo.current(preferred)
        self._build_dimension_controls()
        self._build_parameter_sliders()
        for variable, value in zip(
            self._slider_values,
            selected_real.normalized_values,
        ):
            variable.set(value)
        self._update_parameter_labels(selected_real.normalized_values)
        self.plot.draw_empty()

    def _build_dimension_controls(self) -> None:
        for child in self.dimension_frame.winfo_children():
            child.destroy()
        self._dimension_specs = ()
        self._dimension_plot_vars.clear()
        self._dimension_fixed_vars.clear()
        self._dimension_grid_combos.clear()
        self._dimension_fixed_entries.clear()
        self.dimension_toggles.clear()
        if self.workspace is None:
            return
        item_index = self.rawdata_combo.current()
        if item_index < 0:
            return

        self._dimension_specs = self.workspace.dimensions_for_rawdata(
            item_index
        )
        if not self._dimension_specs:
            ttk.Label(
                self.dimension_frame,
                text="Scalar rawData has no dimensions.",
                style="Panel.TLabel",
                foreground=MUTED,
            ).grid(row=0, column=0, sticky=tk.W)
            return

        ttk.Label(
            self.dimension_frame,
            text="Select 0–2 axes; enter fixed coordinates for the rest.",
            style="Panel.TLabel",
            foreground=MUTED,
            font=("Segoe UI", 8),
        ).grid(row=0, column=0, columnspan=5, sticky=tk.W, pady=(0, 3))
        default_axis = next(
            (
                dimension.index
                for dimension in self._dimension_specs
                if dimension.name.casefold() == "freq"
            ),
            self._dimension_specs[0].index,
        )
        for row, dimension in enumerate(self._dimension_specs, start=1):
            plot_variable = tk.BooleanVar(
                master=self,
                value=dimension.index == default_axis,
            )
            fixed_variable = tk.StringVar(
                master=self,
                value=self._format_coordinate(dimension.default_value),
            )
            toggle = CheckmarkToggle(
                self.dimension_frame,
                text=dimension.label,
                variable=plot_variable,
                command=lambda i=dimension.index: (
                    self._dimension_selection_changed(i)
                ),
            )
            toggle.grid(
                row=row,
                column=0,
                sticky=tk.EW,
                padx=(0, 8),
                pady=2,
            )
            ttk.Label(
                self.dimension_frame,
                text="grid",
                style="Panel.TLabel",
                foreground=MUTED,
            ).grid(row=row, column=1, sticky=tk.E, padx=(0, 4))
            grid_combo = ttk.Combobox(
                self.dimension_frame,
                state="readonly",
                width=11,
                values=tuple(
                    self._format_coordinate(value)
                    for value in dimension.coordinates
                ),
            )
            default_index = min(
                range(len(dimension.coordinates)),
                key=lambda index: abs(
                    float(dimension.coordinates[index])
                    - dimension.default_value
                ),
            )
            grid_combo.current(default_index)
            grid_combo.grid(row=row, column=2, sticky=tk.EW, pady=2)
            grid_combo.bind(
                "<<ComboboxSelected>>",
                lambda _event, i=dimension.index: (
                    self._grid_dimension_changed(i)
                ),
            )
            bind_combobox_keyboard(grid_combo)
            ttk.Label(
                self.dimension_frame,
                text="value",
                style="Panel.TLabel",
                foreground=MUTED,
            ).grid(row=row, column=3, sticky=tk.E, padx=(7, 4))
            entry = ttk.Entry(
                self.dimension_frame,
                textvariable=fixed_variable,
                width=11,
            )
            entry.grid(row=row, column=4, sticky=tk.EW, pady=2)
            entry.bind(
                "<Return>",
                lambda _event, i=dimension.index: (
                    self._fixed_dimension_changed(i)
                ),
            )
            entry.bind(
                "<FocusOut>",
                lambda _event, i=dimension.index: (
                    self._fixed_dimension_changed(i)
                ),
            )
            self._dimension_plot_vars.append(plot_variable)
            self._dimension_fixed_vars.append(fixed_variable)
            self._dimension_grid_combos.append(grid_combo)
            self._dimension_fixed_entries.append(entry)
            self.dimension_toggles.append(toggle)
        self.dimension_frame.columnconfigure(4, weight=1)
        self._update_dimension_entry_states()

    def _rawdata_changed(self, _event: tk.Event | None = None) -> None:
        self._build_dimension_controls()
        self._request_prediction()

    def _dimension_selection_changed(self, index: int) -> None:
        selected_count = sum(
            variable.get()
            for variable in self._dimension_plot_vars
        )
        if selected_count > 2:
            self._dimension_plot_vars[index].set(False)
            self.bell()
        self._update_dimension_entry_states()
        self._request_prediction()

    def _update_dimension_entry_states(self) -> None:
        for selected, combo, entry in zip(
            self._dimension_plot_vars,
            self._dimension_grid_combos,
            self._dimension_fixed_entries,
        ):
            combo.configure(
                state="disabled" if selected.get() else "readonly"
            )
            entry.configure(
                state="disabled" if selected.get() else "normal"
            )

    def _grid_dimension_changed(self, index: int) -> None:
        if self._dimension_plot_vars[index].get():
            return
        selected = self._dimension_grid_combos[index].current()
        if selected < 0:
            return
        coordinate = float(
            self._dimension_specs[index].coordinates[selected]
        )
        self._dimension_fixed_vars[index].set(
            self._format_coordinate(coordinate)
        )
        self._request_prediction()

    def _fixed_dimension_changed(self, index: int) -> None:
        if self._dimension_plot_vars[index].get():
            return
        dimension = self._dimension_specs[index]
        try:
            requested = float(self._dimension_fixed_vars[index].get())
            if not math.isfinite(requested):
                raise ValueError
        except ValueError:
            requested = dimension.default_value
            self.bell()
        self._dimension_fixed_vars[index].set(
            self._format_coordinate(requested)
        )
        matching = next(
            (
                coordinate_index
                for coordinate_index, coordinate in enumerate(
                    dimension.coordinates
                )
                if math.isclose(
                    float(coordinate),
                    requested,
                    rel_tol=1e-12,
                    abs_tol=1e-12 * max(1.0, abs(requested)),
                )
            ),
            None,
        )
        if matching is None:
            self._dimension_grid_combos[index].set("")
        else:
            self._dimension_grid_combos[index].current(matching)
        self._request_prediction()

    def _plot_selection(self) -> tuple[tuple[int, ...], dict[int, float]]:
        plotted = tuple(
            dimension.index
            for dimension, variable in zip(
                self._dimension_specs,
                self._dimension_plot_vars,
            )
            if variable.get()
        )
        fixed: dict[int, float] = {}
        for dimension, selected, variable in zip(
            self._dimension_specs,
            self._dimension_plot_vars,
            self._dimension_fixed_vars,
        ):
            if selected.get():
                continue
            value = float(variable.get())
            if not math.isfinite(value):
                raise ValueError(
                    f"{dimension.name} fixed value must be finite"
                )
            fixed[dimension.index] = value
        return plotted, fixed

    @staticmethod
    def _format_coordinate(value: float) -> str:
        return f"{float(value):.15g}"

    def _build_parameter_sliders(self) -> None:
        assert self.workspace is not None
        for child in self.parameter_scroll.content.winfo_children():
            child.destroy()
        self._slider_values.clear()
        self._slider_labels.clear()
        self.parameter_scales.clear()
        ttk.Label(
            self.parameter_scroll.content,
            text="Parameters",
            style="PanelTitle.TLabel",
        ).pack(anchor=tk.W, pady=(3, 10))
        normalized = (0.5,) * len(self.workspace.parameters)
        raw_values = self.workspace.denormalize(normalized)
        for index, (parameter, raw_value) in enumerate(
            zip(self.workspace.parameters, raw_values)
        ):
            block = ttk.Frame(
                self.parameter_scroll.content,
                style="Panel.TFrame",
            )
            block.pack(fill=tk.X, pady=(0, 10))
            top = ttk.Frame(block, style="Panel.TFrame")
            top.pack(fill=tk.X)
            ttk.Label(
                top,
                text=parameter.name,
                style="Panel.TLabel",
            ).pack(side=tk.LEFT)
            value_label = ttk.Label(
                top,
                text=self._format_parameter(index, raw_value),
                style="Panel.TLabel",
            )
            value_label.pack(side=tk.RIGHT)
            variable = tk.DoubleVar(master=self, value=0.5)
            scale = ttk.Scale(
                block,
                from_=0.0,
                to=1.0,
                variable=variable,
                command=lambda _value, i=index: self._slider_changed(i),
                takefocus=True,
            )
            scale.pack(fill=tk.X, pady=(3, 0))
            scale.bind(
                "<Button-1>",
                lambda event: event.widget.focus_set(),
                add="+",
            )
            for key, delta in (
                ("<Left>", -0.01),
                ("<Right>", 0.01),
                ("<Shift-Left>", -0.05),
                ("<Shift-Right>", 0.05),
            ):
                scale.bind(
                    key,
                    lambda _event, i=index, step=delta: self._nudge_slider(
                        i,
                        step,
                    ),
                )
            range_text = " ∪ ".join(
                f"[{low:g}, {high:g}]"
                for low, high in parameter.ranges
            )
            suffix = f" {parameter.unit}" if parameter.unit else ""
            ttk.Label(
                block,
                text=f"valid range {range_text}{suffix}",
                style="Panel.TLabel",
                foreground=MUTED,
                font=("Segoe UI", 8),
            ).pack(anchor=tk.W)
            self._slider_values.append(variable)
            self._slider_labels.append(value_label)
            self.parameter_scales.append(scale)

    def prediction_inputs(
        self,
    ) -> tuple[
        int,
        tuple[float, ...],
        str | None,
        PlotRequest,
    ]:
        if self.workspace is None:
            raise RuntimeError("load a workspace first")
        checkpoint_index = self.checkpoint_combo.current()
        if checkpoint_index < 0:
            raise ValueError("choose a checkpoint")
        real = self._selected_real_result()
        item_index = self.rawdata_combo.current()
        if item_index < 0:
            raise ValueError("choose a rawData output")
        plotted, fixed = self._plot_selection()
        return (
            self.workspace.checkpoints[checkpoint_index].generation,
            tuple(float(variable.get()) for variable in self._slider_values),
            None if real is None else real.job_name,
            PlotRequest(
                item_index=item_index,
                plotted_dimensions=plotted,
                fixed_values=tuple(sorted(fixed.items())),
            ),
        )

    def show_prediction(self, result: PredictionResult) -> None:
        self._last_prediction = result
        self._draw_prediction()

    def _draw_prediction(self, _event: tk.Event | None = None) -> None:
        if self._last_prediction is None or self.workspace is None:
            return
        item_index = self.rawdata_combo.current()
        if item_index < 0:
            return
        try:
            plotted_dimensions, fixed_values = self._plot_selection()
        except ValueError:
            self.bell()
            return
        self.plot.draw_prediction(
            self._last_prediction,
            self.workspace,
            item_index,
            plotted_dimensions,
            fixed_values,
        )

    def _request_prediction(self, _event: tk.Event | None = None) -> None:
        if self.workspace is not None:
            self._on_prediction_request()

    def _real_generation_changed(
        self,
        _event: tk.Event | None = None,
    ) -> None:
        if self.workspace is None or not self.real_generation_var.get():
            return
        generation = int(self.real_generation_var.get())
        self._real_results_in_combo = self.workspace.results_for_generation(
            generation
        )
        self.real_result_combo["values"] = tuple(
            item.label
            for item in self._real_results_in_combo
        )
        self.real_result_var.set("")

    def _selected_real_result(self) -> RealResult | None:
        index = self.real_result_combo.current()
        if not 0 <= index < len(self._real_results_in_combo):
            return None
        return self._real_results_in_combo[index]

    def _real_result_changed(
        self,
        _event: tk.Event | None = None,
    ) -> None:
        result = self._selected_real_result()
        if result is None or self.workspace is None:
            return
        for variable, value in zip(
            self._slider_values,
            result.normalized_values,
        ):
            variable.set(value)
        self._update_parameter_labels(result.normalized_values)
        self._request_prediction()

    def _clear_real_result(self) -> None:
        self.real_generation_var.set("")
        self.real_result_var.set("")
        self.real_result_combo["values"] = ()
        self._real_results_in_combo = ()
        self._request_prediction()

    def _slider_changed(self, index: int) -> None:
        normalized = tuple(
            variable.get()
            for variable in self._slider_values
        )
        self._update_parameter_labels(normalized, only_index=index)
        self.real_result_combo.set("")
        if not self.auto_refresh_var.get():
            return
        if self._debounce_id:
            self.after_cancel(self._debounce_id)
        self._debounce_id = self.after(
            350,
            self._run_debounced_prediction,
        )

    def _run_debounced_prediction(self) -> None:
        self._debounce_id = None
        self._request_prediction()

    def _update_parameter_labels(
        self,
        normalized: tuple[float, ...],
        *,
        only_index: int | None = None,
    ) -> None:
        if self.workspace is None:
            return
        raw_values = self.workspace.denormalize(normalized)
        indices = (
            range(len(raw_values))
            if only_index is None
            else (only_index,)
        )
        for index in indices:
            if index < len(raw_values):
                self._slider_labels[index].configure(
                    text=self._format_parameter(index, raw_values[index])
                )

    def _format_parameter(self, index: int, raw_value: float) -> str:
        assert self.workspace is not None
        unit = self.workspace.parameters[index].unit
        suffix = f" {unit}" if unit else ""
        return f"{raw_value:.6g}{suffix}"

    def _nudge_slider(self, index: int, delta: float) -> str:
        value = max(
            0.0,
            min(
                1.0,
                float(self._slider_values[index].get()) + float(delta),
            ),
        )
        self._slider_values[index].set(value)
        self._slider_changed(index)
        return "break"
