# tools/hfss_get_para_and_range.py
from __future__ import annotations

import argparse
import ast
import contextlib
import datetime as _dt
import math
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Union


# =========================================================
# Paths
# =========================================================
_THIS_FILE = Path(__file__).resolve()
ROOT_DIR = _THIS_FILE.parents[1]  # .../tools/ -> repo root
JOB_TEMPLATE_DIR = ROOT_DIR / "job_template"
PARAM_FILE = JOB_TEMPLATE_DIR / "parameters_constraints.py"
HISTORY_DIR = ROOT_DIR / "history"
DESIGN_NAME = "HFSSDesign4"

# Type alias matching parameters_constraints_class.py
RangeElem = Union[float, tuple[float, float]]


# =========================================================
# Helpers (file scanning, formatting, AST replacement)
# =========================================================
def _scan_single_aedt_file(folder: Path) -> Path:
    files = sorted(folder.glob("*.aedt"))
    if not files:
        raise FileNotFoundError(f"No .aedt project found in: {folder.resolve()}")
    if len(files) != 1:
        raise RuntimeError(
            f"Multiple .aedt projects found in {folder.resolve()}. "
            f"Please specify one via --project. Found: {[str(p.name) for p in files]}"
        )
    return files[0]


def _format_float(x: float) -> str:
    """Stable float formatting for writing back into a .py file."""
    return format(float(x), ".17g")


def _replace_top_level_assignment(source_text: str, *, target_name: str, replacement_block: str) -> str:
    """
    Replace a top-level assignment like `PARAMETERS = ...` with replacement_block.

    Supports:
      - ast.Assign: PARAMETERS = (...)
      - ast.AnnAssign: PARAMETERS: ... = (...)
    """
    tree = ast.parse(source_text)

    target_node: ast.AST | None = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == target_name:
                    target_node = node
                    break
        elif isinstance(node, ast.AnnAssign):
            t = node.target
            if isinstance(t, ast.Name) and t.id == target_name:
                target_node = node
        if target_node is not None:
            break

    if target_node is None:
        raise ValueError(f"Top-level `{target_name} = ...` not found; cannot replace.")

    if not hasattr(target_node, "lineno") or not hasattr(target_node, "end_lineno"):
        raise RuntimeError("AST node missing lineno/end_lineno; Python 3.8+ required for precise replacement.")

    lines = source_text.splitlines(keepends=True)
    start = int(getattr(target_node, "lineno")) - 1
    end_exclusive = int(getattr(target_node, "end_lineno"))

    if not replacement_block.endswith("\n"):
        replacement_block += "\n"

    return "".join(lines[:start]) + replacement_block + "".join(lines[end_exclusive:])


def _top_level_assignment_block(source_text: str, target_name: str) -> str | None:
    tree = ast.parse(source_text)
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else (node.target,) if isinstance(node, ast.AnnAssign) else ()
        if any(isinstance(target, ast.Name) and target.id == target_name for target in targets):
            lines = source_text.splitlines(keepends=True)
            return "".join(lines[node.lineno - 1 : node.end_lineno])
    return None


def _uses_legacy_parameter_format(source_text: str) -> bool:
    tree = ast.parse(source_text)
    has_get_parameters = any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "get_parameters"
        for node in tree.body
    )
    uses_para = any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "para"
        for node in ast.walk(tree)
    )
    return uses_para or not has_get_parameters


def _default_parameters_constraints_text(
    parameters_block: str,
    constraints_block: str | None = None,
) -> str:
    if not parameters_block.endswith("\n"):
        parameters_block += "\n"
    constraints_block = (constraints_block or "CONSTRAINTS: tuple[str, ...] = ()").strip()

    return (
        '"""\n'
        "HFSS optimization parameters generated from an AEDT project.\n"
        '"""\n'
        "\n"
        "from __future__ import annotations\n"
        "\n"
        "try:\n"
        "    from .parameters_constraints_class import Parameter\n"
        "except ImportError:\n"
        "    from parameters_constraints_class import Parameter\n"
        "\n"
        f"{parameters_block}\n"
        f"{constraints_block}\n"
        "\n"
        "\n"
        "def get_parameters() -> tuple[Parameter, ...]:\n"
        "    return tuple(PARAMETERS)\n"
    )


