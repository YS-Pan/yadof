"""Offline tests: no service changes or live cluster writes."""
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import tomllib

import pytest

from admin_tool.cluster_config.model import Proxy, Settings, Visitor, clean_config, condor_values, frpc_text, read_frpc, status_rows
from admin_tool.cluster_config.runtime import Backend, config_path


def sample(**values):
    return replace(Settings(root_config="D:/condor/condor_config", execute_dir="D:/condor_execution_test",
        mode="frp", port=25564, server="vps.example.org", token_mode="token", token="sample-only",
        private_network="pool-a", manager_visitor="to-manager",
        proxies=[Proxy("worker", "proxy-key", 25564)],
        visitors=[Visitor("to-manager", "manager", "visitor-key", 9618)]), **values)


@pytest.mark.parametrize("role,daemons", [("manager", "MASTER, COLLECTOR, NEGOTIATOR, SCHEDD, STARTD"),
    ("submit", "MASTER, SCHEDD, STARTD"), ("worker", "MASTER, STARTD")])
def test_native_roles_and_routing(role, daemons):
    cfg = sample(role=role)
    cfg.validate(check_files=False)
    values = condor_values(cfg)
    assert values["DAEMON_LIST"] == daemons
    assert values["COLLECTOR_HOST"] == ("127.0.0.1:25564" if role == "manager" else "127.0.0.1:9618")
    assert values["CCB_ADDRESS"] == ""
    assert not any("YADOF_" in key for key in values)
    assert values["DISK"] == str(cfg.disk_mb * 1024)


def test_lan_and_timeout_toggle():
    cfg = sample(mode="lan", interface="192.168.10.2", manager="manager", manager_port=19618, timeout_enabled=True)
    cfg.validate(check_files=False)
    values = condor_values(cfg)
    assert values["COLLECTOR_HOST"] == "manager:19618"
    assert "3600" in values["STARTD.PREEMPT"]
    assert condor_values(replace(cfg, timeout_enabled=False))["STARTD.PREEMPT"] == "False"
    assert condor_values(replace(cfg, visitors=[]), detached=True)["START"] == "False"


@pytest.mark.parametrize("change", [dict(port=0), dict(visitors=[Visitor("v", "m", "k", 25564)]),
    dict(proxies=[Proxy("w", "k", 9618)]), dict(token=""), dict(manager_visitor="missing"),
    dict(cpus=0), dict(private_network="bad name"), dict(execute=False)])
def test_reject_invalid_settings(change):
    with pytest.raises(ValueError):
        sample(**change).validate(check_files=False)


def test_frpc_roundtrip_and_secret_ownership(tmp_path):
    cfg = sample(token='test\\"\n密钥')
    text = frpc_text(cfg)
    parsed = tomllib.loads(text)
    assert parsed["auth"]["token"] == cfg.token
    assert parsed["visitors"][0]["type"] == "stcp"
    assert "YADOF_" not in text
    assert "sample-only" not in json.dumps(cfg.state())
    assert "secretKey" not in json.dumps(cfg.state())
    path = tmp_path / "frpc.toml"
    path.write_text(text, encoding="utf-8")
    restored = sample(frpc_config=str(path))
    read_frpc(restored)
    assert restored.token == cfg.token
    assert restored.proxies == cfg.proxies
    file_cfg = replace(cfg, token_mode="file", token_file="D:/token")
    auth = tomllib.loads(frpc_text(file_cfg))["auth"]
    assert "token" not in auth
    assert auth["tokenSource"]["file"]["path"] == "D:/token"


def test_remove_metadata_preserve_native_customization():
    text = 'YADOF_POOL_ROLE = Worker\nSTARTD_ATTRS = Foo, YADOF_EXECUTE_READY\nSTARTER_NUM_THREADS_ENV_VARS = OMP_NUM_THREADS\nuse POLICY : Preempt_if_Runtime_Exceeds(2400)\nPREEMPT = old\n'
    cleaned = clean_config(text, ["PREEMPT"])
    assert "YADOF_" not in cleaned
    assert "STARTD_ATTRS = Foo" in cleaned
    assert "OMP_NUM_THREADS" in cleaned
    assert "Preempt_if" not in cleaned


def test_status_keeps_job_and_address_without_machine():
    row, = status_rows(json.dumps([dict(Name="slot1", Machine="hidden", Activity="Busy", GlobalJobId="node#1.0#2",
                                      Cpus=4, Memory=1024, Disk=4096, CpusUsage=2.5, MyAddress="<127.0.0.1:9618?sock=x>")]))
    assert row == ("slot1", "Busy", "node#1.0#2", "4", "1,024", "4", "2.5", "<127.0.0.1:9618?sock=x>")
    assert "hidden" not in row


def test_metadata_cleanup_preserves_yadof_checkout_paths():
    text = 'LOCAL_DIR = D:/yadof_latest/temp\nLOCAL_CONFIG_FILE = D:\\yadof_latest\\condor_config.local\n'
    assert clean_config(text) == text
    with pytest.raises(ValueError):
        clean_config('START = $(YADOF_EXECUTE_READY)\n')


@pytest.mark.parametrize("key", ["STARTD_ATTRS", "MASTER_ATTRS", "SCHEDD_ATTRS"])
def test_metadata_cleanup_handles_continued_attribute_lists(key):
    text = (f'{key} = Keep, \\\n'
            '# old advertised attributes \\\n'
            '    YADOF_EXECUTE_READY, \\\n'
            '    KeepToo, YADOF_EXECUTE_DIR\n'
            'STARTER_NUM_THREADS_ENV_VARS = OMP_NUM_THREADS\n')
    cleaned = clean_config(text)
    assert f'{key} = Keep, KeepToo\n' in cleaned
    assert 'STARTER_NUM_THREADS_ENV_VARS = OMP_NUM_THREADS\n' in cleaned
    assert 'YADOF_' not in cleaned


