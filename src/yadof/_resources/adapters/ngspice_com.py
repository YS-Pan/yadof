"""Reusable ngspice batch-process adapter resource.

Copy this file into a workspace before importing it from ``workflow.py``.  The
adapter keeps the source netlist unchanged, writes one candidate-specific driver
netlist, runs the executable selected by ``YADOF_NGSPICE_EXE``, and converts one
ASCII rawfile vector into schema-versioned yadof rawData.
"""

from __future__ import annotations

import json
import math
import os
import re
import runpy
import subprocess
from dataclasses import dataclass, field
from numbers import Real
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np


RAWDATA_SCHEMA_VERSION = 1
_PARAMETER_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_END_RE = re.compile(r"^\s*\.end\s*(?:(?:;|\$).*)?$", re.IGNORECASE)
_CONTROL_RE = re.compile(r"^\s*\.(?:control|endc)\b", re.IGNORECASE)


class NgspiceError(RuntimeError):
    """Base error raised by the adapter."""


class NgspiceRawFileError(NgspiceError):
    """Raised when an ngspice rawfile does not match the supported ASCII format."""


@dataclass(slots=True)
class NgspiceSession:
    """Resolved executable, declarative netlist, scratch directory, and parameters."""

    executable: Path
    netlist: Path
    work_dir: Path
    parameters: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class NgspiceRunResult:
    """Files and diagnostics produced by one completed ngspice process."""

    executable: Path
    driver_netlist: Path
    rawfile: Path
    logfile: Path
    analysis_command: str
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True, slots=True)
class NgspiceVariable:
    index: int
    name: str
    kind: str
    attributes: str = ""


@dataclass(frozen=True, slots=True)
class NgspicePlot:
    title: str
    plot_name: str
    flags: tuple[str, ...]
    variables: tuple[NgspiceVariable, ...]
    values: np.ndarray

    def variable_index(self, name: str) -> int:
        selected = str(name).strip().lower()
        matches = [
            item.index
            for item in self.variables
            if item.name.lower() == selected
        ]
        if len(matches) != 1:
            choices = ", ".join(item.name for item in self.variables)
            raise KeyError(f"ngspice vector {name!r} not found; available vectors: {choices}")
        return matches[0]


def _resolved_file(path: str | Path, label: str) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"{label} does not exist or is not a file: {resolved}")
    return resolved


def _single_line(value: object, label: str) -> str:
    text = str(value).strip()
    if not text or any(character in text for character in "\r\n;"):
        raise ValueError(f"{label} must be one non-empty ngspice command-line value")
    return text


def _parameter_value(value: object) -> str:
    if isinstance(value, bool):
        raise TypeError("ngspice parameter values must not be booleans")
    if isinstance(value, Real):
        numeric = float(value)
        if not math.isfinite(numeric):
            raise ValueError("ngspice parameter values must be finite")
        return f"{numeric:g}"
    return _single_line(value, "ngspice parameter value")


def _raw_path(path: str | Path, base: Path, default_name: str) -> Path:
    selected = Path(path) if path else Path(default_name)
    return (selected if selected.is_absolute() else base / selected).resolve()


def solver_init(
    netlist: str | Path,
    *,
    executable: str | Path | None = None,
    work_dir: str | Path | None = None,
) -> NgspiceSession:
    """Resolve one ngspice executable and declarative source netlist.

    ``executable`` overrides ``YADOF_NGSPICE_EXE``.  The function does not launch
    ngspice or modify the netlist.
    """

    netlist_path = _resolved_file(netlist, "ngspice netlist")
    configured_executable = executable or os.environ.get("YADOF_NGSPICE_EXE")
    if not configured_executable:
        raise NgspiceError(
            "ngspice executable is not configured; set YADOF_NGSPICE_EXE or pass executable="
        )
    executable_path = _resolved_file(configured_executable, "ngspice executable")
    selected_work_dir = Path(work_dir).expanduser().resolve() if work_dir else netlist_path.parent
    selected_work_dir.mkdir(parents=True, exist_ok=True)
    if not selected_work_dir.is_dir():
        raise NotADirectoryError(f"ngspice work_dir is not a directory: {selected_work_dir}")
    return NgspiceSession(executable_path, netlist_path, selected_work_dir)


