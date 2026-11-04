"""Windows administrator GUI; worker threads never touch Tk widgets."""
from __future__ import annotations

import argparse
from dataclasses import fields
from datetime import datetime
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading

from .model import DATA, Proxy, Settings, Visitor, read_frpc
from .runtime import Backend, adapters


class AdminApp:
    def __init__(self, root, *, backend=None, poll=True):
        import tkinter as tk
        from tkinter import ttk
        self.tk, self.ttk, self.root = tk, ttk, root
        self.backend = backend or Backend()
        self.events = queue.Queue()
        self.busy, self.poll_busy, self.closed = False, False, False
        self.cfg = Settings()
        self.proxies, self.visitors = [], []
        self.vars = {}
        self.poll = poll
        root.title("Yadof · 集群配置")
        root.geometry("1140x900")
        root.minsize(960, 800)
        root.protocol("WM_DELETE_WINDOW", self.close)
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
        shell = ttk.Frame(root, padding=12)
        shell.pack(fill="both", expand=True)
        head = ttk.LabelFrame(shell, text="HTCondor", padding=8)
        head.pack(fill="x")
        self.entry(head, "根配置", "root_config", 0, browse="file")
        self.entry(head, "本机监听端口", "port", 1)
        route = ttk.Frame(head)
        route.grid(row=1, column=2, columnspan=2, sticky="w", padx=10)
        ttk.Label(route, text="连接方式：").pack(side="left")
        ttk.Radiobutton(route, text="局域网", variable=self.var("mode"), value="lan").pack(side="left")
        ttk.Radiobutton(route, text="FRP / STCP", variable=self.var("mode"), value="frp").pack(side="left")
        ttk.Label(shell, text="保存会重启本机服务；请在维护时应用。连接方式由上方选项决定。", foreground="#666666").pack(anchor="w", pady=(6, 4))
        self.tabs = ttk.Notebook(shell)
        self.tabs.pack(fill="x", pady=(0, 8))
        local, lan, frp = (ttk.Frame(self.tabs, padding=10) for _ in range(3))
        for frame, name in ((local, "本机资源"), (lan, "局域网设置"), (frp, "FRP设置")):
            self.tabs.add(frame, text=name)
        self.build_local(local)
        self.build_lan(lan)
        self.build_frp(frp)
        # Keep tabs equally sized by Notebook; fit FRP's editor into the tab area.
        actions = ttk.Frame(shell)
        actions.pack(fill="x", pady=(0, 8))
        self.save_button = ttk.Button(actions, text="保存并应用（重启服务）", command=self.save)
        self.save_button.pack(side="left")
        self.leave_button = ttk.Button(actions, text="退出所有集群", command=self.leave)
        self.leave_button.pack(side="left", padx=12)
        ttk.Button(actions, text="立即刷新", command=self.refresh).pack(side="right")
        monitor = ttk.LabelFrame(shell, text="集群资源 · 每 10 秒刷新", padding=6)
        monitor.pack(fill="both", expand=True)
        columns = ("Name", "Activity", "任务编号", "Cpus", "Memory(MB)", "Disk(MB)", "CpusUsage", "广告连接地址")
        self.status_table = ttk.Treeview(monitor, columns=columns, show="headings", height=5)
        for col, width in zip(columns, (160, 80, 160, 55, 100, 100, 85, 260)):
            self.status_table.heading(col, text=col)
            self.status_table.column(col, width=width, minwidth=45)
        self.status_table.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(monitor, orient="horizontal", command=self.status_table.xview)
        scrollbar.grid(row=1, column=0, sticky="ew")
        self.status_table.configure(xscrollcommand=scrollbar.set)
        vertical = ttk.Scrollbar(monitor, orient="vertical", command=self.status_table.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        self.status_table.configure(yscrollcommand=vertical.set)
        monitor.columnconfigure(0, weight=1)
        monitor.rowconfigure(0, weight=1)
        self.address = tk.Text(shell, height=3, wrap="word", font=("Consolas", 9), relief="flat")
        self.address.pack(fill="x", pady=(6, 0))
        self.address.insert("1.0", "本机广告连接地址：等待刷新")
        self.address.configure(state="disabled")
        self.status = tk.StringVar(value="正在读取本机配置…")
        ttk.Label(shell, textvariable=self.status, wraplength=1080).pack(anchor="w", pady=(5, 0))
        self.set_settings(self.cfg)
        root.after(100, self.drain)
        if poll:
            self.start_load()
            root.after(10000, self.tick)

    def var(self, key, boolean=False):
        if key not in self.vars:
            self.vars[key] = self.tk.BooleanVar() if boolean else self.tk.StringVar()
        return self.vars[key]

    def entry(self, frame, label, key, row, *, browse=None, secret=False):
        ttk = self.ttk
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=3)
        entry = ttk.Entry(frame, textvariable=self.var(key), show="●" if secret else "")
        entry.grid(row=row, column=1, sticky="ew", pady=3)
        frame.columnconfigure(1, weight=1)
        if browse:
            ttk.Button(frame, text="浏览…", command=lambda: self.browse(key, browse)).grid(row=row, column=2, padx=6)
        return entry

    def browse(self, key, kind):
        from tkinter import filedialog
        picker = filedialog.askdirectory if kind == "directory" else filedialog.askopenfilename
        path = picker(parent=self.root)
        if path:
            self.var(key).set(path)

    def build_local(self, frame):
        ttk = self.ttk
        role = ttk.Frame(frame)
        role.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))
        ttk.Label(role, text="本机角色：").pack(side="left")
        for name in ("manager", "submit", "worker"):
            ttk.Radiobutton(role, text=name, variable=self.var("role"), value=name, command=self.role_changed).pack(side="left", padx=8)
        ttk.Checkbutton(frame, text="启用本机执行资源（manager / submit 也可执行任务）", variable=self.var("execute", True)).grid(row=1, column=0, columnspan=3, sticky="w")
        for row, (label, key) in enumerate((("CPU（逻辑核心）", "cpus"), ("内存（MiB）", "memory_mb"), ("磁盘（MiB）", "disk_mb")), 2):
            self.entry(frame, label, key, row)
        self.entry(frame, "Condor 工作目录 / EXECUTE", "execute_dir", 5, browse="directory")
        ttk.Checkbutton(frame, text="启用超时驱逐", variable=self.var("timeout_enabled", True)).grid(row=6, column=0, sticky="w", pady=4)
        self.entry(frame, "运行时间上限（秒）", "timeout_seconds", 7)
        ttk.Label(frame, text="CPU、内存和磁盘为调度资源声明；超时从本次作业开始运行时计算。", foreground="#666666").grid(row=8, column=0, columnspan=3, sticky="w", pady=6)

    def build_lan(self, frame):
        ttk = self.ttk
        ttk.Label(frame, text="本机网卡 / IPv4").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.adapter_var = self.tk.StringVar()
        self.adapter_box = ttk.Combobox(frame, textvariable=self.adapter_var, state="readonly")
        self.adapter_box.grid(row=0, column=1, sticky="ew", pady=3)
        self.adapter_box.bind("<<ComboboxSelected>>", lambda _: self.var("interface").set(self.adapter_map.get(self.adapter_var.get(), "")))
        ttk.Button(frame, text="刷新网卡", command=self.refresh_adapters).grid(row=0, column=2, padx=6)
        self.entry(frame, "Manager 主机名 / IPv4", "manager", 1)
        self.entry(frame, "Manager 监听端口", "manager_port", 2)
        ttk.Label(frame, text="manager 角色使用本机选定网卡和上方监听端口；其他角色使用此 Manager 地址。\n沿用本机现有 HTCondor 认证和授权策略。", foreground="#666666").grid(row=3, column=0, columnspan=3, sticky="w", pady=8)
        self.refresh_adapters()

    def build_frp(self, frame):
        ttk = self.ttk
        self.entry(frame, "frpc.exe", "frpc_exe", 0, browse="file")
        ttk.Label(frame, text=f"输出：{DATA / 'frpc.toml'}", foreground="#666666").grid(row=1, column=0, columnspan=3, sticky="w")
        self.entry(frame, "VPS 地址", "server", 2)
        self.entry(frame, "Server port", "server_port", 3)
        auth = ttk.Frame(frame)
        auth.grid(row=4, column=0, columnspan=3, sticky="w")
        ttk.Label(auth, text="FRP 认证：").pack(side="left")
        ttk.Radiobutton(auth, text="Token 文件", variable=self.var("token_mode"), value="file").pack(side="left")
        ttk.Radiobutton(auth, text="输入 Token", variable=self.var("token_mode"), value="token").pack(side="left", padx=12)
        self.entry(frame, "Token 文件（FRP ≥ 0.64）", "token_file", 5, browse="file")
        self.entry(frame, "Token 密钥", "token", 6, secret=True)
        self.entry(frame, "私网名称（两端相同）", "private_network", 7)
        self.entry(frame, "指向 Manager 的 visitor 名称", "manager_visitor", 8)
        tables = ttk.Frame(frame)
        tables.grid(row=9, column=0, columnspan=3, sticky="ew", pady=5)
        for index, (kind, title, columns) in enumerate((("proxies", "本机 STCP proxies", ("name", "localPort")),
                    ("visitors", "STCP visitors → 对端 proxy", ("name", "serverName", "bindPort")))):
            box = ttk.LabelFrame(tables, text=title, padding=4)
            box.grid(row=0, column=index, sticky="nsew", padx=3)
            tables.columnconfigure(index, weight=1)
            tree = ttk.Treeview(box, columns=columns, show="headings", height=2, selectmode="browse")
            for col in columns:
                tree.heading(col, text=col)
                tree.column(col, width=130, stretch=True)
            tree.pack(fill="x")
            setattr(self, kind + "_table", tree)
            row = ttk.Frame(box)
            row.pack(fill="x")
            for title, action in (("添加", "add"), ("编辑", "edit"), ("删除", "remove")):
                ttk.Button(row, text=title, command=lambda k=kind, a=action: self.edit_tunnel(k, a)).pack(side="left", padx=2, pady=3)
        ttk.Button(frame, text="从现有 frpc TOML 导入…", command=self.import_frpc).grid(row=10, column=0, columnspan=2, sticky="w", pady=3)
        ttk.Label(frame, text="仅使用 STCP。localIP / bindAddr 固定为 127.0.0.1；对端 visitor 端口须等于本机监听端口。", foreground="#666666").grid(row=11, column=0, columnspan=3, sticky="w")

    def role_changed(self):
        if self.var("role").get() == "worker":
            self.var("execute", True).set(True)

    def refresh_adapters(self):
        try:
            self.adapter_map = dict(adapters())
            self.adapter_box.configure(values=list(self.adapter_map))
            current = self.var("interface").get()
            label = next((k for k, v in self.adapter_map.items() if v == current), "")
            self.adapter_var.set(label)
        except Exception:
            self.adapter_map = {}

    def edit_tunnel(self, kind, action):
        from tkinter import messagebox
        tree, entries = getattr(self, kind + "_table"), getattr(self, kind)
        selected = tree.selection()
        index = int(selected[0]) if selected else None
        if action != "add" and index is None:
            return
        if action == "remove":
            entries.pop(index)
            self.render_tunnels()
            return
        entry_type = Proxy if kind == "proxies" else Visitor
        entry = entries[index] if action == "edit" else entry_type()
        window = self.tk.Toplevel(self.root)
        window.title("STCP proxy" if kind == "proxies" else "STCP visitor")
        window.transient(self.root)
        window.grab_set()
        box = self.ttk.Frame(window, padding=15)
        box.pack(fill="both", expand=True)
        values = {}
        for i, field in enumerate(fields(entry)):
            self.ttk.Label(box, text=field.name).grid(row=i, column=0, sticky="w", padx=(0, 10), pady=5)
            value = getattr(entry, field.name)
            if action == "add" and field.name == "localPort":
                value = self.var("port").get()
            values[field.name] = self.tk.StringVar(value=str(value))
            self.ttk.Entry(box, textvariable=values[field.name], width=38,
                           show="●" if field.name == "secretKey" else "").grid(row=i, column=1, pady=5)
        def save():
            try:
                raw = {key: int(v.get()) if key in {"localPort", "bindPort"} else v.get() for key, v in values.items()}
                result = entry_type(**raw)
                if index is None:
                    entries.append(result)
                else:
                    entries[index] = result
                self.render_tunnels()
                window.destroy()
            except ValueError:
                messagebox.showerror("无效端口", "请输入整数端口", parent=window)
        self.ttk.Button(box, text="确定", command=save).grid(row=len(values), column=1, sticky="e", pady=8)

    def render_tunnels(self):
        for kind in ("proxies", "visitors"):
            tree = getattr(self, kind + "_table")
            tree.delete(*tree.get_children())
            for i, entry in enumerate(getattr(self, kind)):
                values = (entry.name, entry.localPort) if kind == "proxies" else (entry.name, entry.serverName, entry.bindPort)
                tree.insert("", "end", iid=str(i), values=values)

    def import_frpc(self):
        from tkinter import filedialog, messagebox
        path = filedialog.askopenfilename(parent=self.root, filetypes=[("FRP TOML", "*.toml")])
        if not path:
            return
        try:
            cfg = self.get_settings()
            cfg.frpc_config = path
            read_frpc(cfg)
            cfg.frpc_config = str(self.backend.state_path.parent / "frpc.toml")
            self.set_settings(cfg)
            self.status.set("已导入 STCP 设置；保存时生成独立配置，由 Yadof-frpc 启动任务运行。请停用旧的重复隧道。")
        except Exception as exc:
            messagebox.showerror("导入失败", str(exc), parent=self.root)

    def set_settings(self, cfg):
        for key, var in self.vars.items():
            var.set(getattr(cfg, key))
        self.proxies, self.visitors = list(cfg.proxies), list(cfg.visitors)
        self.refresh_adapters()
        self.render_tunnels()

    def get_settings(self):
        raw = self.cfg.state()
        for key, var in self.vars.items():
            value = var.get()
            if type(getattr(self.cfg, key)) is int:
                value = int(value)
            raw[key] = value
        cfg = Settings.from_state(raw)
        cfg.proxies, cfg.visitors = list(self.proxies), list(self.visitors)
        cfg.frpc_config = str(self.backend.state_path.parent / "frpc.toml")
        return cfg

    def worker(self, kind, call):
        def run():
            try:
                self.events.put((kind, call(), None))
            except Exception as exc:
                self.events.put((kind, None, str(exc)))
        threading.Thread(target=run, daemon=True).start()

    def start_load(self):
        self.worker("load", self.backend.load)

    def refresh(self):
        if self.poll_busy or self.busy or not self.cfg.root_config:
            return
        self.poll_busy = True
        self.worker("snapshot", lambda: self.backend.snapshot(self.cfg))

    def tick(self):
        if not self.closed:
            self.refresh()
            self.root.after(10000, self.tick)

    def save(self):
        from tkinter import messagebox
        if self.busy:
            return
        try:
            cfg = self.get_settings()
            cfg.validate()
        except Exception as exc:
            messagebox.showerror("设置无效", str(exc), parent=self.root)
            return
        self.apply(cfg)

    def leave(self):
        from tkinter import messagebox
        if self.busy:
            return
        if messagebox.askyesno("退出所有集群", "将停止并禁用本机 HTCondor 和 Yadof 管理的 FRP 启动任务，运行中的本机作业会中断。继续？", parent=self.root):
            # Use the last applied state, independent of unfinished form edits.
            self.apply(self.cfg, detached=True)

    def apply(self, cfg, detached=False):
        self.busy = True
        self.save_button.configure(state="disabled")
        self.leave_button.configure(state="disabled")
        self.status.set("正在校验、备份并应用配置…")
        def run():
            result = self.backend.apply(cfg, detached=detached)
            return cfg, result
        self.worker("apply", run)

    def drain(self):
        from tkinter import messagebox
        if self.closed:
            return
        while True:
            try:
                kind, value, error = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "snapshot":
                self.poll_busy = False
            if kind == "apply":
                self.busy = False
                self.save_button.configure(state="normal")
                self.leave_button.configure(state="normal")
            if error:
                self.status.set(error)
                if kind == "apply":
                    messagebox.showerror("应用失败", error, parent=self.root)
                continue
            if kind == "load":
                self.cfg = value
                self.set_settings(value)
                self.status.set("已读取本机配置；选择设置后点击保存并应用。")
                self.refresh()
            elif kind == "apply":
                self.cfg, result = value
                self.status.set(result)
                self.refresh()
            elif kind == "snapshot":
                rows, addresses, status_error = value
                self.status_table.delete(*self.status_table.get_children())
                for row in rows:
                    self.status_table.insert("", "end", values=row)
                self.address.configure(state="normal")
                self.address.delete("1.0", "end")
                self.address.insert("1.0", "本机广告连接地址：\n" + ("\n".join(addresses) or "暂无广告（本机服务可能已停止）"))
                self.address.configure(state="disabled")
                if not self.busy:
                    self.status.set(f"{datetime.now():%H:%M:%S}  " + (f"查询失败：{status_error}" if status_error else f"{len(rows)} 个资源槽"))
        self.root.after(100, self.drain)

    def close(self):
        from tkinter import messagebox
        if self.busy:
            messagebox.showinfo("正在应用", "请等待应用或回滚结束后关闭。", parent=self.root)
            return
        self.closed = True
        self.root.destroy()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Yadof Windows 集群配置")
    parser.add_argument("--smoke-test", action="store_true", help="仅构建界面，不读取或修改服务，自动关闭")
    args = parser.parse_args(argv)
    if os.name == "nt" and not args.smoke_test:
        import ctypes
        if not ctypes.windll.shell32.IsUserAnAdmin():
            executable = Path(sys.executable).with_name("pythonw.exe")
            entry = Path(__file__).resolve().parents[2] / "admin_config.pyw"
            result = ctypes.windll.shell32.ShellExecuteW(None, "runas", str(executable),
                subprocess.list2cmdline(["-X", "utf8", "-B", str(entry)]), str(entry.parent), 1)
            if result <= 32:
                import tkinter.messagebox
                tkinter.messagebox.showerror("需要管理员权限", "Windows 未授予修改 HTCondor 服务所需的管理员权限。")
                return 1
            return 0
    import tkinter as tk
    root = tk.Tk()
    AdminApp(root, poll=not args.smoke_test)
    if args.smoke_test:
        root.after(800, root.destroy)
    root.mainloop()
    return 0