# =========================================================
# Helpers (HFSS variable extraction — used by PyAEDT fallback)
# =========================================================
@contextlib.contextmanager
def _suppress_output(enabled: bool = True):
    """Suppress stdout/stderr (useful to quiet AEDT/PyAEDT output)."""
    if not enabled:
        yield
        return
    with open(os.devnull, "w") as devnull:
        old_out, old_err = sys.stdout, sys.stderr
        try:
            sys.stdout = devnull
            sys.stderr = devnull
            yield
        finally:
            sys.stdout = old_out
            sys.stderr = old_err


def _get_attr(obj: Any, names: Iterable[str]) -> Any:
    """Get first existing attribute from names; if callable, call it."""
    for name in names:
        if hasattr(obj, name):
            v = getattr(obj, name)
            try:
                return v() if callable(v) else v
            except Exception:
                continue
    return None


_UNIT_RE = re.compile(r"^\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*([a-zA-Zµμ]*)\s*$")


def _parse_value_with_unit(val: Any) -> tuple[float | None, str]:
    """
    Parse '14mm' -> (14.0, 'mm'), '-30deg' -> (-30.0, 'deg'), '1e-3m' -> (0.001, 'm').
    Returns (None, '') if cannot parse as number(+optional unit).
    """
    if val is None:
        return None, ""

    if isinstance(val, (int, float)) and not (isinstance(val, float) and math.isnan(val)):
        return float(val), ""

    text = str(val).strip()
    if not text:
        return None, ""

    m = _UNIT_RE.match(text.replace(" ", ""))
    if not m:
        return None, ""

    num_s, unit = m.group(1), m.group(2) or ""
    try:
        return float(num_s), unit
    except Exception:
        return None, unit


def _is_optimization_enabled(var_obj: Any) -> bool:
    v = _get_attr(var_obj, ["is_optimization_enabled", "optimization_enabled"])
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in {"1", "true", "yes", "y"}:
        return True
    if s in {"0", "false", "no", "n", ""}:
        return False
    return bool(v)


def _get_current_value_and_unit(hfss: Any, var_name: str, var_obj: Any) -> tuple[float | None, str]:
    """
    Best-effort extraction of current variable numeric value and unit.
    """
    for src in (
        _get_attr(var_obj, ["expression"]),
        _get_attr(var_obj, ["value"]),
        _get_attr(var_obj, ["evaluated_value", "aedt_value", "string_value"]),
    ):
        if src is None:
            continue

        if isinstance(src, (int, float)):
            unit = str(_get_attr(var_obj, ["units", "unit"]) or "")
            return float(src), unit

        val, unit = _parse_value_with_unit(src)
        if val is not None:
            return val, unit

    nv = _get_attr(var_obj, ["numeric_value"])
    if nv is not None:
        try:
            val = float(nv)
            unit = str(_get_attr(var_obj, ["units", "unit"]) or "")
            return val, unit
        except Exception:
            pass

    try:
        odesign = getattr(hfss, "_odesign", None)
        if odesign is not None and hasattr(odesign, "GetVariableValue"):
            raw = odesign.GetVariableValue(var_name)
            val, unit = _parse_value_with_unit(raw)
            return val, unit
    except Exception:
        pass

    return None, ""


# =========================================================
# Data structure for collected parameters
# =========================================================
@dataclass(frozen=True)
class OptParam:
    name: str
    ranges: tuple[RangeElem, ...]   # e.g. ((lo,hi),)  or  (v1, v2, v3, ...)
    value: float
    unit: str


# =========================================================
# AEDT file parsing for Optimetrics variables (primary path)
# =========================================================

