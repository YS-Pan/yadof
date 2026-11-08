"""Visual constants and ttk styling for the viewer."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


BACKGROUND = "#f4f6fa"
PANEL = "#ffffff"
TEXT = "#172033"
MUTED = "#62708a"
ACCENT = "#246bfd"
PREDICTION = "#246bfd"
TRUTH = "#ef7f31"


def configure_styles(root: tk.Tk) -> None:
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure(".", font=("Segoe UI", 10), background=BACKGROUND)
    style.configure("TFrame", background=BACKGROUND)
    style.configure("Panel.TFrame", background=PANEL)
    style.configure(
        "Header.TLabel",
        background=BACKGROUND,
        foreground=TEXT,
        font=("Segoe UI Semibold", 18),
    )
    style.configure("Subtle.TLabel", background=BACKGROUND, foreground=MUTED)
    style.configure("Panel.TLabel", background=PANEL, foreground=TEXT)
    style.configure(
        "PanelTitle.TLabel",
        background=PANEL,
        foreground=TEXT,
        font=("Segoe UI Semibold", 11),
    )
    style.configure(
        "Accent.TButton",
        background=ACCENT,
        foreground="white",
        padding=(14, 7),
    )
    style.map(
        "Accent.TButton",
        background=[("active", "#1857d7"), ("disabled", "#a9badf")],
    )
    style.configure(
        "Viewer.TNotebook",
        background=BACKGROUND,
        borderwidth=0,
        tabmargins=(0, 0, 0, 0),
    )
    style.configure(
        "Viewer.TNotebook.Tab",
        padding=(20, 10),
        font=("Segoe UI Semibold", 10),
        borderwidth=1,
    )
    style.map(
        "Viewer.TNotebook.Tab",
        padding=[
            ("selected", (20, 10)),
            ("!selected", (20, 10)),
        ],
        background=[
            ("selected", PANEL),
            ("active", "#e8edf6"),
            ("!selected", "#dce3ee"),
        ],
        foreground=[
            ("selected", ACCENT),
            ("active", TEXT),
            ("!selected", MUTED),
        ],
    )
