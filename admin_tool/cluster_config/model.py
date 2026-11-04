"""Validated settings and native HTCondor/frpc configuration generation."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import ipaddress
import json
import os
from pathlib import Path
import re
import socket

DATA = Path(os.environ.get("PROGRAMDATA", str(Path.home()))) / "Yadof"
NAME = re.compile(r"^[A-Za-z0-9_.-]+$")
ASSIGNMENT = re.compile(r"^\s*([A-Za-z_][\w.]*)\s*=", re.I)


@dataclass
class Proxy:
    name: str = ""
    secretKey: str = ""
    localPort: int = 9618


@dataclass
class Visitor:
    name: str = ""
    serverName: str = ""
    secretKey: str = ""
    bindPort: int = 29618
    serverUser: str = ""


@dataclass
class Settings:
    root_config: str = ""
    port: int = 9618
    role: str = "worker"
    execute: bool = True
    cpus: int = 1
    memory_mb: int = 1024
    disk_mb: int = 4096
    execute_dir: str = "D:/condor/execute"
    timeout_enabled: bool = False
    timeout_seconds: int = 3600
    mode: str = "lan"
    interface: str = ""
    manager: str = ""
    manager_port: int = 9618
    frpc_exe: str = ""
    frpc_config: str = str(DATA / "frpc.toml")
    server: str = ""
    server_port: int = 7000
    token_mode: str = "file"
    token_file: str = ""
    token: str = ""
    private_network: str = ""
    manager_visitor: str = ""
    proxies: list[Proxy] = field(default_factory=list)
    visitors: list[Visitor] = field(default_factory=list)

    def state(self) -> dict:
        value = asdict(self)
        value.pop("token")
        # Secrets have one owner: frpc.toml. GUI state contains no credentials.
        for entries in (value["proxies"], value["visitors"]):
            for entry in entries:
                entry.pop("secretKey")
        return value

    @classmethod
    def from_state(cls, value: dict) -> Settings:
        value = dict(value)
        value["proxies"] = [Proxy(**p) for p in value.get("proxies", [])]
        value["visitors"] = [Visitor(**p) for p in value.get("visitors", [])]
        return cls(**value)

    def validate(self, *, check_files: bool = True) -> None:
        def port(value, label):
            if type(value) is not int or not 1 <= value <= 65535:
                raise ValueError(f"{label}必须为 1–65535")
        port(self.port, "HTCondor 监听端口")
        if self.role not in {"manager", "submit", "worker"} or self.mode not in {"lan", "frp"}:
            raise ValueError("请选择角色与连接方式")
        if self.role == "worker" and not self.execute:
            raise ValueError("worker 必须启用本机执行资源")
        for value, label in ((self.cpus, "CPU"), (self.memory_mb, "内存"), (self.disk_mb, "磁盘"),
                             (self.timeout_seconds, "超时秒数")):
            if type(value) is not int or not 1 <= value <= 2**31 - 1:
                raise ValueError(f"{label}必须为正整数，且不超过 2147483647")
        for value in (self.root_config, self.execute_dir, self.frpc_config):
            if not value or any(c in value for c in '\r\n\0$"'):
                raise ValueError("配置/执行目录不能为空，也不能包含换行、引号或 $ 宏")
        execute = Path(self.execute_dir)
        if not execute.is_absolute() or execute == Path(execute.anchor):
            raise ValueError("执行目录必须为本地磁盘上的非根绝对路径")
        if any(p.is_symlink() or (p.exists() and getattr(p.lstat(), "st_file_attributes", 0) & 0x400)
               for p in (execute, *execute.parents)):
            raise ValueError("执行目录不能穿过符号链接或联接点")
        if os.name == "nt":
            import ctypes
            if ctypes.windll.kernel32.GetDriveTypeW(execute.anchor) != 3:
                raise ValueError("执行目录必须位于本地固定磁盘")
            protected = [Path(os.environ[x]).resolve() for x in ("WINDIR", "ProgramFiles", "ProgramData") if x in os.environ]
            protected += [Path(__file__).resolve().parents[2]]
            if any(execute.resolve().is_relative_to(p) for p in protected):
                raise ValueError("执行目录不能位于系统、软件、HTCondor 配置或凭据目录内")
            config_dir = Path(self.root_config).resolve().parent
            if execute.resolve() == config_dir or any(execute.resolve().is_relative_to(config_dir / name)
                    for name in ("tokens.d", "passwords.d", "log", "spool", "bin", "sbin")):
                raise ValueError("执行目录不能覆盖 HTCondor 配置、凭据、日志或程序目录")
        if self.mode == "lan":
            try:
                address = ipaddress.ip_address(self.interface)
                if address.version != 4 or address.is_loopback or address.is_unspecified or address.is_link_local:
                    raise ValueError()
            except ValueError:
                raise ValueError("请选择具有有效 IPv4 地址的局域网网卡") from None
            port(self.manager_port, "Manager 端口")
            if self.role != "manager" and not re.fullmatch(r"[A-Za-z0-9_.-]+", self.manager):
                raise ValueError("请输入 Manager 主机名或 IPv4 地址")
            return
        if not self.server or any(c.isspace() for c in self.server) or "/" in self.server:
            raise ValueError("请输入 VPS 主机名或 IP（不带协议）")
        port(self.server_port, "FRP server port")
        if self.token_mode not in {"file", "token"}:
            raise ValueError("请选择 token 文件或密钥")
        if self.token_mode == "token" and not self.token.strip():
            raise ValueError("token 密钥不能为空")
        if self.token_mode == "file":
            if not Path(self.token_file).is_absolute():
                raise ValueError("请选择 token 文件的绝对路径")
            if check_files and not Path(self.token_file).read_text(encoding="utf-8-sig").strip():
                raise ValueError("token 文件为空")
        if not NAME.fullmatch(self.private_network):
            raise ValueError("请输入两端相同的私网名称（字母、数字、_、.、-）")
        names, ports = set(), {self.port}
        if not self.proxies or not self.visitors:
            raise ValueError("双向 STCP 至少需要一个 proxy 和一个 visitor")
        for entry in [*self.proxies, *self.visitors]:
            if not NAME.fullmatch(entry.name) or entry.name in names or not entry.secretKey.strip():
                raise ValueError("STCP 条目名称必须有效且唯一，secretKey 不能为空")
            names.add(entry.name)
            if isinstance(entry, Proxy):
                if entry.localPort != self.port:
                    raise ValueError("proxy localPort 必须等于本机 HTCondor 监听端口")
            else:
                if not NAME.fullmatch(entry.serverName):
                    raise ValueError("visitor serverName 必须为对端 proxy 名称")
                port(entry.bindPort, "visitor bindPort")
                if entry.bindPort in ports:
                    raise ValueError("visitor 本地端口不能重复或与 HTCondor 监听端口相同")
                ports.add(entry.bindPort)
        if self.role != "manager" and self.manager_visitor not in {v.name for v in self.visitors}:
            raise ValueError("请选择指向 Manager 的 visitor")
        if check_files and not Path(self.frpc_exe).is_file():
            raise ValueError("请选择 frpc.exe")


def frpc_text(cfg: Settings) -> str:
    q = lambda s: json.dumps(s, ensure_ascii=False)
    lines = [f"serverAddr = {q(cfg.server)}", f"serverPort = {cfg.server_port}",
             'auth.method = "token"', 'transport.tls.enable = true']
    if cfg.token_mode == "file":
        lines += ['auth.tokenSource.type = "file"', f"auth.tokenSource.file.path = {q(cfg.token_file)}"]
    else:
        lines += [f"auth.token = {q(cfg.token)}"]
    for p in cfg.proxies:
        lines += ["", "[[proxies]]", f"name = {q(p.name)}", 'type = "stcp"',
                  f"secretKey = {q(p.secretKey)}", 'localIP = "127.0.0.1"', f"localPort = {p.localPort}"]
    for v in cfg.visitors:
        lines += ["", "[[visitors]]", f"name = {q(v.name)}", 'type = "stcp"',
                  f"serverName = {q(v.serverName)}", f"serverUser = {q(v.serverUser)}",
                  f"secretKey = {q(v.secretKey)}", 'bindAddr = "127.0.0.1"', f"bindPort = {v.bindPort}"]
    return "\n".join(lines) + "\n"


def read_frpc(cfg: Settings) -> None:
    import tomllib
    value = tomllib.loads(Path(cfg.frpc_config).read_text(encoding="utf-8-sig"))
    cfg.server, cfg.server_port = value.get("serverAddr", ""), value.get("serverPort", 7000)
    auth = value.get("auth", {})
    source = auth.get("tokenSource", {})
    cfg.token_mode = "file" if source else "token"
    cfg.token_file = source.get("file", {}).get("path", "")
    cfg.token = auth.get("token", "")
    if any(e.get("type") != "stcp" for key in ("proxies", "visitors") for e in value.get(key, [])):
        raise ValueError("所选文件包含其他类型的隧道，请为 Yadof 选择独立的 frpc TOML")
    cfg.proxies = [Proxy(p["name"], p.get("secretKey", ""), p.get("localPort", 9618)) for p in value.get("proxies", [])]
    cfg.visitors = [Visitor(v["name"], v["serverName"], v.get("secretKey", ""), v["bindPort"], v.get("serverUser", ""))
                    for v in value.get("visitors", [])]
    if any(p.get("localIP", "127.0.0.1") != "127.0.0.1" for p in value.get("proxies", [])) or any(
            v.get("bindAddr", "127.0.0.1") != "127.0.0.1" for v in value.get("visitors", [])):
        raise ValueError("STCP proxy/visitor 必须使用 127.0.0.1")


def condor_values(cfg: Settings, *, detached=False) -> dict[str, str]:
    daemons = ["MASTER"]
    if not detached:
        if cfg.role == "manager":
            daemons += ["COLLECTOR", "NEGOTIATOR", "SCHEDD"]
        elif cfg.role == "submit":
            daemons += ["SCHEDD"]
        if cfg.execute:
            daemons += ["STARTD"]
    endpoint = f"{cfg.interface}:{cfg.port}" if cfg.role == "manager" else f"{cfg.manager}:{cfg.manager_port}"
    if cfg.mode == "frp" and not detached:
        target = cfg.port if cfg.role == "manager" else next(v.bindPort for v in cfg.visitors if v.name == cfg.manager_visitor)
        endpoint = f"127.0.0.1:{target}"
    values = {
        "DAEMON_LIST": ", ".join(daemons), "CONDOR_HOST": "" if detached else endpoint,
        "COLLECTOR_HOST": "" if detached else endpoint, "USE_SHARED_PORT": "True", "SHARED_PORT_PORT": str(cfg.port),
        "COLLECTOR_PORT": str(cfg.port), "COLLECTOR_USES_SHARED_PORT": "True", "UPDATE_COLLECTOR_WITH_TCP": "True",
        "NETWORK_INTERFACE": "127.0.0.1" if cfg.mode == "frp" else cfg.interface,
        "BIND_ALL_INTERFACES": "False", "ENABLE_IPV4": "True", "ENABLE_IPV6": "False",
        "PRIVATE_NETWORK_NAME": cfg.private_network if cfg.mode == "frp" and not detached else "",
        "PRIVATE_NETWORK_INTERFACE": "127.0.0.1" if cfg.mode == "frp" and not detached else "",
        "CCB_ADDRESS": "", "TCP_FORWARDING_HOST": "", "FLOCK_TO": "", "FLOCK_COLLECTOR_HOSTS": "",
        "FLOCK_NEGOTIATOR_HOSTS": "", "START": str(cfg.execute and not detached),
        "EXECUTE": cfg.execute_dir.replace("\\", "/"), "NUM_CPUS": str(cfg.cpus), "MEMORY": str(cfg.memory_mb),
        "DISK": str(cfg.disk_mb * 1024), "NUM_SLOTS": "1", "NUM_SLOTS_TYPE_1": "1",
        "SLOT_TYPE_1": "100%", "SLOT_TYPE_1_PARTITIONABLE": "True",
    }
    for daemon in ("MASTER", "STARTD", "SCHEDD", "COLLECTOR", "NEGOTIATOR", "SHARED_PORT"):
        values[f"{daemon}.CCB_ADDRESS"] = ""
    # A user-selected hard runtime ceiling, independent of interactive-idle policy.
    limit = f'(JobState == "Running") && ((time() - JobCurrentStartDate) > {cfg.timeout_seconds})'
    active = cfg.timeout_enabled and not detached
    values.update({"PREEMPT": limit if active else "False", "STARTD.PREEMPT": limit if active else "False",
                   "WANT_SUSPEND": "False", "STARTD.WANT_SUSPEND": "False",
                   "MAXJOBRETIREMENTTIME": "0" if active else "2147483647",
                   "SUSPEND": "False", "STARTD.SUSPEND": "False"})
    return values


def clean_config(text: str, replace=()) -> str:
    """Remove old GUI metadata and replace native assignments, including continuations."""
    result, skip = [], False
    replace = {key.upper() for key in replace}
    for line in text.splitlines():
        if skip:
            skip = line.rstrip().endswith("\\")
            continue
        match = ASSIGNMENT.match(line)
        key = match[1].upper() if match else ""
        if "YADOF_" in key or key in replace or re.match(r"\s*use\s+POLICY\s*:\s*Preempt_if_Runtime_Exceeds", line, re.I):
            skip = line.rstrip().endswith("\\")
            continue
        if key in {"STARTD_ATTRS", "MASTER_ATTRS", "SCHEDD_ATTRS"}:
            prefix, value = line.split("=", 1)
            line = prefix + "= " + ", ".join(x for x in re.split(r"[,\s]+", value.strip()) if x and "YADOF_" not in x.upper())
        elif not line.lstrip().startswith("#") and "YADOF_" in line.upper():
            raise ValueError("旧配置仍引用 YADOF_*；请先移除该自定义表达式")
        result.append(line)
    return "\n".join(result).rstrip() + "\n"


STATUS_FIELDS = ("Name", "Activity", "GlobalJobId", "Cpus", "Memory", "Disk", "CpusUsage", "MyAddress")


def status_rows(output: str) -> list[tuple[str, ...]]:
    ads = json.loads(output)
    def number(value, divisor=1):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return "—"
        return f"{value / divisor:,.2f}".rstrip("0").rstrip(".")
    return [tuple(str(ad.get(k) or "—") if k in {"Name", "Activity", "GlobalJobId", "MyAddress"}
                  else number(ad.get(k), 1024 if k == "Disk" else 1) for k in STATUS_FIELDS) for ad in ads]
