from __future__ import annotations

import ast

import pytest

from project.tools.specific.hfss import get_para_and_range_direct as generator


def _parameters():
    return [
        generator.OptParam("length", ((1.0, 2.0),), 1.5, "mm"),
        generator.OptParam("mode", (1.0, 2.0, 3.0), 2.0, ""),
    ]


def test_generated_parameters_use_current_parameter_api():
    source = generator._build_parameters_constraints_text(_parameters(), None)

    ast.parse(source)
    assert "from .parameters_constraints_class import Parameter" in source
    assert "Parameter('length', ((1, 2),), unit='mm')" in source
    assert "Parameter('mode', (1, 2, 3), unit='')" in source
    assert "def get_parameters()" in source
    assert "para(" not in source
    assert "normValue" not in source


def test_noncurrent_template_is_rejected_instead_of_migrated():
    old_source = """
from parameters_constraints_class import para

PARAMETERS = (
    para("old", ((0, 1),), value=0.5, normValue=float("nan"), unit="mm"),
)

CONSTRAINTS = (
    "$length - 1.2",
)
"""

    with pytest.raises(ValueError, match="current Parameter contract"):
        generator._build_parameters_constraints_text(_parameters(), old_source)


def test_direct_parser_tolerates_non_utf8_bytes(tmp_path):
    aedt_path = tmp_path / "model.aedt"
    aedt_path.write_bytes(
        b"VariableProp('length', 'VariableProp', '', '1.5mm')\n"
        b"\xff\xfe embedded payload\n"
        b"length(i=true, int=false, Min='1mm', Max='2mm', Level='[1 : 2] mm')\n"
    )

    parameters = generator._collect_parameters_from_aedt_file(aedt_path)

    assert parameters == [generator.OptParam("length", ((1.0, 2.0),), 1.5, "mm")]


def test_single_aedt_scan_uses_the_only_project(tmp_path):
    expected = tmp_path / "only.aedt"
    expected.write_bytes(b"")

    assert generator._scan_single_aedt_file(tmp_path) == expected


def test_single_aedt_scan_requires_an_unambiguous_project(tmp_path):
    with pytest.raises(FileNotFoundError):
        generator._scan_single_aedt_file(tmp_path)

    (tmp_path / "one.aedt").write_bytes(b"")
    (tmp_path / "two.aedt").write_bytes(b"")
    with pytest.raises(RuntimeError, match="Multiple .aedt projects"):
        generator._scan_single_aedt_file(tmp_path)