def test_metadata_cleanup_ignores_comments_inside_removed_continuation():
    text = ('YADOF_OLD = first \\\n'
            '# explanatory comment\n'
            '    second\n'
            'STARTER_NUM_THREADS_ENV_VARS = OMP_NUM_THREADS\n')
    assert clean_config(text) == 'STARTER_NUM_THREADS_ENV_VARS = OMP_NUM_THREADS\n'


@pytest.mark.parametrize("text", [
    'LABEL = "YADOF_worker"\n',
    'USER_JOB_WRAPPER = yadof_job.exe\n',
    'REQUIREMENTS = (Name == "YADOF_worker")\n',
])
def test_metadata_cleanup_preserves_literal_names(text):
    assert clean_config(text) == text


@pytest.mark.parametrize("value", ['$(YADOF_READY)', 'TARGET.YADOF_READY', "TARGET.'YADOF_READY'", '"$(yadof_ready:False)"'])
def test_legacy_reference_error_identifies_source_without_values(value):
    with pytest.raises(ValueError) as error:
        clean_config(f'# native customization\nCUSTOM_POLICY = {value} && "private-value"\n',
                     source=Path('other-node/condor_config.local'))
    message = str(error.value)
    assert 'condor_config.local:2' in message
    assert 'CUSTOM_POLICY' in message
    assert 'YADOF_READY' in message.upper()
    assert 'private-value' not in message


def test_real_condor_parser_and_frpc(tmp_path):
    import shutil
    condor = shutil.which("condor_config_val")
    frpc = Path("D:/FRP/frp_0.71.0_windows_amd64/frpc.exe")
    if not condor or not frpc.is_file():
        pytest.skip("native validators unavailable")
    root = tmp_path / "condor_config"
    local = tmp_path / "condor_config.local"
    root.write_text(f'RELEASE_DIR = D:/condor\nLOCAL_DIR = {tmp_path.as_posix()}\nLOCAL_CONFIG_FILE = {config_path(local)}\n', encoding="utf-8")
    local.write_text('YADOF_POOL_ROLE = Worker\nSTARTER_NUM_THREADS_ENV_VARS = OMP_NUM_THREADS\n'
                     'STARTD_ATTRS = Keep, \\\n'
                     '  YADOF_EXECUTE_READY, KeepToo\n'
                     'USER_JOB_WRAPPER = yadof_job.exe\n', encoding="utf-8")
    cfg = sample(root_config=str(root), frpc_exe=str(frpc))
    stage = tmp_path / "stage"
    stage.mkdir()
    changes, _ = Backend().plan(cfg, stage)
    assert "YADOF_" not in changes[local.resolve()]
    assert "OMP_NUM_THREADS" in changes[local.resolve()]
    assert "STARTD_ATTRS = Keep, KeepToo" in changes[local.resolve()]
    assert "USER_JOB_WRAPPER = yadof_job.exe" in changes[local.resolve()]
    assert "sample-only" not in changes[root.resolve()]


def test_plan_reports_the_loaded_file_and_line_before_any_mutation(tmp_path):
    root, local, stage = tmp_path / 'condor_config', tmp_path / 'legacy.local', tmp_path / 'stage'
    root.write_text('RELEASE_DIR = D:/condor\n', encoding='utf-8')
    local.write_text('# custom policy\nCUSTOM_POLICY = TARGET.YADOF_EXECUTE_READY\n', encoding='utf-8')
    stage.mkdir()
    original = {p: p.read_bytes() for p in (root, local)}
    def run(args, **kwargs):
        assert args == ['condor_config_val', '-config']
        return f'{root}\n{local}'
    def control(*args, **kwargs):
        pytest.fail('configuration planning must not change services')
    with pytest.raises(ValueError) as error:
        Backend(run=run, control=control).plan(sample(root_config=str(root)), stage)
    assert f'{local.resolve()}:2' in str(error.value)
    assert 'CUSTOM_POLICY' in str(error.value)
    assert all(p.read_bytes() == data for p, data in original.items())
    assert not list(stage.iterdir())


def test_failed_start_restores_files_and_lifecycle(tmp_path):
    root, state = tmp_path / "condor_config", tmp_path / "state.json"
    root.write_text("original", encoding="utf-8")
    calls = []
    def control(action, **kwargs):
        calls.append(action)
        if action == "Snapshot":
            return '{"running":true,"startMode":"Auto"}'
        if action == "Start":
            raise RuntimeError("simulated startup failure")
    backend = Backend(state_path=state, control=control)
    backend.plan = lambda cfg, work, **kwargs: ({root: "changed"}, {root: "original"})
    cfg = sample(root_config=str(root))
    with pytest.raises(RuntimeError, match="原配置和服务状态已恢复"):
        backend.apply(cfg, detached=True)
    assert root.read_text() == "original"
    assert not state.exists()
    assert calls == ["Protect", "Snapshot", "Stop", "Start", "Stop", "Restore"]


def test_local_address_survives_collector_failure(tmp_path):
    address_file = tmp_path / "master_address"
    address_file.write_text("<127.0.0.1:25564?sock=master>\n", encoding="utf-8")
    def run(args, **kwargs):
        if args[0] == "condor_status":
            raise RuntimeError("collector offline")
        return str(address_file) if args[-1] == "MASTER_ADDRESS_FILE" else str(tmp_path / "missing")
    rows, addresses, error = Backend(run=run).snapshot(sample())
    assert rows == [] and "25564" in addresses[0] and error == "collector offline"
