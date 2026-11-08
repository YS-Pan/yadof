"""Sortable failure table; every Tk operation stays on the calling thread."""

from __future__ import annotations

import os

from . import FAILURE_COLUMNS, FAILURE_HEADERS, FailureRow, failure_sort_key


def show_errors(root, rows: list[FailureRow], *, on_error):
    import tkinter as tk
    from tkinter import ttk

    window = tk.Toplevel(root)
    window.title(f"失败记录（{len(rows)}）")
    window.geometry("1200x500")
    frame = ttk.Frame(window, padding=8)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="双击记录可打开对应的 jobs 文件夹").pack(anchor="w", pady=(0, 6))
    table_frame = ttk.Frame(frame)
    table_frame.pack(fill="both", expand=True)
    table = ttk.Treeview(table_frame, columns=FAILURE_COLUMNS, show="headings")
    for column, header, width in zip(FAILURE_COLUMNS, FAILURE_HEADERS, (185, 145, 260, 130, 500)):
        table.heading(column, text=header)
        table.column(column, width=width, stretch=column == "error_message", anchor="w")
    vertical = ttk.Scrollbar(table_frame, orient="vertical", command=table.yview)
    horizontal = ttk.Scrollbar(table_frame, orient="horizontal", command=table.xview)
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
            on_error(f"找不到 {row.job_name} 的 jobs 文件夹")
            return
        try:
            os.startfile(row.job_dir)  # type: ignore[attr-defined]
        except OSError as exc:
            on_error(f"无法打开 jobs 文件夹：{exc}")

    table.bind("<Double-1>", open_selected)
    return window