def set_variables(session: NgspiceSession, name_to_value: Mapping[str, object]) -> bool:
    """Set top-level ``.param`` values that the next :func:`analyze` will apply."""

    updates: dict[str, str] = {}
    for raw_name, raw_value in dict(name_to_value or {}).items():
        name = str(raw_name).strip()
        if not _PARAMETER_NAME_RE.fullmatch(name):
            raise ValueError(f"invalid ngspice top-level parameter name: {raw_name!r}")
        updates[name] = _parameter_value(raw_value)
    session.parameters.update(updates)
    return True


def _load_parameters_py_value_only(path: str | Path) -> dict[str, str]:
    parameter_path = _resolved_file(path, "parameter file")
    namespace = runpy.run_path(str(parameter_path))
    parameters = namespace.get("PARAMETERS")
    if parameters is None:
        raise ValueError(f"{str(parameter_path)!r} does not define PARAMETERS")
    output: dict[str, str] = {}
    for parameter in parameters:
        name = str(parameter.name)
        unit = str(getattr(parameter, "unit", "") or "")
        value = float(parameter.value)
        if not math.isfinite(value):
            raise ValueError(f"Parameter {name!r} value must be finite")
        output[name] = f"{value:g}{unit}" if unit else f"{value:g}"
    return output


def set_para(
    session: NgspiceSession,
    para_file: str | Path = "parameters_constraints.py",
) -> bool:
    """Load assigned yadof parameters and stage them for the next simulation."""

    return set_variables(session, _load_parameters_py_value_only(para_file))


def _ngspice_output_path(path: Path, work_dir: Path) -> str:
    try:
        relative = path.resolve().relative_to(work_dir.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"ngspice rawfile must be inside work_dir: {path}") from exc
    if not relative or any(character.isspace() for character in relative) or '"' in relative:
        raise ValueError(f"ngspice rawfile path below work_dir must not contain whitespace: {path}")
    return relative


def _build_driver_netlist(
    source: str,
    *,
    parameters: Mapping[str, str],
    analysis_command: str,
    rawfile: Path,
    work_dir: Path,
    vectors: Sequence[str],
) -> str:
    lines = source.splitlines()
    if any(_CONTROL_RE.match(line) for line in lines):
        raise NgspiceError(
            "source netlist must not contain .control/.endc; analyze() owns the batch control block"
        )
    end_indices = [index for index, line in enumerate(lines) if _END_RE.match(line)]
    if len(end_indices) != 1:
        raise NgspiceError(
            f"source netlist must contain exactly one top-level .end line; found {len(end_indices)}"
        )

    command = _single_line(analysis_command, "analysis_command")
    selected_vectors = tuple(_single_line(item, "ngspice output vector") for item in vectors)
    if not selected_vectors:
        raise ValueError("vectors must contain at least one ngspice vector or 'all'")

    control = [".control", "set filetype=ascii"]
    for name, value in parameters.items():
        control.append(f"alterparam {name} = {value}")
    if parameters:
        control.append("reset")
    control.extend(
        [
            command,
            f"write {_ngspice_output_path(rawfile, work_dir)} {' '.join(selected_vectors)}",
            "quit",
            ".endc",
        ]
    )
    end_index = end_indices[0]
    return "\n".join(lines[:end_index] + control + lines[end_index:]) + "\n"


def _log_tail(path: Path, limit: int = 4000) -> str:
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[-limit:]


def _log_has_error(path: Path) -> bool:
    if not path.is_file():
        return False
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        return any(
            re.match(r"^\s*(?:fatal\s+)?error\s*:", line, re.IGNORECASE)
            for line in stream
        )


