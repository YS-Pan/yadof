from __future__ import annotations

import ast

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


def test_legacy_template_is_migrated_and_constraints_are_preserved():
    legacy = """
from parameters_constraints_class import para

PARAMETERS = (
    para("old", ((0, 1),), value=0.5, normValue=float("nan"), unit="mm"),
)

CONSTRAINTS = (
    "$length - 1.2",
)
"""

    source = generator._build_parameters_constraints_text(_parameters(), legacy)

    ast.parse(source)
    assert "Parameter('length', ((1, 2),), unit='mm')" in source
    assert '"$length - 1.2"' in source
    assert "def get_parameters()" in source
    assert "para(" not in source
