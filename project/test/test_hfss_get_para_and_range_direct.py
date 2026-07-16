from __future__ import annotations

import ast
from pathlib import Path
from uuid import uuid4

import pytest

from project.tools.specific.hfss import get_para_and_range_direct as generator


def _parameters() -> tuple[list[generator.OptParam], tuple[str, str]]:
    names = tuple(f"parameter_{index}" for index in range(2))
    parameters = [
        generator.OptParam(names[0], ((1.0, 2.0),), 1.5, "mm"),
        generator.OptParam(names[1], (1.0, 2.0, 3.0), 2.0, ""),
    ]
    return parameters, names


def _temporary_aedt_path(tmp_path: Path) -> Path:
    return tmp_path / f"synthetic_{uuid4().hex}.aedt"


def test_generated_parameters_use_current_parameter_api():
    parameters, names = _parameters()

    source = generator._build_parameters_constraints_text(parameters, None)

    ast.parse(source)
    assert "from .parameters_constraints_class import Parameter" in source
    assert f"Parameter({names[0]!r}, ((1, 2),), unit='mm')" in source
    assert f"Parameter({names[1]!r}, (1, 2, 3), unit='')" in source
    assert "def get_parameters()" in source
    assert "para(" not in source
    assert "normValue" not in source


def test_noncurrent_template_is_rejected_instead_of_migrated():
    parameters, _ = _parameters()
    legacy_name = f"parameter_{uuid4().hex}"
    old_source = f'''
from parameters_constraints_class import para

PARAMETERS = (
    para({legacy_name!r}, ((0, 1),), value=0.5, normValue=float("nan"), unit="mm"),
)

CONSTRAINTS = ()
'''

    with pytest.raises(ValueError, match="current Parameter contract"):
        generator._build_parameters_constraints_text(parameters, old_source)


def test_direct_parser_tolerates_non_utf8_bytes(tmp_path):
    variable_name = f"parameter_{uuid4().hex}"
    aedt_path = _temporary_aedt_path(tmp_path)
    aedt_path.write_bytes(
        f"VariableProp('{variable_name}', 'VariableProp', '', '1.5mm')\n".encode("ascii")
        + b"\xff\xfe embedded payload\n"
        + f"{variable_name}(i=true, int=false, Min='1mm', Max='2mm', Level='[1 : 2] mm')\n".encode(
            "ascii"
        )
    )

    parameters = generator._collect_parameters_from_aedt_file(aedt_path)

    assert parameters == [generator.OptParam(variable_name, ((1.0, 2.0),), 1.5, "mm")]


def test_single_aedt_scan_uses_the_only_project(tmp_path):
    expected = _temporary_aedt_path(tmp_path)
    expected.write_bytes(b"")

    assert generator._scan_single_aedt_file(tmp_path) == expected


def test_single_aedt_scan_requires_an_unambiguous_project(tmp_path):
    with pytest.raises(FileNotFoundError):
        generator._scan_single_aedt_file(tmp_path)

    _temporary_aedt_path(tmp_path).write_bytes(b"")
    _temporary_aedt_path(tmp_path).write_bytes(b"")
    with pytest.raises(RuntimeError, match="Multiple .aedt projects"):
        generator._scan_single_aedt_file(tmp_path)
