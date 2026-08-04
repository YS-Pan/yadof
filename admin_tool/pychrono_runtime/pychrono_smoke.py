"""Validate the isolated shared PyChrono interpreter with a mechanics step."""

import importlib.util
import json
import math
import os
import pathlib
import site
import sys
import tempfile

import pychrono as chrono


expected_python = pathlib.Path(
    os.environ["YADOF_EXPECTED_PYCHRONO_PYTHON"]
).resolve()
expected_version = os.environ["YADOF_EXPECTED_PYCHRONO_VERSION"]
expected_build = os.environ["YADOF_EXPECTED_PYCHRONO_BUILD"]
actual_python = pathlib.Path(sys.executable).resolve()
if actual_python != expected_python:
    raise RuntimeError(f"unexpected interpreter: {actual_python}")
if os.environ.get("PYTHONPATH"):
    raise RuntimeError("PYTHONPATH leaked into the PyChrono process")
if site.ENABLE_USER_SITE:
    raise RuntimeError("user site is enabled")
if importlib.util.find_spec("yadof") is not None:
    raise RuntimeError("yadof is importable in the PyChrono environment")

metadata_files = list(
    (pathlib.Path(sys.prefix) / "conda-meta").glob("pychrono-*.json")
)
if len(metadata_files) != 1:
    raise RuntimeError(f"expected one PyChrono Conda record, found {metadata_files}")
package_metadata = json.loads(metadata_files[0].read_text(encoding="utf-8"))
version = str(package_metadata["version"])
build = str(package_metadata["build"])
if version != expected_version or build != expected_build:
    raise RuntimeError(f"unexpected PyChrono package: {version} {build}")
if "projectchrono/label/release" not in str(package_metadata["channel"]):
    raise RuntimeError("PyChrono is not from the official release channel")

system = chrono.ChSystemNSC()
system.SetGravitationalAcceleration(chrono.ChVector3d(0.0, -9.81, 0.0))
body = chrono.ChBody()
body.SetMass(2.0)
body.SetPos(chrono.ChVector3d(0.0, 1.0, 0.0))
system.AddBody(body)
system.DoStepDynamics(0.01)
velocity_y = float(body.GetPosDt().y)
if not math.isfinite(velocity_y) or not (-0.2 < velocity_y < -0.01):
    raise RuntimeError(f"unexpected gravity response: {velocity_y}")

print(
    json.dumps(
        {
            "schema_version": 1,
            "python_executable": str(actual_python),
            "python_version": sys.version,
            "pychrono_version": version,
            "pychrono_build": build,
            "pychrono_channel": package_metadata["channel"],
            "pychrono_module": str(pathlib.Path(chrono.__file__).resolve()),
            "velocity_y_after_0_01_s": velocity_y,
            "temp_directory": tempfile.gettempdir(),
            "pythonpath_present": bool(os.environ.get("PYTHONPATH")),
            "user_site_enabled": bool(site.ENABLE_USER_SITE),
            "yadof_importable": importlib.util.find_spec("yadof") is not None,
        },
        sort_keys=True,
    )
)
