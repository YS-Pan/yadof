from __future__ import annotations

import json
from pathlib import Path
import runpy
import subprocess

import numpy as np
import pytest

from yadof.job_template.rawdata_contract import validate_rawdata_item
from yadof.resources import adapter_resource


REAL_RAWFILE = """Title: RC transient
Date: Sat Aug  1 00:00:00  2026
Plotname: Transient Analysis
Flags: real
No. Variables: 2
No. Points: 3
Variables:
\t0\ttime\ttime
\t1\tv(out)\tvoltage
Values:
0\t\t0.0
\t0.0
1\t\t1.0e-3
\t0.5
2\t\t2.0e-3
\t0.75
"""


COMPLEX_RAWFILE = """Title: RC AC
Date: Sat Aug  1 00:00:00  2026
Plotname: AC Analysis
Flags: complex
No. Variables: 2
No. Points: 2
Variables:
 0 frequency frequency grid=3
 1 v(out) voltage
Values:
 0 1.0e1,0.0
 1.0,-1.0
 1 1.0e2,0.0
 0.0,-2.0
"""


@pytest.fixture
def adapter():
    return runpy.run_path(str(adapter_resource("ngspice_com.py")))


def test_ngspice_session_parameters_and_driver_batch_contract(adapter, tmp_path, monkeypatch):
    executable = tmp_path / "ngspice.exe"
    executable.write_bytes(b"fake executable")
    netlist = tmp_path / "rc.cir"
    netlist.write_text(
        "RC circuit\n.param resistance=1k\nR1 in out {resistance}\n.tran 1m 2m\n.end\n",
        encoding="utf-8",
    )
    parameter_file = tmp_path / "parameters_constraints.py"
    parameter_file.write_text(
        "class Parameter:\n"
        "    def __init__(self, name, value, unit):\n"
        "        self.name, self.value, self.unit = name, value, unit\n"
        "PARAMETERS = (Parameter('resistance', 2.5, 'k'),)\n",
        encoding="utf-8",
    )

    session = adapter["solver_init"](netlist, executable=executable)
    assert adapter["set_para"](session, parameter_file) is True
    assert adapter["set_variables"](session, {"capacitance": "2u"}) is True

    def fake_run(command, **kwargs):
        assert command[:3] == [str(executable), "-n", "-b"]
        assert kwargs["cwd"] == tmp_path
        driver = Path(command[-1])
        source = driver.read_text(encoding="utf-8")
        assert "alterparam resistance = 2.5k" in source
        assert "alterparam capacitance = 2u" in source
        assert source.index("reset") < source.index("run")
        assert "write candidate.raw all" in source
        assert source.rstrip().endswith(".end")
        raw_path = tmp_path / "candidate.raw"
        raw_path.write_text(REAL_RAWFILE, encoding="utf-8")
        Path(command[command.index("-o") + 1]).write_text("ok\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="banner", stderr="")

    monkeypatch.setattr(adapter["subprocess"], "run", fake_run)
    result = adapter["analyze"](
        session,
        rawfile="candidate.raw",
        logfile="candidate.log",
        driver_netlist="candidate.cir",
    )

    assert result.returncode == 0
    assert result.rawfile == tmp_path / "candidate.raw"
    assert adapter["read_rawfile"](result.rawfile).plot_name == "Transient Analysis"


def test_ngspice_analyze_rejects_task_owned_control_blocks(adapter, tmp_path):
    executable = tmp_path / "ngspice.exe"
    executable.write_bytes(b"fake executable")
    netlist = tmp_path / "controlled.cir"
    netlist.write_text(
        "controlled\n.tran 1m 2m\n.control\nrun\n.endc\n.end\n",
        encoding="utf-8",
    )
    session = adapter["solver_init"](netlist, executable=executable)

    with pytest.raises(adapter["NgspiceError"], match="must not contain .control"):
        adapter["analyze"](session)


def test_ngspice_analyze_rejects_errors_reported_with_zero_exit_code(
    adapter, tmp_path, monkeypatch
):
    executable = tmp_path / "ngspice.exe"
    executable.write_bytes(b"fake executable")
    netlist = tmp_path / "rc.cir"
    netlist.write_text("RC circuit\n.op\n.end\n", encoding="utf-8")
    session = adapter["solver_init"](netlist, executable=executable)

    def fake_run(command, **kwargs):
        del kwargs
        Path(command[command.index("-o") + 1]).write_text(
            "Error: parameter 'missing' not found\n", encoding="utf-8"
        )
        (tmp_path / "ngspice.raw").write_text(REAL_RAWFILE, encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(adapter["subprocess"], "run", fake_run)
    with pytest.raises(adapter["NgspiceError"], match="reported an error"):
        adapter["analyze"](session)


def test_ngspice_real_rawfile_exports_schema_versioned_curve(adapter, tmp_path):
    rawfile = tmp_path / "real.raw"
    rawfile.write_text(REAL_RAWFILE, encoding="utf-8")

    output = Path(
        adapter["save_result"](
            rawfile,
            "v(out)",
            out_dir=tmp_path / "rawData",
            output_name="output_voltage",
            metadata={"task_quantity": "voltage"},
        )
    )
    loaded = validate_rawdata_item(output)
    np.testing.assert_allclose(loaded["data"], [0.0, 0.5, 0.75])
    np.testing.assert_allclose(loaded["axis_time"], [0.0, 1.0e-3, 2.0e-3])
    metadata = json.loads(str(loaded["metadata"]))
    assert metadata["schema_version"] == 1
    assert metadata["rawdata_name"] == "output_voltage"
    assert metadata["axis_names"] == ["time"]
    assert metadata["axes"][0]["unit"] == "s"
    assert metadata["task_quantity"] == "voltage"


def test_ngspice_complex_rawfile_exports_explicit_component(adapter, tmp_path):
    rawfile = tmp_path / "complex.raw"
    rawfile.write_text(COMPLEX_RAWFILE, encoding="utf-8")

    output = adapter["save_result"](
        rawfile,
        "v(out)",
        component="magnitude",
        out_dir=tmp_path,
        output_name="gain",
    )
    loaded = validate_rawdata_item(output)
    np.testing.assert_allclose(loaded["data"], [np.sqrt(2.0), 2.0])
    np.testing.assert_allclose(loaded["axis_frequency"], [10.0, 100.0])
    metadata = json.loads(str(loaded["metadata"]))
    assert metadata["ngspice_component"] == "magnitude"
    assert metadata["axes"][0]["unit"] == "Hz"


def test_ngspice_rawfile_reader_rejects_binary_data(adapter, tmp_path):
    rawfile = tmp_path / "binary.raw"
    rawfile.write_bytes(b"Title: binary\nBinary:\n\x00\x01")

    with pytest.raises(adapter["NgspiceRawFileError"], match="binary"):
        adapter["read_rawfile"](rawfile)