# Matches: VariableProp('name', '...', '', 'currentValue', ...)
_VAR_PROP_RE = re.compile(
    r"VariableProp\(\s*'([^']*)'\s*,\s*'[^']*'\s*,\s*'[^']*'\s*,\s*'([^']*)'"
)

# Matches optimisation-variable lines inside $begin 'Variables' … $end 'Variables'
# e.g.  $C1(i=true, int=false, Min='120uF', …, Level='[120, 240, 360, 480] uF')
_OPTIM_VAR_LINE_RE = re.compile(
    r"^\s*(\$?\w+)\((i=(?:true|false),\s*int=(?:true|false),.+)\)\s*$",
    re.MULTILINE,
)


def _parse_optim_var_attrs(attr_str: str) -> dict[str, str]:
    """
    Parse key=value pairs from the interior of an optimization-variable
    definition line.  Handles both unquoted values (``true``, ``false``)
    and single-quoted values (``'120uF'``, ``'[120, 240, 360, 480] uF'``).
    """
    result: dict[str, str] = {}
    i = 0
    n = len(attr_str)
    while i < n:
        # skip whitespace / commas
        while i < n and attr_str[i] in " ,\t\r\n":
            i += 1
        if i >= n:
            break
        # key
        key_start = i
        while i < n and attr_str[i] != "=":
            i += 1
        if i >= n:
            break
        key = attr_str[key_start:i].strip()
        i += 1  # skip '='
        if i >= n:
            break
        # value
        if attr_str[i] == "'":
            i += 1  # skip opening quote
            val_start = i
            while i < n and attr_str[i] != "'":
                i += 1
            value = attr_str[val_start:i]
            if i < n:
                i += 1  # skip closing quote
        else:
            val_start = i
            while i < n and attr_str[i] not in ", \t\r\n":
                i += 1
            value = attr_str[val_start:i].strip()
        result[key] = value
    return result


def _parse_level_string(level_str: str) -> tuple[list[RangeElem], str]:
    """
    Parse a Level string from an AEDT optimisation-variable definition.

    Continuous  : ``'[1: 15] mm'``   →  ``([(1.0, 15.0)], 'mm')``
    Discrete    : ``'[120, 240, 360, 480] uF'``  →  ``([120.0, 240.0, 360.0, 480.0], 'uF')``
    No unit     : ``'[-1: 1]'``      →  ``([(-1.0, 1.0)], '')``

    Returns ``(ranges_list, unit_string)``.
    """
    level_str = level_str.strip()
    if not level_str:
        return [], ""

    bracket_start = level_str.find("[")
    bracket_end = level_str.rfind("]")
    if bracket_start < 0 or bracket_end < 0 or bracket_end <= bracket_start:
        return [], ""

    bracket_content = level_str[bracket_start + 1 : bracket_end].strip()
    unit = level_str[bracket_end + 1 :].strip()

    # Continuous range  →  "lo : hi"
    if ":" in bracket_content:
        parts = bracket_content.split(":")
        if len(parts) != 2:
            return [], unit
        try:
            lo = float(parts[0].strip())
            hi = float(parts[1].strip())
            return [(lo, hi)], unit
        except ValueError:
            return [], unit

    # Discrete values  →  "v1, v2, v3, …"
    if "," in bracket_content:
        try:
            values: list[RangeElem] = [
                float(v.strip()) for v in bracket_content.split(",") if v.strip()
            ]
            return values, unit
        except ValueError:
            return [], unit

    # Single value
    try:
        val = float(bracket_content)
        return [val], unit
    except ValueError:
        return [], unit


