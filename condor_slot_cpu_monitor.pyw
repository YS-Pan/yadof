"""Monitor HTCondor slot CpusUsage and plot the recorded CSV.

Run with ``pythonw condor_slot_cpu_monitor.pyw`` on a machine where
``condor_status`` can query the pool. Matplotlib is needed for the plot button.

This pool exposes CpusUsage as a slot ClassAd expression. Query it with
``condor_status -af:ht`` so HTCondor evaluates the expression before output.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import importlib.util
import math
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


FIELDS = (
    "collected_at",
    "advertised_at",
    "ad_age_seconds",
    "slot",
    "machine",
    "slot_type",
    "state",
    "activity",
    "cpus",
    "cpus_usage",
    "cpu_usage_percent",
    "condor_load_cores",
)
ATTRIBUTES = (
    "Name", "Machine", "SlotType", "PartitionableSlot", "State", "Activity",
    "Cpus", "CpusUsage", "CondorLoadAvg", "LastHeardFrom",
)
DEFAULT_CSV = Path(__file__).resolve().parent / "temp" / "condor_slot_cpu.csv"
YADOF_PYTHONW = Path(r"C:\ProgramData\miniconda3\envs\yadof\pythonw.exe")


def _number(value: object) -> float | None:
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def parse_slot_ads(ads: object, collected_at: datetime) -> list[dict[str, object]]:
    """Convert evaluated slot ClassAds to rows, excluding parent slots."""
    if not isinstance(ads, list):
        raise ValueError("condor_status data must be a list")
    rows: list[dict[str, object]] = []
    for ad in ads:
        if not isinstance(ad, dict) or str(ad.get("PartitionableSlot", "")).lower() == "true":
            continue
        slot = ad.get("Name")
        cpus = _number(ad.get("Cpus"))
        usage = _number(ad.get("CpusUsage"))
        load = _number(ad.get("CondorLoadAvg"))
        heard = _number(ad.get("LastHeardFrom"))
        if not isinstance(slot, str) or not slot or cpus is None or cpus <= 0:
            continue
        advertised_at = (
            datetime.fromtimestamp(heard, tz=timezone.utc).astimezone()
            if heard is not None
            else None
        )
        age = max(0, round(collected_at.timestamp() - heard)) if heard is not None else ""
        rows.append({
            "collected_at": collected_at.isoformat(timespec="seconds"),
            "advertised_at": advertised_at.isoformat(timespec="seconds") if advertised_at else "",
            "ad_age_seconds": age,
            "slot": slot,
            "machine": ad.get("Machine", ""),
            "slot_type": ad.get("SlotType", ""),
            "state": ad.get("State", ""),
            "activity": ad.get("Activity", ""),
            "cpus": int(cpus) if cpus.is_integer() else cpus,
            "cpus_usage": round(usage, 6) if usage is not None else "",
            "cpu_usage_percent": round(usage / cpus * 100, 2) if usage is not None else "",
            "condor_load_cores": round(load, 4) if load is not None else "",
        })
    return sorted(rows, key=lambda row: str(row["slot"]))


def query_slots() -> list[dict[str, object]]:
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        result = subprocess.run(
            ["condor_status", "-af:ht", *ATTRIBUTES],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=25,
            creationflags=flags,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("找不到 condor_status；请将 HTCondor bin 目录加入 PATH。") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("condor_status 查询超时（25 秒）。") from exc
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"condor_status 返回 {result.returncode}")
    lines = result.stdout.splitlines()
    if not lines or [part.strip() for part in lines[0].split("\t")] != list(ATTRIBUTES):
        raise RuntimeError("condor_status 返回的字段标题与预期不符。")
    ads = []
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = [part.strip() for part in line.split("\t")]
        if len(parts) != len(ATTRIBUTES):
            raise RuntimeError("condor_status 返回的行列数与预期不符。")
        ads.append(dict(zip(ATTRIBUTES, parts)))
    return parse_slot_ads(ads, datetime.now().astimezone())


def append_rows(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists() or path.stat().st_size == 0
    if not new_file:
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            if next(csv.reader(source), []) != list(FIELDS):
                raise ValueError("CSV 表头与本工具格式不符，请选择其他文件。")
    with path.open("a", encoding="utf-8-sig" if new_file else "utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerows(rows)


def read_plot_rows(path: Path) -> dict[str, list[tuple[datetime, float]]]:
    series: dict[str, list[tuple[datetime, float]]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if not reader.fieldnames or not {"slot", "collected_at", "cpus_usage"} <= set(reader.fieldnames):
            raise ValueError("CSV 缺少绘图所需的列。")
        for row in reader:
            slot = row.get("slot", "")
            value = _number(row.get("cpus_usage"))
            try:
                moment = datetime.fromisoformat(row.get("collected_at", ""))
            except ValueError:
                continue
            if slot and value is not None:
                series.setdefault(slot, []).append((moment, value))
    for points in series.values():
        points.sort(key=lambda item: item[0])
    return series


class PlotWindow(tk.Toplevel):
    def __init__(self, parent: tk.Tk, path: Path, series: dict[str, list[tuple[datetime, float]]]):
        super().__init__(parent)
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
        from matplotlib.figure import Figure

        self.title(f"槽 CPU 负载曲线 — {path.name}")
        self.geometry("1100x650")
        self.series = series
        self.slots = sorted(series)

        left = ttk.Frame(self, padding=8)
        left.pack(side="left", fill="y")
        ttk.Label(left, text="选择槽（Ctrl/Shift 多选）").pack(anchor="w")
        self.selection = tk.Listbox(left, selectmode="extended", exportselection=False, width=31)
        self.selection.pack(fill="both", expand=True)
        for slot in self.slots:
            self.selection.insert("end", slot)
        self.selection.select_set(0, "end")
        self.selection.bind("<<ListboxSelect>>", lambda _event: self.redraw())

        right = ttk.Frame(self, padding=8)
        right.pack(side="right", fill="both", expand=True)
        self.figure = Figure(figsize=(9, 6), dpi=100)
        self.axes = self.figure.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.figure, master=right)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        NavigationToolbar2Tk(self.canvas, right).update()
        self.redraw()

    def redraw(self) -> None:
        self.axes.clear()
        selected = [self.slots[index] for index in self.selection.curselection()]
        for slot in selected:
            points = self.series[slot]
            self.axes.plot([time for time, _ in points], [value for _, value in points],
                           marker=".", markersize=3, linewidth=1, label=slot)
        self.axes.set_ylabel("CpusUsage (CPU cores)")
        self.axes.set_xlabel("Collection time")
        self.axes.grid(True, alpha=0.3)
        if selected:
            self.axes.legend(loc="upper left", fontsize="x-small", ncol=min(3, len(selected)))
        self.figure.autofmt_xdate()
        self.figure.tight_layout()
        self.canvas.draw_idle()


class MonitorApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("HTCondor 槽 CPU 监控")
        self.geometry("980x580")
        self.path = tk.StringVar(value=str(DEFAULT_CSV))
        self.interval = tk.StringVar(value="30")
        self.status = tk.StringVar(value="就绪。CpusUsage 表示每个槽报告的 CPU 核数用量。")
        self.messages: queue.Queue[tuple[str, object]] = queue.Queue()
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None

        controls = ttk.Frame(self, padding=10)
        controls.pack(fill="x")
        ttk.Label(controls, text="CSV:").grid(row=0, column=0, sticky="w")
        ttk.Entry(controls, textvariable=self.path).grid(row=0, column=1, columnspan=5, sticky="ew", padx=6)
        ttk.Button(controls, text="选择", command=self.choose_output).grid(row=0, column=6)
        ttk.Label(controls, text="间隔（秒）:").grid(row=1, column=0, sticky="w", pady=8)
        ttk.Entry(controls, textvariable=self.interval, width=8).grid(row=1, column=1, sticky="w")
        self.start_button = ttk.Button(controls, text="开始监控", command=self.start)
        self.start_button.grid(row=1, column=2, padx=8)
        self.stop_button = ttk.Button(controls, text="停止", command=self.stop, state="disabled")
        self.stop_button.grid(row=1, column=3)
        ttk.Button(controls, text="绘制 CSV", command=self.plot_csv).grid(row=1, column=4, padx=8)
        controls.columnconfigure(1, weight=1)

        table_frame = ttk.Frame(self, padding=(10, 0, 10, 5))
        table_frame.pack(fill="both", expand=True)
        columns = ("slot", "activity", "cpus", "usage", "percent", "age")
        self.table = ttk.Treeview(table_frame, columns=columns, show="headings")
        titles = {"slot": "槽", "activity": "状态", "cpus": "分配核数", "usage": "CpusUsage（核）",
                  "percent": "占分配核数 (%)", "age": "广告年龄（秒）"}
        for column in columns:
            self.table.heading(column, text=titles[column])
            self.table.column(column, width=280 if column == "slot" else 120, stretch=True)
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        self.table.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        ttk.Label(self, textvariable=self.status, padding=10).pack(fill="x")
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(100, self.drain_messages)
        self.after(250, self.start)

    def choose_output(self) -> None:
        chosen = filedialog.asksaveasfilename(parent=self, defaultextension=".csv",
                                              filetypes=[("CSV", "*.csv")], initialfile=Path(self.path.get()).name)
        if chosen:
            self.path.set(chosen)

    def start(self) -> None:
        try:
            interval = int(self.interval.get())
            if not 5 <= interval <= 3600:
                raise ValueError
        except ValueError:
            messagebox.showerror("间隔无效", "请输入 5 到 3600 之间的整数秒。", parent=self)
            return
        path = Path(self.path.get().strip())
        if not self.path.get().strip() or path.is_dir():
            messagebox.showerror("CSV 路径无效", "请选择 CSV 文件路径。", parent=self)
            return
        self.stop_event = threading.Event()
        self.worker = threading.Thread(target=self.monitor, args=(path, interval), daemon=True)
        self.worker.start()
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status.set("正在查询 HTCondor 槽...")

    def monitor(self, path: Path, interval: int) -> None:
        while not self.stop_event.is_set():
            try:
                rows = query_slots()
                append_rows(path, rows)
                self.messages.put(("sample", (rows, len(rows))))
            except (OSError, ValueError, RuntimeError) as exc:
                self.messages.put(("error", str(exc)))
            if self.stop_event.wait(interval):
                break
        self.messages.put(("stopped", None))

    def stop(self) -> None:
        self.stop_event.set()
        self.stop_button.configure(state="disabled")
        self.status.set("正在停止...")

    def drain_messages(self) -> None:
        try:
            while True:
                kind, payload = self.messages.get_nowait()
                if kind == "sample":
                    rows, saved = payload  # type: ignore[misc]
                    for item in self.table.get_children():
                        self.table.delete(item)
                    for row in rows:
                        self.table.insert("", "end", values=(
                            row["slot"], f'{row["state"]}/{row["activity"]}', row["cpus"],
                            row["cpus_usage"], row["cpu_usage_percent"], row["ad_age_seconds"]
                        ))
                    self.status.set(f"显示 {len(rows)} 个执行槽；本次写入 {saved} 条采样记录。CSV: {self.path.get()}")
                elif kind == "error":
                    self.status.set(f"查询或写入失败：{payload}")
                elif kind == "stopped":
                    self.worker = None
                    self.start_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    self.status.set("监控已停止。")
        except queue.Empty:
            pass
        self.after(100, self.drain_messages)

    def plot_csv(self) -> None:
        chosen = filedialog.askopenfilename(parent=self, title="选择要绘制的 CSV",
                                             initialdir=str(Path(self.path.get()).parent),
                                             filetypes=[("CSV", "*.csv")])
        if not chosen:
            return
        try:
            series = read_plot_rows(Path(chosen))
            if not series:
                raise ValueError("CSV 中没有可绘制的记录。")
            PlotWindow(self, Path(chosen), series)
        except (OSError, ValueError, ImportError) as exc:
            messagebox.showerror("无法绘图", str(exc), parent=self)

    def close(self) -> None:
        self.stop_event.set()
        self.destroy()


if __name__ == "__main__":
    if (sys.platform == "win32" and importlib.util.find_spec("matplotlib") is None
            and YADOF_PYTHONW.is_file()
            and Path(sys.executable).resolve() != YADOF_PYTHONW.resolve()):
        raise SystemExit(subprocess.call([str(YADOF_PYTHONW), str(Path(__file__).resolve())]))
    MonitorApp().mainloop()