def analyze(
    session: NgspiceSession,
    *,
    analysis_command: str = "run",
    vectors: Sequence[str] = ("all",),
    timeout: float | None = None,
    rawfile: str | Path = "ngspice.raw",
    logfile: str | Path = "ngspice.log",
    driver_netlist: str | Path = "ngspice_yadof.cir",
) -> NgspiceRunResult:
    """Run one isolated ngspice batch process and validate its ASCII rawfile."""

    raw_path = _raw_path(rawfile, session.work_dir, "ngspice.raw")
    log_path = _raw_path(logfile, session.work_dir, "ngspice.log")
    driver_path = _raw_path(driver_netlist, session.work_dir, "ngspice_yadof.cir")
    if len({raw_path, log_path, driver_path, session.netlist}) != 4:
        raise ValueError("netlist, driver_netlist, rawfile, and logfile paths must be distinct")
    for path in (raw_path, log_path, driver_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    source = session.netlist.read_text(encoding="utf-8-sig")
    rendered = _build_driver_netlist(
        source,
        parameters=session.parameters,
        analysis_command=analysis_command,
        rawfile=raw_path,
        work_dir=session.work_dir,
        vectors=vectors,
    )
    for stale in (raw_path, log_path):
        stale.unlink(missing_ok=True)
    driver_path.write_text(rendered, encoding="utf-8", newline="\n")

    command = [
        str(session.executable),
        "-n",
        "-b",
        "-o",
        str(log_path),
        str(driver_path),
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=session.work_dir,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise NgspiceError(
            f"ngspice exceeded timeout={timeout!r} seconds\n{_log_tail(log_path)}"
        ) from exc
    except OSError as exc:
        raise NgspiceError(f"could not start ngspice executable {session.executable}: {exc}") from exc

    if completed.returncode != 0:
        raise NgspiceError(
            f"ngspice exited with code {completed.returncode}\n{_log_tail(log_path)}"
        )
    if _log_has_error(log_path):
        raise NgspiceError(f"ngspice reported an error\n{_log_tail(log_path)}")
    if not raw_path.is_file() or raw_path.stat().st_size == 0:
        raise NgspiceError(f"ngspice did not create a non-empty rawfile\n{_log_tail(log_path)}")
    read_rawfile(raw_path)
    return NgspiceRunResult(
        executable=session.executable,
        driver_netlist=driver_path,
        rawfile=raw_path,
        logfile=log_path,
        analysis_command=str(analysis_command),
        returncode=int(completed.returncode),
        stdout=str(completed.stdout or ""),
        stderr=str(completed.stderr or ""),
    )


def _header_value(headers: Mapping[str, str], name: str) -> str:
    try:
        return headers[name.lower()]
    except KeyError as exc:
        raise NgspiceRawFileError(f"ngspice rawfile is missing {name!r}") from exc


def _parse_raw_value(token: str, *, complex_values: bool) -> complex | float:
    text = token.strip().strip("()")
    try:
        if complex_values:
            real_text, imaginary_text = text.split(",", 1)
            return complex(float(real_text), float(imaginary_text))
        return float(text)
    except (TypeError, ValueError) as exc:
        raise NgspiceRawFileError(f"invalid ngspice raw value: {token!r}") from exc


def read_rawfile(path: str | Path) -> NgspicePlot:
    """Parse the single-plot ASCII rawfile emitted by :func:`analyze`."""

    raw_path = _resolved_file(path, "ngspice rawfile")
    lines = raw_path.read_text(encoding="utf-8", errors="replace").splitlines()
    headers: dict[str, str] = {}
    variable_marker = None
    value_marker = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        lowered = stripped.lower()
        if lowered == "variables:":
            variable_marker = index
            break
        if lowered == "binary:":
            raise NgspiceRawFileError(
                "binary ngspice rawfiles are unsupported; use analyze() to request ASCII output"
            )
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()
    if variable_marker is None:
        raise NgspiceRawFileError("ngspice rawfile has no Variables section")

    try:
        variable_count = int(_header_value(headers, "No. Variables"))
        point_count = int(_header_value(headers, "No. Points"))
    except ValueError as exc:
        raise NgspiceRawFileError("ngspice rawfile has invalid variable/point counts") from exc
    variables: list[NgspiceVariable] = []
    cursor = variable_marker + 1
    while cursor < len(lines) and len(variables) < variable_count:
        stripped = lines[cursor].strip()
        cursor += 1
        if not stripped:
            continue
        if stripped.lower() == "values:":
            break
        parts = stripped.split()
        if len(parts) < 3:
            raise NgspiceRawFileError(f"invalid ngspice variable declaration: {stripped!r}")
        try:
            variable_index = int(parts[0])
        except ValueError as exc:
            raise NgspiceRawFileError(f"invalid ngspice variable index: {parts[0]!r}") from exc
        variables.append(
            NgspiceVariable(variable_index, parts[1], parts[2], " ".join(parts[3:]))
        )
    if len(variables) != variable_count:
        raise NgspiceRawFileError(
            f"ngspice rawfile declares {variable_count} variables but contains {len(variables)}"
        )
    while cursor < len(lines):
        if lines[cursor].strip().lower() == "values:":
            value_marker = cursor
            break
        cursor += 1
    if value_marker is None:
        raise NgspiceRawFileError("ngspice rawfile has no Values section")

    flags = tuple(item.lower() for item in _header_value(headers, "Flags").split())
    complex_values = "complex" in flags
    dtype = np.complex128 if complex_values else np.float64
    values = np.empty((point_count, variable_count), dtype=dtype)
    cursor = value_marker + 1
    for point_index in range(point_count):
        while cursor < len(lines) and not lines[cursor].strip():
            cursor += 1
        if cursor >= len(lines):
            raise NgspiceRawFileError(f"rawfile ended before point {point_index}")
        first = lines[cursor].strip().split()
        cursor += 1
        if len(first) < 2:
            raise NgspiceRawFileError(f"invalid first value for point {point_index}")
        try:
            raw_point_index = int(first[0])
        except ValueError as exc:
            raise NgspiceRawFileError(f"invalid point index: {first[0]!r}") from exc
        if raw_point_index != point_index:
            raise NgspiceRawFileError(
                f"unexpected point index {raw_point_index}; expected {point_index}"
            )
        values[point_index, 0] = _parse_raw_value(first[1], complex_values=complex_values)
        for variable_index in range(1, variable_count):
            while cursor < len(lines) and not lines[cursor].strip():
                cursor += 1
            if cursor >= len(lines):
                raise NgspiceRawFileError(
                    f"rawfile ended at point {point_index}, variable {variable_index}"
                )
            token = lines[cursor].strip().split()[0]
            cursor += 1
            values[point_index, variable_index] = _parse_raw_value(
                token, complex_values=complex_values
            )
    return NgspicePlot(
        title=_header_value(headers, "Title"),
        plot_name=_header_value(headers, "Plotname"),
        flags=flags,
        variables=tuple(variables),
        values=values,
    )


def _component_values(values: np.ndarray, component: str) -> np.ndarray:
    selected = str(component).strip().lower()
    functions = {
        "real": np.real,
        "imag": np.imag,
        "magnitude": np.abs,
        "phase_rad": np.angle,
        "phase_deg": lambda item: np.degrees(np.angle(item)),
        "db20": lambda item: 20.0 * np.log10(np.abs(item)),
    }
    if selected not in functions:
        choices = ", ".join(functions)
        raise ValueError(f"unknown ngspice component {component!r}; expected one of: {choices}")
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.asarray(functions[selected](values), dtype=float)


def _sanitize_filename(value: str, max_len: int = 180) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1F\s]+', "_", str(value).strip()).strip(" ._")
    name = re.sub(r"_+", "_", name) or "unnamed"
    return name[:max_len]


def _axis_name(variable: NgspiceVariable) -> str:
    name = re.sub(r"[^A-Za-z0-9_]+", "_", variable.name).strip("_")
    return name or "scale"


def _unit_for_kind(kind: str) -> str:
    return {
        "time": "s",
        "frequency": "Hz",
        "voltage": "V",
        "current": "A",
    }.get(str(kind).lower(), "")


def save_result(
    result_or_rawfile: NgspiceRunResult | str | Path,
    vector: str,
    *,
    component: str = "real",
    out_dir: str | Path = "rawData",
    output_name: str | None = None,
    metadata: Mapping[str, object] | None = None,
) -> str:
    """Export one ngspice vector as a float yadof rawData ``.npz`` file."""

    rawfile = (
        result_or_rawfile.rawfile
        if isinstance(result_or_rawfile, NgspiceRunResult)
        else Path(result_or_rawfile)
    )
    plot = read_rawfile(rawfile)
    variable_index = plot.variable_index(vector)
    variable = plot.variables[variable_index]
    selected_component = str(component).strip().lower()
    data = _component_values(plot.values[:, variable_index], selected_component)

    rawdata_name = _sanitize_filename(output_name or f"{variable.name}_{selected_component}")
    if rawdata_name.lower().endswith(".npz"):
        rawdata_name = rawdata_name[:-4]
    output_dir = Path(out_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{rawdata_name}.npz"

    extra_arrays: dict[str, np.ndarray] = {}
    axis_names: list[str] = []
    axes: list[dict[str, object]] = []
    if data.size != 1:
        scale_variable = plot.variables[0]
        scale_values = np.asarray(plot.values[:, 0])
        if np.any(np.abs(np.imag(scale_values)) > 0.0):
            raise NgspiceRawFileError("ngspice scale vector has non-zero imaginary values")
        axis_name = _axis_name(scale_variable)
        axis_key = f"axis_{axis_name}"
        axis_unit = _unit_for_kind(scale_variable.kind)
        axis_names.append(axis_name)
        descriptor: dict[str, object] = {
            "index": 0,
            "size": int(data.size),
            "name": axis_name,
            "values_key": axis_key,
        }
        if axis_unit:
            descriptor["unit"] = axis_unit
        axes.append(descriptor)
        extra_arrays[axis_key] = np.asarray(np.real(scale_values), dtype=float)
    else:
        data = np.asarray(data[0], dtype=float)

    rawdata_metadata = dict(metadata or {})
    rawdata_metadata.update(
        {
            "schema_version": RAWDATA_SCHEMA_VERSION,
            "rawdata_name": rawdata_name,
            "shape": [int(size) for size in data.shape],
            "axis_names": axis_names,
            "axes": axes,
            "simulator": "ngspice",
            "source": "ngspice ASCII rawfile",
            "ngspice_title": plot.title,
            "ngspice_plot_name": plot.plot_name,
            "ngspice_vector": variable.name,
            "ngspice_vector_type": variable.kind,
            "ngspice_component": selected_component,
            "ngspice_scale_vector": plot.variables[0].name if data.shape else None,
        }
    )
    temporary_path = output_path.with_name(output_path.name + ".tmp.npz")
    try:
        np.savez_compressed(
            temporary_path,
            data=data,
            metadata=json.dumps(rawdata_metadata, ensure_ascii=True, default=str),
            **extra_arrays,
        )
        os.replace(temporary_path, output_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return str(output_path)


__all__ = [
    "NgspiceError",
    "NgspicePlot",
    "NgspiceRawFileError",
    "NgspiceRunResult",
    "NgspiceSession",
    "NgspiceVariable",
    "analyze",
    "read_rawfile",
    "save_result",
    "set_para",
    "set_variables",
    "solver_init",
]