def _collect_parameters_from_aedt_file(aedt_path: Path) -> list[OptParam]:
    """
    Parse the ``.aedt`` file directly to extract optimisation-included
    variables with full support for **discrete** ranges via the ``Level``
    field in the Optimetrics Variables section.

    Falls back to ``Min`` / ``Max`` (continuous) when ``Level`` is absent
    or unparseable.
    """
    text = aedt_path.read_text(encoding="utf-8")

    # ---- 1. current values from every VariableProp line ----
    var_current_values: dict[str, str] = {}
    for m in _VAR_PROP_RE.finditer(text):
        var_current_values[m.group(1)] = m.group(2)

    # ---- 2. optimisation-variable definitions ----
    optim_vars: dict[str, dict[str, str]] = {}
    for m in _OPTIM_VAR_LINE_RE.finditer(text):
        var_name = m.group(1)
        attr_str = m.group(2)
        optim_vars[var_name] = _parse_optim_var_attrs(attr_str)

    if not optim_vars:
        raise RuntimeError(
            "No optimisation variable definitions found in AEDT file. "
            "Falling back to PyAEDT."
        )

    # ---- 3. build OptParam list for included variables ----
    out: list[OptParam] = []
    for var_name in sorted(optim_vars, key=str.lower):
        attrs = optim_vars[var_name]

        # only "included" variables
        if attrs.get("i", "false").lower() != "true":
            continue

        # --- ranges from Level ---
        level_str = attrs.get("Level", "")
        ranges: list[RangeElem]
        level_unit: str
        if level_str:
            ranges, level_unit = _parse_level_string(level_str)
        else:
            ranges, level_unit = [], ""

        # fallback: Min / Max  →  single continuous interval
        if not ranges:
            min_str = attrs.get("Min", "")
            max_str = attrs.get("Max", "")
            lo_val, u_lo = _parse_value_with_unit(min_str)
            hi_val, u_hi = _parse_value_with_unit(max_str)
            if lo_val is None or hi_val is None:
                continue
            ranges = [(lo_val, hi_val)]
            level_unit = u_lo or u_hi or ""

        # --- current value ---
        val_str = var_current_values.get(var_name, "")
        if not val_str:
            # variable not found among VariableProp lines → skip
            continue
        cur, u_cur = _parse_value_with_unit(val_str)
        if cur is None:
            continue

        unit = level_unit or u_cur or ""

        # coerce to proper tuple[RangeElem, ...]
        ranges_tuple: tuple[RangeElem, ...] = tuple(
            (float(e[0]), float(e[1])) if isinstance(e, (tuple, list)) else float(e)
            for e in ranges
        )

        out.append(
            OptParam(
                name=str(var_name),
                ranges=ranges_tuple,
                value=float(cur),
                unit=str(unit),
            )
        )

    return out


# =========================================================
# PyAEDT-based collection (fallback — continuous ranges only)
# =========================================================
def _collect_optimization_parameters(hfss: Any) -> list[OptParam]:
    vm = getattr(hfss, "variable_manager", None)
    if vm is None:
        raise RuntimeError("hfss.variable_manager not found; cannot read variables.")

    variables = _get_attr(vm, ["variables"])  # usually a dict-like
    if not isinstance(variables, dict):
        raise RuntimeError("hfss.variable_manager.variables is not a dict; incompatible PyAEDT version?")

    out: list[OptParam] = []
    for var_name, var_obj in variables.items():
        try:
            if not _is_optimization_enabled(var_obj):
                continue

            min_s = _get_attr(var_obj, ["optimization_min_value"])
            max_s = _get_attr(var_obj, ["optimization_max_value"])
            lo, u_lo = _parse_value_with_unit(min_s)
            hi, u_hi = _parse_value_with_unit(max_s)

            if lo is None or hi is None:
                # Skip variables with unusable optimization ranges
                continue
            if u_lo != u_hi:
                raise ValueError(
                    f"Variable {var_name!r} optimization min/max units mismatch: {min_s!r} vs {max_s!r}"
                )

            cur, u_cur = _get_current_value_and_unit(hfss, str(var_name), var_obj)
            if cur is None:
                raise ValueError(f"Variable {var_name!r} current value is not numeric/parsible.")

            unit = u_lo
            # Be strict on unit mismatch to avoid silently wrong files
            if u_cur and unit and (u_cur != unit):
                raise ValueError(
                    f"Variable {var_name!r} unit mismatch: current={u_cur!r}, opt_range={unit!r}. "
                    f"Current value extraction returned {cur!r}{u_cur}."
                )
            if not unit and u_cur:
                unit = u_cur

            out.append(OptParam(
                name=str(var_name),
                ranges=((float(lo), float(hi)),),   # single continuous interval
                value=float(cur),
                unit=str(unit),
            ))
        except Exception:
            # Keep going; one bad variable should not block others.
            continue

    out.sort(key=lambda p: p.name.lower())
    return out


