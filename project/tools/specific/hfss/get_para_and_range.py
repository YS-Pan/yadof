# tools/specific/hfss/get_para_and_range.py
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
from typing import Any, Iterable


# =========================================================
# Paths
# =========================================================
_THIS_FILE = Path(__file__).resolve()
ROOT_DIR = _THIS_FILE.parents[3]  # .../project/tools/specific/hfss/ -> project/
JOB_TEMPLATE_DIR = ROOT_DIR / "job_template"
PARAM_FILE = JOB_TEMPLATE_DIR / "parameters_constraints.py"
HISTORY_DIR = JOB_TEMPLATE_DIR / "history"


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


def _default_parameters_constraints_text(parameters_block: str) -> str:
    if not parameters_block.endswith("\n"):
        parameters_block += "\n"

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
        "CONSTRAINTS: tuple[str, ...] = ()\n"
        "\n"
        "\n"
        "def get_parameters() -> tuple[Parameter, ...]:\n"
        "    return tuple(PARAMETERS)\n"
    )


# =========================================================
# Helpers (HFSS variable extraction)
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
                # if property getter fails, try next
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
    # Prefer the variable's expression (often like "11mm")
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

    # Fallback: try numeric_value + units (if available)
    nv = _get_attr(var_obj, ["numeric_value"])
    if nv is not None:
        try:
            val = float(nv)
            unit = str(_get_attr(var_obj, ["units", "unit"]) or "")
            return val, unit
        except Exception:
            pass

    # Last fallback: try the underlying oDesign API if present
    try:
        odesign = getattr(hfss, "_odesign", None)
        if odesign is not None and hasattr(odesign, "GetVariableValue"):
            raw = odesign.GetVariableValue(var_name)
            val, unit = _parse_value_with_unit(raw)
            return val, unit
    except Exception:
        pass

    return None, ""


@dataclass(frozen=True)
class OptParam:
    name: str
    lo: float
    hi: float
    value: float
    unit: str


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

            out.append(OptParam(name=str(var_name), lo=float(lo), hi=float(hi), value=float(cur), unit=str(unit)))
        except Exception:
            # Keep going; one bad variable should not block others.
            # (If you prefer strict behavior, change to `raise`.)
            continue

    out.sort(key=lambda p: p.name.lower())
    return out


def _build_parameters_block(params: list[OptParam]) -> str:
    lines: list[str] = []
    lines.append("PARAMETERS = (\n")
    for p in params:
        ranges_src = f"(({_format_float(p.lo)}, {_format_float(p.hi)}),)"
        line = (
            f"    Parameter({p.name!r}, {ranges_src}, "
            f"unit={p.unit!r}),\n"
        )
        lines.append(line)
    lines.append(")\n")
    return "".join(lines)


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
        prog="get_para_and_range.py",
        description=(
            "Read optimization-enabled variables (name/value/min/max) from job_template/*.aedt "
            "and regenerate job_template/parameters_constraints.py."
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

    hfss = None
    try:
        hfss = _open_hfss_project(project_path, args.design, non_graphical=non_graphical, quiet=quiet)
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
            "No optimization-enabled variables found (or ranges/values were not parseable). "
            "Check your HFSS variable optimization settings."
        )

    parameters_block = _build_parameters_block(params)

    # Build new file content: prefer replacing PARAMETERS in old file (clone_paraFile.py style)
    if template_text:
        try:
            new_text = _replace_top_level_assignment(
                template_text, target_name="PARAMETERS", replacement_block=parameters_block
            )
        except Exception:
            # Fallback: generate a minimal new file if replacement fails
            new_text = _default_parameters_constraints_text(parameters_block)
    else:
        new_text = _default_parameters_constraints_text(parameters_block)

    # Write to a temp file first, then archive old, then atomically move temp into place
    timestamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    tmp_path = ROOT_DIR / f".parameters_constraints.py.tmp_{os.getpid()}"
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
