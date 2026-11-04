"""Native validation, transactional file updates and Windows service lifecycle."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
import time
import uuid

from .model import DATA, Settings, clean_config, condor_values, frpc_text, read_frpc, status_rows

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def config_path(path: Path) -> str:
    """LOCAL_CONFIG_FILE is a whitespace-separated list, not a quoted path list."""
    parent = str(path.resolve().parent)
    if os.name == "nt":
        import ctypes
        buffer = ctypes.create_unicode_buffer(32768)
        if ctypes.windll.kernel32.GetShortPathNameW(parent, buffer, len(buffer)):
            parent = buffer.value
    value = str(Path(parent) / path.name).replace("\\", "/")
    if any(c.isspace() for c in value):
        raise ValueError("HTCondor 配置路径含空格且没有 Windows 短路径；请使用无空格的配置目录")
    return value


def command(args, *, env=None, timeout=15):
    result = subprocess.run([str(x) for x in args], capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=timeout, creationflags=NO_WINDOW, env=env)
    if result.returncode:
        # Native frpc diagnostics can echo credentials. Do not expose its output.
        if len(args) > 1 and args[1] == "verify":
            raise RuntimeError("frpc 校验失败，请核对版本、token 与 STCP 设置（需要 FRP ≥ 0.64）")
        raise RuntimeError((result.stderr or result.stdout or f"{args[0]} failed").strip())
    return result.stdout.strip()


def lifecycle(action, *, plan=None, target=None):
    args = ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
            Path(__file__).with_name("lifecycle.ps1"), "-Action", action]
    if plan:
        args += ["-PlanPath", plan]
    if target:
        args += ["-TargetPath", target]
    return command(args, timeout=120)


def atomic_write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class Backend:
    def __init__(self, state_path: Path = DATA / "admin_config.json", *, run=command, control=lifecycle):
        self.state_path, self.run, self.control = state_path, run, control

    def env(self, root):
        return {**os.environ, "CONDOR_CONFIG": str(root)}

    def sources(self, root=None):
        text = self.run(["condor_config_val", "-config"], env=self.env(root) if root else None)
        paths = [Path(line.strip()) for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
        if not paths or any(not path.is_file() for path in paths):
            raise ValueError("无法读取 HTCondor 配置来源")
        return list(dict.fromkeys(path.resolve() for path in paths))

    def load(self):
        if self.state_path.is_file():
            cfg = Settings.from_state(json.loads(self.state_path.read_text(encoding="utf-8-sig")))
            if Path(cfg.frpc_config).is_file():
                read_frpc(cfg)
            return cfg
        paths = self.sources()
        cfg = Settings(root_config=str(paths[0]))
        text = self.run(["condor_config_val", "-dump"], env=self.env(paths[0]))
        values = {}
        for line in text.splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                values[key.strip().upper()] = value.strip()
        def integer(key, default):
            try:
                return int(values.get(key, default))
            except ValueError:
                return default
        cfg.port = integer("SHARED_PORT_PORT", 9618)
        cfg.cpus = integer("NUM_CPUS", os.cpu_count() or 1)
        cfg.memory_mb = integer("MEMORY", 1024)
        cfg.disk_mb = max(1, integer("DISK", 4194304) // 1024)
        # Query expansion for paths because the dump may retain macros.
        cfg.execute_dir = self.run(["condor_config_val", "EXECUTE"], env=self.env(paths[0]))
        daemons = values.get("DAEMON_LIST", "").upper()
        cfg.role = "manager" if "COLLECTOR" in daemons else "submit" if "SCHEDD" in daemons else "worker"
        cfg.execute = "STARTD" in daemons
        cfg.interface = values.get("NETWORK_INTERFACE", "")
        endpoint = values.get("COLLECTOR_HOST", values.get("CONDOR_HOST", ""))
        cfg.manager, _, manager_port = endpoint.partition(":")
        cfg.manager_port = int(manager_port) if manager_port.isdigit() else 9618
        cfg.private_network = values.get("PRIVATE_NETWORK_NAME", "")
        cfg.mode = "frp" if cfg.private_network else "lan"
        preempt = values.get("STARTD.PREEMPT", values.get("PREEMPT", "False"))
        found = re.search(r"JobCurrentStartDate\)\s*>\s*(\d+)", preempt)
        cfg.timeout_enabled = found is not None
        cfg.timeout_seconds = int(found[1]) if found else 3600
        old_frpc = values.get("YADOF_STCP_PROXY_CONFIG", "").strip('"')
        if old_frpc and Path(old_frpc).is_file():
            cfg.frpc_config = old_frpc
            read_frpc(cfg)
            cfg.manager_visitor = values.get("YADOF_STCP_VISITOR_NAME", "")
        return cfg

    def snapshot(self, cfg):
        env = self.env(cfg.root_config)
        # Address files are local, work for every role and include the shared-port socket.
        addresses = []
        for macro in ("MASTER_ADDRESS_FILE", "STARTD_ADDRESS_FILE", "SCHEDD_ADDRESS_FILE", "COLLECTOR_ADDRESS_FILE"):
            try:
                value = self.run(["condor_config_val", macro], env=env, timeout=2)
                path = Path(value)
                if path.is_file():
                    address = path.read_text(encoding="utf-8", errors="replace").splitlines()[0]
                    addresses.append(f"{macro.removesuffix('_ADDRESS_FILE')}: {address}")
            except (OSError, RuntimeError, subprocess.TimeoutExpired, IndexError):
                continue
        try:
            rows = status_rows(self.run(["condor_status", "-json", "-attributes",
                         "Name,Activity,GlobalJobId,Cpus,Memory,Disk,CpusUsage,MyAddress"], env=env, timeout=6))
            error = ""
        except (OSError, RuntimeError, subprocess.TimeoutExpired, ValueError) as exc:
            rows, error = [], str(exc)
        return rows, addresses, error

    def plan(self, cfg, work: Path, *, detached=False):
        sources = self.sources(cfg.root_config)
        root = Path(cfg.root_config).resolve()
        if sources[0] != root:
            raise ValueError("请选择 condor_config 根文件")
        texts = {p: p.read_text(encoding="utf-8-sig") for p in sources}
        # Conditional/dynamic includes need manual consolidation: never silently drop them.
        for text in texts.values():
            if re.search(r"^\s*(include\s*:|LOCAL_CONFIG_FILE\s*=.*\|)", text, re.M | re.I):
                raise ValueError("配置含动态 include；请先整理为普通本地配置文件")
        local = root.with_name("condor_config.local")
        values = condor_values(cfg, detached=detached)
        directives = {"LOCAL_CONFIG_FILE", "LOCAL_CONFIG_DIR"}
        root_text = clean_config(texts[root], [*directives, *values])
        local_native = config_path(local)
        root_text += f"\nLOCAL_CONFIG_FILE = {local_native}\nLOCAL_CONFIG_DIR =\n"
        local_text = "\n".join(clean_config(texts[p], [*directives, *values]) for p in sources if p != root)
        local_text += "\n# HTCondor native settings managed by admin_config.pyw\n"
        local_text += "\n".join(f"{k} = {v}" for k, v in values.items()) + "\n"
        stage_local, stage_root = work / "condor_config.local", work / "condor_config"
        stage_local.write_text(local_text, encoding="utf-8")
        stage_root.write_text(root_text.replace(f"LOCAL_CONFIG_FILE = {local_native}",
                                               f"LOCAL_CONFIG_FILE = {config_path(stage_local)}"), encoding="utf-8")
        self.run(["condor_config_val", "-dump"], env=self.env(stage_root))
        for key in ("DAEMON_LIST", "SHARED_PORT_PORT", "COLLECTOR_HOST", "STARTD.PREEMPT", "EXECUTE"):
            actual = self.run(["condor_config_val", key], env=self.env(stage_root))
            if actual != values[key]:
                raise ValueError(f"HTCondor 校验失败：{key} 被其他配置覆盖")
        changes = {root: root_text, local: local_text}
        if cfg.mode == "frp" and not detached:
            staged = work / "frpc.toml"
            staged.write_text(frpc_text(cfg), encoding="utf-8")
            self.run([cfg.frpc_exe, "verify", "-c", staged], timeout=15)
            changes[Path(cfg.frpc_config).resolve()] = staged.read_text(encoding="utf-8")
        return changes, texts

    def apply(self, cfg, *, detached=False):
        if not detached:
            cfg.validate()
            if cfg.execute:
                self.check_resources(cfg)
        elif not Path(cfg.root_config).is_file():
            raise ValueError("请选择有效的 HTCondor 根配置")
        data = self.state_path.parent
        data.mkdir(parents=True, exist_ok=True)
        self.control("Protect", target=data)
        backup = data / "backups" / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
        backup.mkdir(parents=True)
        with tempfile.TemporaryDirectory(prefix="stage-", dir=data) as temporary:
            work = Path(temporary)
            changes, sources = self.plan(cfg, work, detached=detached)
            # Keep a file-level snapshot, including previously absent destinations.
            original = {p: p.read_bytes() if p.exists() else None for p in {*sources, *changes, self.state_path}}
            for i, (path, content) in enumerate(original.items()):
                if content is not None:
                    (backup / f"file-{i}.bak").write_bytes(content)
            (backup / "files.json").write_text(json.dumps({str(p): f"file-{i}.bak" if content is not None else None
                for i, (p, content) in enumerate(original.items())}, indent=2), encoding="utf-8")
            snapshot = json.loads(self.control("Snapshot"))
            restore = backup / "services.json"
            restore.write_text(json.dumps(snapshot), encoding="utf-8")
            action = work / "action.json"
            action.write_text(json.dumps({"detached": detached, "mode": cfg.mode, "frpc_exe": cfg.frpc_exe,
                                         "frpc_config": cfg.frpc_config}), encoding="utf-8")
            if any((p.read_bytes() if p.exists() else None) != content for p, content in original.items()):
                raise RuntimeError("校验期间配置已被其他程序修改，请重试")
            try:
                self.control("Stop")
                if cfg.execute and not detached:
                    Path(cfg.execute_dir).mkdir(parents=True, exist_ok=True)
                    self.control("ExecuteAcl", target=cfg.execute_dir)
                for path, content in changes.items():
                    if path.suffix == ".toml":
                        path.parent.mkdir(parents=True, exist_ok=True)
                        # Restrict a dedicated subdirectory, never an arbitrary user's folder.
                        if path.parent.resolve() != data.resolve():
                            raise ValueError(f"FRP 输出文件必须位于 {data} 内；请使用导入按钮读取其他文件")
                    atomic_write(path, content)
                self.control("Start", plan=action)
                if cfg.mode == "frp" and not detached:
                    for visitor in cfg.visitors:
                        with socket.create_connection(("127.0.0.1", visitor.bindPort), timeout=4):
                            pass
                state = cfg.state()
                state["role"] = cfg.role
                atomic_write(self.state_path, json.dumps(state, ensure_ascii=False, indent=2))
            except Exception as error:
                rollback_errors = []
                try:
                    self.control("Stop")
                except Exception as exc:
                    rollback_errors.append(str(exc))
                for path, content in original.items():
                    try:
                        if content is None:
                            path.unlink(missing_ok=True)
                        else:
                            path.write_bytes(content)
                    except OSError as exc:
                        rollback_errors.append(str(exc))
                try:
                    self.control("Restore", plan=restore)
                except Exception as exc:
                    rollback_errors.append(str(exc))
                suffix = "；回滚未完全成功：" + "；".join(rollback_errors) if rollback_errors else "；原配置和服务状态已恢复"
                raise RuntimeError(f"应用失败：{error}{suffix}。备份：{backup}") from error
        return f"{'已退出所有集群并禁用本机 HTCondor' if detached else '设置已保存并重启 HTCondor'}。备份：{backup}"

    @staticmethod
    def check_resources(cfg):
        import psutil
        if cfg.cpus > (os.cpu_count() or 1) or cfg.memory_mb > psutil.virtual_memory().total // 1024**2:
            raise ValueError("声明的 CPU 或内存超过本机资源")
        path = Path(cfg.execute_dir)
        while not path.exists() and path != path.parent:
            path = path.parent
        if cfg.disk_mb > shutil.disk_usage(path).free // 1024**2:
            raise ValueError("声明的磁盘超过执行目录所在磁盘的可用空间")


def adapters():
    import psutil
    return [(f"{name} — {address.address}", address.address) for name, addresses in psutil.net_if_addrs().items()
            if psutil.net_if_stats().get(name) and psutil.net_if_stats()[name].isup for address in addresses
            if address.family == socket.AF_INET and not address.address.startswith(("127.", "169.254."))]