# =========================================================
# Building the PARAMETERS = (...) block
# =========================================================
def _format_ranges(ranges: tuple[RangeElem, ...]) -> str:
    """
    Format a ``ranges`` tuple for writing into a ``.py`` file.

    Examples::

        ((10, 30),)                       →  "((10, 30),)"
        (120, 240, 360, 480)              →  "(120, 240, 360, 480)"
        (3.5,)                            →  "(3.5,)"
        ((0.1, 6.2),)                     →  "((0.10000000000000001, 6.2000000000000002),)"
    """
    if not ranges:
        return "()"
    parts: list[str] = []
    for elem in ranges:
        if isinstance(elem, tuple):
            parts.append(f"({_format_float(elem[0])}, {_format_float(elem[1])})")
        else:
            parts.append(_format_float(elem))
    if len(parts) == 1:
        return "(" + parts[0] + ",)"
    return "(" + ", ".join(parts) + ")"


def _build_parameters_block(params: list[OptParam]) -> str:
    lines: list[str] = []
    lines.append("PARAMETERS = (\n")
    for p in params:
        ranges_src = _format_ranges(p.ranges)
        lines.append(f"    Parameter({p.name!r}, {ranges_src}, unit={p.unit!r}),\n")
    lines.append(")\n")
    return "".join(lines)


def _build_parameters_constraints_text(params: list[OptParam], template_text: str | None) -> str:
    parameters_block = _build_parameters_block(params)
    if template_text and not _uses_legacy_parameter_format(template_text):
        return _replace_top_level_assignment(
            template_text,
            target_name="PARAMETERS",
            replacement_block=parameters_block,
        )
    constraints_block = (
        _top_level_assignment_block(template_text, "CONSTRAINTS")
        if template_text
        else None
    )
    return _default_parameters_constraints_text(parameters_block, constraints_block)


# =========================================================
# Main flow
# =========================================================
def _open_hfss_project(project_path: Path, design_name: str | None, *, non_graphical: bool, quiet: bool) -> Any:
    # Keep imports local to avoid hard dependency when script is imported.
    try:
        from ansys.aedt.core import Hfss  # type: ignore
    except Exception:  # pragma: no cover
        try:
            from pyaedt import Hfss  # type: ignore
        except Exception as e:
            raise ImportError(
                "PyAEDT is required to run this script. "
                "Install/enable 'ansys-aedt-core' (or 'pyaedt') in your environment."
            ) from e

    with _suppress_output(enabled=quiet):
        hfss = Hfss(
            project=str(project_path),
            design=design_name,
            non_graphical=non_graphical,
            new_desktop=True,
            close_on_exit=False,
            remove_lock=True,
        )

    # Infer design (same idea as hfss_com.solver_init)
    if design_name is None:
        designs = getattr(hfss, "design_list", None) or []
        if len(designs) != 1:
            raise RuntimeError(
                f"Project '{project_path.name}' has {len(designs)} designs: {designs}. "
                "Please specify --design."
            )
        design_name = str(designs[0]).strip()

        # Ensure active design is the inferred one
        try:
            with _suppress_output(enabled=quiet):
                hfss.set_active_design(design_name)  # type: ignore[attr-defined]
        except Exception:
            pass

    return hfss


