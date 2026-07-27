"""Small Tk widgets and keyboard behavior shared by both tabs."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .style import PANEL


def _is_widget_descendant(widget: object, ancestor: object) -> bool:
    """Check ancestry without resolving Tcl-only combobox popup names."""

    current = widget
    visited: set[int] = set()
    while isinstance(current, tk.Misc) and id(current) not in visited:
        if current is ancestor:
            return True
        visited.add(id(current))
        current = getattr(current, "master", None)
    return False


def move_combobox(combo: ttk.Combobox, direction: int) -> str:
    values = tuple(combo["values"])
    if not values:
        return "break"
    current = combo.current()
    if current < 0:
        target = len(values) - 1 if direction < 0 else 0
    else:
        target = max(0, min(len(values) - 1, current + int(direction)))
    if target != current:
        combo.current(target)
        combo.event_generate("<<ComboboxSelected>>")
    return "break"


def bind_combobox_keyboard(combo: ttk.Combobox) -> None:
    combo.configure(takefocus=True)
    combo.bind(
        "<Up>",
        lambda _event, widget=combo: move_combobox(widget, -1),
    )
    combo.bind(
        "<Down>",
        lambda _event, widget=combo: move_combobox(widget, 1),
    )


class ScrollableFrame(ttk.Frame):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.canvas = tk.Canvas(
            self,
            highlightthickness=0,
            background=PANEL,
            borderwidth=0,
        )
        scrollbar = ttk.Scrollbar(
            self,
            orient=tk.VERTICAL,
            command=self.canvas.yview,
        )
        self.content = ttk.Frame(
            self.canvas,
            padding=(14, 6, 14, 14),
        )
        self._window = self.canvas.create_window(
            (0, 0),
            window=self.content,
            anchor=tk.NW,
        )
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.content.bind(
            "<Configure>",
            lambda _event: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")
            ),
        )
        self.canvas.bind(
            "<Configure>",
            lambda event: self.canvas.itemconfigure(
                self._window,
                width=event.width,
            ),
        )
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_mousewheel(self, event: tk.Event) -> None:
        if _is_widget_descendant(event.widget, self.canvas):
            self.canvas.yview_scroll(int(-event.delta / 120), "units")