def _archive_old_param_file_if_any(*, timestamp: str) -> Path | None:
    if not PARAM_FILE.exists():
        return None

    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    dest = HISTORY_DIR / f"parameters_constraints {timestamp}.py"

    # Ensure uniqueness
    if dest.exists():
        i = 1
        while True:
            cand = HISTORY_DIR / f"parameters_constraints {timestamp} ({i}).py"
            if not cand.exists():
                dest = cand
                break
            i += 1

    shutil.move(str(PARAM_FILE), str(dest))
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="hfss_get_para_and_range.py",
        description=(
            "Read optimization-included variables (name/value/ranges) from job_template/*.aedt "
            "and regenerate job_template/parameters_constraints.py.  "
            "Supports both continuous and discrete ranges via the AEDT Level field."
        ),
    )
    parser.add_argument(
        "--project",
        type=str,
        default=None,
        help="Path to .aedt. Default: scan job_template/*.aedt (must be exactly one).",
    )
    parser.add_argument(
        "--design",
        type=str,
        default=None,
        help="Design name in the .aedt project. Default: if exactly one design, use it.",
    )
    parser.add_argument(
        "--graphical",
        action="store_true",
        help="Launch AEDT in graphical mode (default: non-graphical/headless).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show AEDT/PyAEDT output (default: quiet).",
    )
    args = parser.parse_args(argv)

    project_path = Path(args.project).resolve() if args.project else _scan_single_aedt_file(JOB_TEMPLATE_DIR)
    if not project_path.exists():
        raise FileNotFoundError(project_path)

    non_graphical = not bool(args.graphical)
    quiet = not bool(args.verbose)

    # Read existing parameters_constraints.py as template (before moving it)
    template_text: str | None = None
    if PARAM_FILE.exists():
        template_text = PARAM_FILE.read_text(encoding="utf-8")

    # ---- Primary path: parse .aedt file directly (supports discrete ranges) ----
    params: list[OptParam] | None = None
    try:
        params = _collect_parameters_from_aedt_file(project_path)
        if params:
            print(f"[OK] Parsed {len(params)} optimization parameter(s) from AEDT file directly.")
        else:
            params = None  # fall through to PyAEDT
    except Exception as exc:
        if not quiet:
            print(f"[INFO] AEDT file parsing did not succeed ({exc}); trying PyAEDT fallback.")
        params = None

    # ---- Fallback: PyAEDT (continuous ranges only) ----
    if not params:
        hfss = None
        try:
            hfss = _open_hfss_project(
                project_path, design_name=DESIGN_NAME,
                non_graphical=non_graphical, quiet=quiet,
            )
            params = _collect_optimization_parameters(hfss)
        finally:
            if hfss is not None:
                try:
                    with _suppress_output(enabled=quiet):
                        hfss.release_desktop()
                except Exception:
                    pass

    if not params:
        raise RuntimeError(
            "No optimization-included variables found (or ranges/values were not parseable). "
            "Check your HFSS variable optimization settings."
        )

    try:
        new_text = _build_parameters_constraints_text(params, template_text)
    except (SyntaxError, ValueError):
        new_text = _default_parameters_constraints_text(_build_parameters_block(params))

    # Write to a temp file first, then archive old, then atomically move temp into place
    timestamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    tmp_path = JOB_TEMPLATE_DIR / f".parameters_constraints.py.tmp_{os.getpid()}"
    try:
        tmp_path.write_text(new_text, encoding="utf-8")

        archived = _archive_old_param_file_if_any(timestamp=timestamp)
        os.replace(str(tmp_path), str(PARAM_FILE))

        # Minimal console output
        print(f"[OK] Project: {project_path}")
        print(f"[OK] Found {len(params)} optimization parameter(s).")
        if archived:
            print(f"[OK] Archived old parameters_constraints.py -> {archived}")
        print(f"[OK] Wrote new parameters_constraints.py -> {PARAM_FILE}")
        return 0
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
